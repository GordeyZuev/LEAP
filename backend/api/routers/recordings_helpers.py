"""Shared helpers for recording HTTP routes (export, dry-run, response shaping, bulk ID resolution)."""

from __future__ import annotations

import csv
import io
from io import StringIO
from typing import Any, Literal

from fastapi import HTTPException, status

from api.core.context import ServiceContext
from api.repositories.recording_repos import RecordingRepository
from api.schemas.recording.filters import RecordingFilters as RecordingFiltersSchema
from api.schemas.recording.operations import BulkProcessDryRunResponse, DryRunResponse
from api.schemas.recording.request import ConfigOverrideRequest
from api.schemas.recording.response import ProcessingStageResponse, SourceInfo, UploadInfo
from api.services.config_utils import (
    BoundTemplateNotFoundError,
    InvalidOutputPresetsError,
    RuntimeTemplateNotFoundError,
    resolve_full_config,
)
from models import ProcessingStatus
from models.recording import ProcessingStageStatus, ProcessingStageType, TargetStatus

_CONFIG_RESOLUTION_HTTP_ERRORS = (
    RuntimeTemplateNotFoundError,
    BoundTemplateNotFoundError,
    InvalidOutputPresetsError,
)


def _merged_positive_int_lists(*groups: list[int] | None) -> list[int] | None:
    xs: list[int] = []
    for g in groups:
        if g:
            xs.extend(g)
    out = sorted({i for i in xs if i > 0})
    return out if out else None


def _build_override_from_flexible(config: ConfigOverrideRequest) -> dict:
    """
    Convert ConfigOverrideRequest to manual_override dictionary.

    Returns a dict that will be merged with resolved config hierarchy.
    """
    override: dict = {}

    if config.template_id:
        override["runtime_template_id"] = config.template_id

    if config.processing_config:
        override["processing_config"] = config.processing_config

    if config.metadata_config:
        override["metadata_config"] = config.metadata_config

    if config.output_config:
        override["output_config"] = config.output_config

    return override


# ============================================================================
# Bulk operations — ID resolution
# ============================================================================


async def _resolve_recording_ids(
    recording_ids: list[int] | None,
    filters: RecordingFiltersSchema | None,
    limit: int,
    ctx: ServiceContext,
) -> list[int]:
    """Universal resolver: returns recording IDs from explicit list or filters."""
    if recording_ids:
        return recording_ids

    if filters:
        return await _query_recordings_by_filters(filters, limit, ctx)

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Either recording_ids or filters must be specified",
    )


async def _query_recordings_by_filters(
    filters: RecordingFiltersSchema,
    limit: int,
    ctx: ServiceContext,
) -> list[int]:
    """Build query by filters and return list of recording IDs (delegates to repository)."""
    from_dt = None
    to_dt = None

    if filters.from_date:
        from utils.date_utils import InvalidDateFormatError, parse_from_date_to_datetime

        try:
            from_dt = parse_from_date_to_datetime(filters.from_date)
        except InvalidDateFormatError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    if filters.to_date:
        from utils.date_utils import InvalidDateFormatError, parse_to_date_to_datetime

        try:
            to_dt = parse_to_date_to_datetime(filters.to_date)
        except InvalidDateFormatError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    recording_repo = RecordingRepository(ctx.session)
    template_ids = _merged_positive_int_lists(
        filters.template_ids,
        [filters.template_id] if filters.template_id is not None else None,
    )
    source_ids = _merged_positive_int_lists(
        filters.source_ids,
        [filters.source_id] if filters.source_id is not None else None,
    )
    return await recording_repo.get_filtered_ids(
        ctx.user_id,
        template_ids=template_ids,
        source_ids=source_ids,
        statuses=filters.status,
        failed=filters.failed,
        is_mapped=filters.is_mapped,
        exclude_blank=filters.exclude_blank,
        include_deleted=filters.include_deleted,
        from_dt=from_dt,
        to_dt=to_dt,
        search=filters.search,
        sort_by=filters.order_by,
        sort_order=filters.order,
        limit=limit,
    )


def _build_source_info(recording) -> SourceInfo | None:
    """Build SourceInfo from recording.source."""
    if not recording.source:
        return None
    return SourceInfo(
        type=recording.source.source_type,
        name=recording.source.input_source.name if recording.source.input_source else None,
        input_source_id=recording.source.input_source_id,
    )


def _build_uploads_dict(outputs) -> dict:
    """Build uploads dictionary from recording outputs."""
    uploads = {}
    for output in outputs or []:
        tt = output.target_type
        platform = (getattr(tt, "value", tt) or "").lower()
        if not platform:
            continue
        st = output.status
        status_str = (getattr(st, "value", st) or "").lower() or "unknown"
        url = None
        if output.target_meta:
            url = (
                output.target_meta.get("video_url")
                or output.target_meta.get("target_link")
                or output.target_meta.get("url")
            )
        uploads[platform] = UploadInfo(
            status=status_str,
            url=url,
            started_at=output.started_at,
            uploaded_at=output.uploaded_at,
            error=output.failed_reason if output.failed else None,
        )
    return uploads


def _build_processing_stages(stages) -> list[ProcessingStageResponse]:
    """Build processing stages list from recording stages."""
    return [
        ProcessingStageResponse(
            stage_type=stage.stage_type.value,
            status=stage.status.value,
            failed=stage.failed,
            failed_at=stage.failed_at,
            failed_reason=stage.failed_reason,
            retry_count=stage.retry_count,
            started_at=stage.started_at,
            completed_at=stage.completed_at,
        )
        for stage in stages or []
    ]


# ============================================================================
# Export
# ============================================================================

PLATFORM_ORDER = [
    "youtube",
    "vk",
    "yandex_disk",
    "rutube",
    "google_drive",
    "local_storage",
    "other",
]


def _collect_platforms_from_recordings(recordings: list[Any]) -> list[str]:
    """Collect unique target types: canonical order first, then remaining platforms sorted."""
    seen: set[str] = set()
    for r in recordings:
        for output in r.outputs or []:
            tt = output.target_type
            platform = (getattr(tt, "value", tt) or "").lower()
            if platform:
                seen.add(platform)
    ordered = [p for p in PLATFORM_ORDER if p in seen]
    rest = sorted(seen.difference(ordered))
    return ordered + rest


def _extract_output_url(output: Any) -> str | None:
    """Extract video URL from output target_meta."""
    if not output.target_meta:
        return None
    return output.target_meta.get("video_url") or output.target_meta.get("target_link") or output.target_meta.get("url")


def _build_export_row(
    recording: Any,
    platforms: list[str],
    verbosity: Literal["short", "long"],
    questions: list[str] | None = None,
) -> dict[str, Any]:
    """
    Build single export row as dict.

    Args:
        recording: Recording model with outputs, main_topics, etc.
        platforms: List of platform keys (youtube, vk, ...) to include.
        verbosity: short (core + urls) or long (full details).
        questions: Self-check questions from extracted.json (for verbosity=long).

    Returns:
        Flat dict suitable for JSON/CSV/XLSX export.
    """
    outputs_by_platform: dict[str, Any] = {}
    for output in recording.outputs or []:
        tt = output.target_type
        platform = (getattr(tt, "value", tt) or "").lower()
        if platform:
            st = output.status
            outputs_by_platform[platform] = {
                "url": _extract_output_url(output),
                "status": (getattr(st, "value", st) or "").lower(),
            }

    row: dict[str, Any] = {
        "id": recording.id,
        "display_name": recording.display_name,
        "start_time": recording.start_time.isoformat() if recording.start_time else None,
        "duration": recording.duration,
        "status": (getattr(recording.status, "value", recording.status) if recording.status else None),
    }

    for platform in platforms:
        info = outputs_by_platform.get(platform, {})
        row[f"{platform}_url"] = info.get("url")
        if verbosity == "long":
            row[f"{platform}_status"] = info.get("status")

    if recording.main_topics:
        row["main_topics"] = recording.main_topics
    else:
        row["main_topics"] = None

    if verbosity == "long":
        row["questions"] = questions if questions else None
        row["failed"] = recording.failed
        row["failed_reason"] = recording.failed_reason
        row["failed_at_stage"] = recording.failed_at_stage
        row["is_mapped"] = recording.is_mapped
        row["template_id"] = recording.template_id
        row["template_name"] = recording.template.name if recording.template else None
        stype = recording.source.source_type if recording.source else None
        row["source_type"] = getattr(stype, "value", stype) if stype else None
        row["source_name"] = (
            recording.source.input_source.name if recording.source and recording.source.input_source else None
        )
        row["deleted"] = recording.deleted
        row["deleted_at"] = recording.deleted_at.isoformat() if recording.deleted_at else None
        row["on_pause"] = recording.on_pause
        row["created_at"] = recording.created_at.isoformat() if recording.created_at else None
        row["updated_at"] = recording.updated_at.isoformat() if recording.updated_at else None

    return row


def _get_export_column_order(platforms: list[str], verbosity: Literal["short", "long"]) -> list[str]:
    """Return ordered column names for export."""
    if verbosity == "short":
        base = ["id", "display_name", "start_time", "duration", "status"]
        platform_cols = [f"{p}_url" for p in platforms]
        return base + platform_cols + ["main_topics"]
    base = [
        "id",
        "display_name",
        "start_time",
        "duration",
        "status",
        "failed",
        "failed_reason",
        "failed_at_stage",
        "is_mapped",
        "template_id",
        "template_name",
        "source_type",
        "source_name",
    ]
    platform_cols = []
    for p in platforms:
        platform_cols.extend([f"{p}_url", f"{p}_status"])
    return (
        base
        + platform_cols
        + ["main_topics", "questions", "deleted", "deleted_at", "on_pause", "created_at", "updated_at"]
    )


def _format_cell_value(value: Any) -> str:
    """Format value for CSV (handle lists, None, datetime)."""
    if value is None:
        return ""
    if isinstance(value, list):
        return "; ".join(str(v) for v in value)
    return str(value)


def _generate_csv(rows: list[dict], columns: list[str]) -> str:
    """Generate CSV content as string (UTF-8 with BOM)."""
    buf = StringIO()
    buf.write("\ufeff")  # BOM for Excel
    writer = csv.writer(buf, quoting=csv.QUOTE_MINIMAL)
    writer.writerow(columns)
    for row in rows:
        writer.writerow([_format_cell_value(row.get(c)) for c in columns])
    return buf.getvalue()


def _generate_xlsx_bytes(rows: list[dict], columns: list[str]) -> bytes:
    """Generate XLSX file as bytes."""
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "Recordings"
    ws.append(columns)
    for row in rows:
        ws.append([_format_cell_value(row.get(c)) for c in columns])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ============================================================================
# Dry-run
# ============================================================================


async def _execute_dry_run_single(
    recording_id: int,
    config_override: ConfigOverrideRequest | None,
    ctx: ServiceContext,
) -> DryRunResponse:
    """
    Dry-run: shows what /run will do based on config and current state.
    Shows detailed plan of what steps will be executed.
    """
    from api.repositories.template_repos import OutputPresetRepository

    recording_repo = RecordingRepository(ctx.session)
    recording = await recording_repo.get_by_id(recording_id, ctx.user_id)

    if not recording:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recording not found")

    manual_override = _build_override_from_flexible(config_override) if config_override else None

    try:
        full_config, output_config, recording = await resolve_full_config(
            ctx.session,
            recording_id,
            ctx.user_id,
            manual_override=manual_override,
            include_output_config=True,
        )
    except _CONFIG_RESOLUTION_HTTP_ERRORS as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e

    stage_map: dict[str, Any] = {}
    for stage in recording.processing_stages or []:
        stt = stage.stage_type
        stage_type_str: str = str(getattr(stt, "value", stt))
        stage_map[stage_type_str] = stage

    def stage_done_with_reason(stage_type: ProcessingStageType) -> tuple[bool, str | None]:
        st = stage_map.get(stage_type.value)
        if not st:
            return False, None
        status_value = st.status.value if hasattr(st.status, "value") else str(st.status)
        if status_value == ProcessingStageStatus.COMPLETED.value:
            return True, "Completed"
        if status_value == ProcessingStageStatus.SKIPPED.value:
            detail = (st.failed_reason or "").strip()
            return True, detail or "Skipped"
        return False, None

    # Align with processing flags from resolved full_config (same keys as run_recording_task)
    trimming = full_config.get("trimming", {})
    transcription = full_config.get("transcription", {})

    trim_enabled = trimming.get("enable_trimming", True)
    transcribe_enabled = transcription.get("enable_transcription", True)
    extract_topics_enabled = transcription.get("enable_topics", True)
    generate_subs_enabled = transcription.get("enable_subtitles", True)

    upload_enabled = output_config.get("auto_upload", False)

    steps = []

    if recording.local_video_path:
        steps.append({"name": "download", "enabled": False, "skip_reason": "Completed"})
    else:
        steps.append({"name": "download", "enabled": True})

    if not trim_enabled:
        steps.append({"name": "trim", "enabled": False, "skip_reason": "Disabled in config"})
    else:
        done, reason = stage_done_with_reason(ProcessingStageType.TRIM)
        # processed_video_path: legacy recordings finished trim before TRIM stage existed
        if done or recording.processed_video_path:
            skip_reason = reason if done else "Completed"
            steps.append({"name": "trim", "enabled": False, "skip_reason": skip_reason})
        else:
            steps.append({"name": "trim", "enabled": True})

    if not transcribe_enabled:
        steps.append({"name": "transcribe", "enabled": False, "skip_reason": "Disabled in config"})
    else:
        done, reason = stage_done_with_reason(ProcessingStageType.TRANSCRIBE)
        if done:
            steps.append({"name": "transcribe", "enabled": False, "skip_reason": reason})
        else:
            steps.append({"name": "transcribe", "enabled": True})

    if not extract_topics_enabled:
        steps.append({"name": "topics", "enabled": False, "skip_reason": "Disabled in config"})
    else:
        done, reason = stage_done_with_reason(ProcessingStageType.EXTRACT_TOPICS)
        if done:
            steps.append({"name": "topics", "enabled": False, "skip_reason": reason})
        else:
            steps.append({"name": "topics", "enabled": True})

    if not generate_subs_enabled:
        steps.append({"name": "subtitles", "enabled": False, "skip_reason": "Disabled in config"})
    else:
        done, reason = stage_done_with_reason(ProcessingStageType.GENERATE_SUBTITLES)
        if done:
            steps.append({"name": "subtitles", "enabled": False, "skip_reason": reason})
        else:
            steps.append({"name": "subtitles", "enabled": True})

    if not upload_enabled:
        steps.append({"name": "upload", "enabled": False, "skip_reason": "Disabled in config"})
    else:
        preset_ids = output_config.get("preset_ids", [])

        if not preset_ids:
            steps.append({"name": "upload", "enabled": False, "skip_reason": "No presets configured"})
        else:
            preset_repo = OutputPresetRepository(ctx.session)
            presets = await preset_repo.find_by_ids(preset_ids, ctx.user_id)

            platform_statuses: dict[str, dict[str, Any]] = {}
            for output in recording.outputs or []:
                tt = output.target_type
                pkey = (getattr(tt, "value", tt) or "").lower()
                if not pkey:
                    continue
                platform_statuses[pkey] = {
                    "status": output.status,
                    "uploaded_at": output.uploaded_at.isoformat() if output.uploaded_at else None,
                }

            platforms_to_upload = []
            upload_details = []
            is_ready = recording.status == ProcessingStatus.READY

            for preset in presets:
                if not preset.is_active:
                    continue

                preset_key = str(preset.platform).lower()
                platform_status = platform_statuses.get(preset_key)

                if platform_status:
                    target_status = platform_status["status"]
                    if target_status == TargetStatus.UPLOADED:
                        upload_details.append(
                            {
                                "platform": preset.platform,
                                "status": "uploaded",
                                "uploaded_at": platform_status["uploaded_at"],
                            }
                        )
                    elif target_status == TargetStatus.FAILED:
                        platforms_to_upload.append(preset.platform)
                        upload_details.append({"platform": preset.platform, "status": "failed", "will_retry": True})
                    else:
                        platforms_to_upload.append(preset.platform)
                        upload_details.append({"platform": preset.platform, "status": "pending", "will_retry": True})
                elif is_ready:
                    upload_details.append({"platform": preset.platform, "status": "Completed"})
                else:
                    platforms_to_upload.append(preset.platform)
                    upload_details.append({"platform": preset.platform, "status": "not_started", "will_upload": True})

            upload_step = {"name": "upload", "enabled": bool(platforms_to_upload), "details": upload_details}

            if not platforms_to_upload:
                upload_step["skip_reason"] = "Completed"

            steps.append(upload_step)

    # Config sources info
    config_sources = {}

    if (config_override and config_override.template_id) or recording.template_id:
        from api.repositories.template_repos import RecordingTemplateRepository

        template_repo = RecordingTemplateRepository(ctx.session)

        if config_override and config_override.template_id:
            runtime_template = await template_repo.find_by_id(config_override.template_id, ctx.user_id)

            if runtime_template:
                config_sources["runtime_template"] = {
                    "id": runtime_template.id,
                    "name": runtime_template.name,
                    "will_be_bound": config_override.bind_template,
                }

        if recording.template_id:
            bound_template = await template_repo.find_by_id(recording.template_id, ctx.user_id)

            if bound_template:
                config_sources["bound_template"] = {
                    "id": bound_template.id,
                    "name": bound_template.name,
                }

    if config_override:
        has_overrides = any(
            [
                config_override.processing_config,
                config_override.metadata_config,
                config_override.output_config,
            ]
        )
        config_sources["has_manual_overrides"] = has_overrides

    return DryRunResponse(
        dry_run=True,
        recording_id=recording_id,
        current_status=recording.status,
        steps=steps,
        config_sources=config_sources if config_sources else None,
    )


async def _execute_dry_run_bulk(
    recording_ids: list[int] | None,
    filters: RecordingFiltersSchema | None,
    limit: int,
    ctx: ServiceContext,
) -> BulkProcessDryRunResponse:
    """Dry-run for bulk process: shows which recordings will be processed and which skipped."""
    resolved_ids = await _resolve_recording_ids(recording_ids, filters, limit, ctx)

    recording_repo = RecordingRepository(ctx.session)
    recordings_info = []
    skipped_count = 0

    recordings_map = await recording_repo.get_by_ids(resolved_ids, ctx.user_id)

    for rec_id in resolved_ids:
        recording = recordings_map.get(rec_id)

        if not recording:
            recordings_info.append(
                {"recording_id": rec_id, "will_be_processed": False, "skip_reason": "Recording not found or no access"}
            )
            skipped_count += 1
            continue

        if recording.blank_record:
            recordings_info.append(
                {
                    "recording_id": rec_id,
                    "will_be_processed": False,
                    "skip_reason": "Blank record (too short or too small)",
                }
            )
            skipped_count += 1
            continue

        recordings_info.append(
            {
                "recording_id": rec_id,
                "will_be_processed": True,
                "display_name": recording.display_name,
                "current_status": recording.status,
                "start_time": recording.start_time.isoformat() if recording.start_time else None,
            }
        )

    return BulkProcessDryRunResponse(
        matched_count=len(resolved_ids) - skipped_count,
        skipped_count=skipped_count,
        total=len(resolved_ids),
        recordings=recordings_info,
    )
