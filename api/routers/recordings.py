"""Recording endpoints with multi-tenancy support"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, Field

from api.core.context import ServiceContext
from api.core.dependencies import get_service_context
from api.repositories.config_repos import UserConfigRepository
from api.repositories.recording_repos import RecordingRepository
from api.schemas.recording.filters import RecordingFilters as RecordingFiltersSchema
from api.schemas.recording.operations import (
    BulkProcessDryRunResponse,
    ConfigSaveResponse,
    DryRunResponse,
    RecordingBulkOperationResponse,
    RecordingOperationResponse,
    ResetRecordingResponse,
    RetryUploadResponse,
)
from api.schemas.recording.request import (
    BulkDeleteRequest,
    BulkDownloadRequest,
    BulkRunRequest,
    BulkSubtitlesRequest,
    BulkTopicsRequest,
    BulkTranscribeRequest,
    BulkTrimRequest,
    BulkUploadRequest,
)
from api.schemas.recording.response import (
    OutputTargetResponse,
    PresetInfo,
    ProcessingStageResponse,
    RecordingListItem,
    RecordingListResponse,
    RecordingResponse,
    SourceInfo,
    SourceResponse,
    UploadInfo,
)
from logger import get_logger
from models import ProcessingStatus
from models.recording import TargetStatus

router = APIRouter(prefix="/api/v1/recordings", tags=["Recordings"])
logger = get_logger()


# ============================================================================
# Request/Response Models (used only in this router - KISS)
# ============================================================================


class DetailedRecordingResponse(RecordingResponse):
    """Extended response model with detailed information."""

    videos: dict | None = None
    audio: dict | None = None
    transcription: dict | None = None
    topics: dict | None = None
    subtitles: dict | None = None
    processing_stages_detailed: list[dict] | None = None
    uploads: dict | None = None


class TrimVideoRequest(BaseModel):
    """Request for video trimming (FFmpeg - removing silence)."""

    silence_threshold: float = -40.0
    min_silence_duration: float = 2.0
    padding_before: float = 5.0
    padding_after: float = 5.0


class ConfigOverrideRequest(BaseModel):
    """
    Flexible request for override configuration in process endpoint.

    Supports any fields from template config for override.
    Runtime template usage: specify template_id to use template config without permanent binding.
    """

    template_id: int | None = Field(None, description="Runtime template to use (not saved to DB by default)")
    bind_template: bool = Field(False, description="If true, save template_id to recording and set is_mapped=true")
    processing_config: dict | None = Field(None, description="Override processing config")
    metadata_config: dict | None = Field(None, description="Override metadata config")
    output_config: dict | None = Field(None, description="Override output config")

    class Config:
        json_schema_extra = {
            "example": {
                "template_id": 5,
                "bind_template": False,
                "processing_config": {
                    "transcription": {
                        "enable_transcription": True,
                        "language": "ru",
                        "granularity": "short",
                        "enable_topics": True,
                    }
                },
                "metadata_config": {
                    "title_template": "{themes}",
                    "description_template": "{summary}\\n\\n{topics}",
                    "youtube": {
                        "playlist_id": "PLxxx",
                        "privacy": "unlisted",
                        "thumbnail_name": "python_base.png",
                        "category_id": "27",
                        "tags": ["AI", "ML", "lecture"],
                    },
                    "vk": {
                        "album_id": "123456",
                        "group_id": 123456,
                        "thumbnail_name": "applied_python.png",
                        "privacy_view": 0,
                        "privacy_comment": 0,
                        "wallpost": False,
                    },
                },
                "output_config": {
                    "preset_ids": [10],
                    "auto_upload": True,
                    "upload_captions": True,
                },
            }
        }


def _build_override_from_flexible(config: ConfigOverrideRequest) -> dict:
    """
    Convert ConfigOverrideRequest to manual_override dictionary.

    Returns a dict that will be merged with resolved config hierarchy.
    """
    override = {}

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
# Bulk Operations Helper Functions (DRY)
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

    raise ValueError("Either recording_ids or filters must be specified")


async def _query_recordings_by_filters(
    filters: RecordingFiltersSchema,
    limit: int,
    ctx: ServiceContext,
) -> list[int]:
    """Build query by filters and return list of recording IDs."""
    from sqlalchemy import select

    from database.models import RecordingModel

    query = select(RecordingModel.id).where(RecordingModel.user_id == ctx.user_id)

    if not filters.include_deleted:
        query = query.where(RecordingModel.deleted == False)  # noqa: E712

    if filters.template_id:
        query = query.where(RecordingModel.template_id == filters.template_id)

    if filters.source_id:
        query = query.where(RecordingModel.input_source_id == filters.source_id)

    if filters.status:
        has_failed = "FAILED" in filters.status
        other_statuses = [s for s in filters.status if s != "FAILED"]

        if has_failed and other_statuses:
            from sqlalchemy import or_

            query = query.where(
                or_(
                    RecordingModel.status.in_(other_statuses),
                    RecordingModel.failed == True,  # noqa: E712
                )
            )
        elif has_failed:
            query = query.where(RecordingModel.failed == True)  # noqa: E712
        else:
            query = query.where(RecordingModel.status.in_(other_statuses))

    if filters.is_mapped is not None:
        query = query.where(RecordingModel.is_mapped == filters.is_mapped)

    if filters.failed is not None:
        query = query.where(RecordingModel.failed == filters.failed)

    if filters.exclude_blank:
        query = query.where(~RecordingModel.blank_record)

    if filters.search:
        query = query.where(RecordingModel.display_name.ilike(f"%{filters.search}%"))

    # Date filters
    if filters.from_date:
        from utils.date_utils import InvalidDateFormatError, parse_from_date_to_datetime

        try:
            from_dt = parse_from_date_to_datetime(filters.from_date)
        except InvalidDateFormatError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
        query = query.where(RecordingModel.start_time >= from_dt)

    if filters.to_date:
        from utils.date_utils import InvalidDateFormatError, parse_to_date_to_datetime

        try:
            to_dt = parse_to_date_to_datetime(filters.to_date)
        except InvalidDateFormatError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
        query = query.where(RecordingModel.start_time <= to_dt)

    order_column = getattr(RecordingModel, filters.order_by, RecordingModel.created_at)
    if filters.order == "desc":
        query = query.order_by(order_column.desc())
    else:
        query = query.order_by(order_column.asc())

    query = query.limit(limit)

    result = await ctx.session.execute(query)
    return [row[0] for row in result.all()]


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
    for output in outputs:
        platform = output.target_type.value.lower()
        url = None
        if output.target_meta:
            url = (
                output.target_meta.get("video_url")
                or output.target_meta.get("target_link")
                or output.target_meta.get("url")
            )
        uploads[platform] = UploadInfo(
            status=output.status.value.lower(),
            url=url,
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
            completed_at=stage.completed_at,
        )
        for stage in stages
    ]


async def _execute_dry_run_single(
    recording_id: int,
    config_override: ConfigOverrideRequest | None,
    ctx: ServiceContext,
) -> dict:
    """Dry-run for single process: shows execution plan without running."""
    from api.repositories.template_repos import OutputPresetRepository
    from api.services.config_utils import resolve_full_config

    recording_repo = RecordingRepository(ctx.session)
    recording = await recording_repo.get_by_id(recording_id, ctx.user_id)

    if not recording:
        raise HTTPException(404, "Recording not found")

    manual_override = _build_override_from_flexible(config_override) if config_override else None

    full_config, output_config, recording = await resolve_full_config(
        ctx.session,
        recording_id,
        ctx.user_id,
        manual_override=manual_override,
        include_output_config=True,
    )

    steps = []

    if not recording.local_video_path:
        steps.append({"name": "download", "enabled": True})
    else:
        steps.append({"name": "download", "enabled": False, "skip_reason": "Already downloaded"})

    if full_config.get("trimming", {}).get("enable_trimming", True):
        steps.append({"name": "trim", "enabled": True})
    else:
        steps.append({"name": "trim", "enabled": False, "skip_reason": "Disabled in config"})

    if full_config.get("transcription", {}).get("enable_transcription", True):
        steps.append({"name": "transcribe", "enabled": True})
    else:
        steps.append({"name": "transcribe", "enabled": False})

    steps.append({"name": "topics", "enabled": True})

    auto_upload = output_config.get("auto_upload", False)
    if auto_upload:
        platforms = []
        preset_ids = output_config.get("preset_ids", [])

        if preset_ids:
            preset_repo = OutputPresetRepository(ctx.session)
            presets = await preset_repo.find_by_ids(preset_ids, ctx.user_id)
            platforms = [preset.platform for preset in presets if preset.is_active]

        steps.append({"name": "upload", "enabled": True, "platforms": platforms})
    else:
        steps.append({"name": "upload", "enabled": False, "skip_reason": "auto_upload is false"})

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
                "start_time": recording.start_time.isoformat(),
            }
        )

    return BulkProcessDryRunResponse(
        matched_count=len(resolved_ids) - skipped_count,
        skipped_count=skipped_count,
        total=len(resolved_ids),
        recordings=recordings_info,
    )


# ============================================================================
# CRUD Endpoints
# ============================================================================


@router.get("", response_model=RecordingListResponse)
async def list_recordings(
    search: str | None = Query(None, description="Search substring in display_name (case-insensitive)"),
    template_id: int | None = Query(None, description="Filter by template ID"),
    source_id: int | None = Query(None, description="Filter by source ID"),
    status_filter: list[str] = Query(
        default=[], description="Filter by statuses (repeat param for multiple: ?status=A&status=B)", alias="status"
    ),
    failed: bool | None = Query(None, description="Only failed recordings"),
    is_mapped: bool | None = Query(None, description="Filter by is_mapped (true/false/null=all)"),
    include_blank: bool = Query(False, description="Include blank records (short/small)"),
    include_deleted: bool = Query(False, description="Include deleted recordings"),
    from_date: str | None = Query(None, description="Filter: start_time >= from_date (YYYY-MM-DD)"),
    to_date: str | None = Query(None, description="Filter: start_time <= to_date (YYYY-MM-DD)"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    ctx: ServiceContext = Depends(get_service_context),
):
    """Get paginated list of recordings with filtering and search."""
    recording_repo = RecordingRepository(ctx.session)
    recordings = await recording_repo.list_by_user(ctx.user_id, include_deleted=include_deleted)

    if template_id is not None:
        recordings = [r for r in recordings if r.template_id == template_id]

    if source_id is not None:
        recordings = [r for r in recordings if r.input_source_id == source_id]

    if status_filter:
        has_failed = "FAILED" in status_filter
        other_statuses = [s for s in status_filter if s != "FAILED"]

        if has_failed and other_statuses:
            recordings = [r for r in recordings if r.status.value in other_statuses or r.failed]
        elif has_failed:
            recordings = [r for r in recordings if r.failed]
        else:
            recordings = [r for r in recordings if r.status.value in other_statuses]

    if failed is not None:
        recordings = [r for r in recordings if r.failed == failed]

    if is_mapped is not None:
        recordings = [r for r in recordings if r.is_mapped == is_mapped]

    if not include_blank:
        recordings = [r for r in recordings if not r.blank_record]

    if from_date:
        from utils.date_utils import InvalidDateFormatError, parse_from_date_to_datetime

        try:
            from_dt = parse_from_date_to_datetime(from_date)
        except InvalidDateFormatError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
        recordings = [r for r in recordings if r.start_time >= from_dt]

    if to_date:
        from utils.date_utils import InvalidDateFormatError, parse_to_date_to_datetime

        try:
            to_dt = parse_to_date_to_datetime(to_date)
        except InvalidDateFormatError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
        recordings = [r for r in recordings if r.start_time <= to_dt]

    if search:
        search_lower = search.lower()
        recordings = [r for r in recordings if search_lower in r.display_name.lower()]

    total = len(recordings)
    start = (page - 1) * per_page
    end = start + per_page
    paginated_recordings = recordings[start:end]
    total_pages = (total + per_page - 1) // per_page if total > 0 else 1

    items = []
    for r in paginated_recordings:
        items.append(
            RecordingListItem(
                id=r.id,
                display_name=r.display_name,
                start_time=r.start_time,
                duration=r.duration,
                status=r.status,
                failed=r.failed,
                failed_at_stage=r.failed_at_stage,
                is_mapped=r.is_mapped,
                template_id=r.template_id,
                template_name=r.template.name if r.template else None,
                source=_build_source_info(r),
                uploads=_build_uploads_dict(r.outputs),
                processing_stages=_build_processing_stages(r.processing_stages),
                deleted=r.deleted,
                deleted_at=r.deleted_at,
                delete_state=r.delete_state,
                deletion_reason=r.deletion_reason,
                soft_deleted_at=r.soft_deleted_at,
                hard_delete_at=r.hard_delete_at,
                expire_at=r.expire_at,
                created_at=r.created_at,
                updated_at=r.updated_at,
            )
        )

    return RecordingListResponse(
        total=total,
        page=page,
        per_page=per_page,
        total_pages=total_pages,
        items=items,
    )


@router.get("/{recording_id}")
async def get_recording(
    recording_id: int,
    detailed: bool = Query(False, description="Include detailed information (files, transcription, topics, uploads)"),
    ctx: ServiceContext = Depends(get_service_context),
) -> RecordingListItem | DetailedRecordingResponse:
    """Get recording by ID with optional detailed information."""
    recording_repo = RecordingRepository(ctx.session)
    recording = await recording_repo.get_by_id(recording_id, ctx.user_id, include_deleted=True)

    if not recording:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Recording {recording_id} not found or you don't have access",
        )

    if not detailed:
        return RecordingListItem(
            id=recording.id,
            display_name=recording.display_name,
            start_time=recording.start_time,
            duration=recording.duration,
            status=recording.status,
            failed=recording.failed,
            failed_at_stage=recording.failed_at_stage,
            is_mapped=recording.is_mapped,
            template_id=recording.template_id,
            template_name=recording.template.name if recording.template else None,
            source=_build_source_info(recording),
            uploads=_build_uploads_dict(recording.outputs),
            processing_stages=_build_processing_stages(recording.processing_stages),
            deleted=recording.deleted,
            deleted_at=recording.deleted_at,
            delete_state=recording.delete_state,
            deletion_reason=recording.deletion_reason,
            soft_deleted_at=recording.soft_deleted_at,
            hard_delete_at=recording.hard_delete_at,
            expire_at=recording.expire_at,
            created_at=recording.created_at,
            updated_at=recording.updated_at,
        )

    # Detailed information
    from transcription_module.manager import get_transcription_manager

    transcription_manager = get_transcription_manager()

    # Base information (common fields)
    base_data = {
        "id": recording.id,
        "display_name": recording.display_name,
        "start_time": recording.start_time,
        "duration": recording.duration,
        "status": recording.status,
        "is_mapped": recording.is_mapped,
        "blank_record": recording.blank_record,
        "processing_preferences": recording.processing_preferences,
        "source": (
            SourceResponse(
                source_type=recording.source.source_type,
                source_key=recording.source.source_key,
                metadata=recording.source.meta or {},
            )
            if recording.source
            else None
        ),
        "outputs": [
            OutputTargetResponse(
                id=output.id,
                target_type=output.target_type,
                status=output.status,
                target_meta=output.target_meta or {},
                uploaded_at=output.uploaded_at,
                failed=output.failed,
                failed_at=output.failed_at,
                failed_reason=output.failed_reason,
                retry_count=output.retry_count,
                preset=(PresetInfo(id=output.preset.id, name=output.preset.name) if output.preset else None),
            )
            for output in recording.outputs
        ],
        "processing_stages": [
            ProcessingStageResponse(
                stage_type=stage.stage_type,
                status=stage.status,
                failed=stage.failed,
                failed_at=stage.failed_at,
                failed_reason=stage.failed_reason,
                retry_count=stage.retry_count,
                completed_at=stage.completed_at,
            )
            for stage in recording.processing_stages
        ],
        "failed": recording.failed,
        "failed_at": recording.failed_at,
        "failed_reason": recording.failed_reason,
        "failed_at_stage": recording.failed_at_stage,
        "video_file_size": recording.video_file_size,
        "deleted": recording.deleted,
        "deleted_at": recording.deleted_at,
        "delete_state": recording.delete_state,
        "deletion_reason": recording.deletion_reason,
        "soft_deleted_at": recording.soft_deleted_at,
        "hard_delete_at": recording.hard_delete_at,
        "expire_at": recording.expire_at,
        "created_at": recording.created_at,
        "updated_at": recording.updated_at,
    }

    # Video files
    videos = {}
    if recording.local_video_path:
        path = Path(recording.local_video_path)
        videos["original"] = {
            "path": str(path),
            "size_mb": round(path.stat().st_size / (1024 * 1024), 2) if path.exists() else None,
            "exists": path.exists(),
        }
    if recording.processed_video_path:
        path = Path(recording.processed_video_path)
        videos["processed"] = {
            "path": str(path),
            "size_mb": round(path.stat().st_size / (1024 * 1024), 2) if path.exists() else None,
            "exists": path.exists(),
        }

    # Audio files
    audio_info = {}
    if recording.processed_audio_path:
        audio_path = Path(recording.processed_audio_path)
        if audio_path.exists():
            audio_info = {
                "path": str(audio_path),
                "size_mb": round(audio_path.stat().st_size / (1024 * 1024), 2),
                "exists": True,
            }
        else:
            audio_info = {
                "path": str(audio_path),
                "exists": False,
                "size_mb": None,
            }

    # Get user_slug for transcription paths
    user_slug = recording.owner.user_slug

    # Transcription (hide _metadata and model from user)
    transcription_data = None
    if transcription_manager.has_master(recording_id, user_slug):
        try:
            master = transcription_manager.load_master(recording_id, user_slug)
            transcription_data = {
                "exists": True,
                "created_at": master.get("created_at"),
                "language": master.get("language"),
                # Hide model from user (exists in _metadata for admin)
                "stats": master.get("stats"),
                "files": {
                    "master": str(transcription_manager.get_dir(recording_id, user_slug) / "master.json"),
                    "segments_txt": str(
                        transcription_manager.get_dir(recording_id, user_slug) / "cache" / "segments.txt"
                    ),
                    "words_txt": str(transcription_manager.get_dir(recording_id, user_slug) / "cache" / "words.txt"),
                },
            }
        except Exception as e:
            logger.warning(f"Failed to load transcription for recording {recording_id}: {e}")
            transcription_data = {"exists": False}
    else:
        transcription_data = {"exists": False}

    # Topics (all versions) - hide _metadata from user
    topics_data = None
    if transcription_manager.has_topics(recording_id, user_slug):
        try:
            topics_file = transcription_manager.load_topics(recording_id, user_slug)

            # Clean versions from administrative metadata
            versions_clean = []
            for version in topics_file.get("versions", []):
                version_clean = {k: v for k, v in version.items() if k != "_metadata"}
                versions_clean.append(version_clean)

            topics_data = {
                "exists": True,
                "active_version": topics_file.get("active_version"),
                "versions": versions_clean,
            }
        except Exception as e:
            logger.warning(f"Failed to load topics for recording {recording_id}: {e}")
            topics_data = {"exists": False}
    else:
        topics_data = {"exists": False}

    # Subtitles
    subtitles = {}
    cache_dir = transcription_manager.get_dir(recording_id, user_slug) / "cache"
    for fmt in ["srt", "vtt"]:
        subtitle_path = cache_dir / f"subtitles.{fmt}"
        subtitles[fmt] = {
            "path": str(subtitle_path) if subtitle_path.exists() else None,
            "exists": subtitle_path.exists(),
            "size_kb": round(subtitle_path.stat().st_size / 1024, 2) if subtitle_path.exists() else None,
        }

    # Processing stages detailed (with metadata and timestamps)
    processing_stages_detailed = None
    if hasattr(recording, "processing_stages") and recording.processing_stages:
        processing_stages_detailed = [
            {
                "type": stage.stage_type.value if hasattr(stage.stage_type, "value") else str(stage.stage_type),
                "status": stage.status.value if hasattr(stage.status, "value") else str(stage.status),
                "created_at": stage.created_at.isoformat() if stage.created_at else None,
                "completed_at": stage.completed_at.isoformat() if stage.completed_at else None,
                "meta": stage.stage_meta,
            }
            for stage in recording.processing_stages
        ]

    # Upload to platforms
    uploads = {}
    if hasattr(recording, "outputs") and recording.outputs:
        for target in recording.outputs:
            platform = target.target_type.value if hasattr(target.target_type, "value") else str(target.target_type)

            # Base information
            upload_info = {
                "status": target.status.value if hasattr(target.status, "value") else str(target.status),
                "url": target.target_meta.get("video_url") or target.target_meta.get("target_link")
                if target.target_meta
                else None,
                "video_id": target.target_meta.get("video_id") if target.target_meta else None,
                "uploaded_at": target.uploaded_at.isoformat() if target.uploaded_at else None,
                "failed": target.failed,
                "retry_count": target.retry_count,
            }

            # Add information about preset if exists
            if target.preset:
                upload_info["preset"] = {
                    "id": target.preset.id,
                    "name": target.preset.name,
                }

            uploads[platform] = upload_info

    # Create response model
    return DetailedRecordingResponse(
        **base_data,
        videos=videos if videos else None,
        audio=audio_info if audio_info else None,
        transcription=transcription_data,
        topics=topics_data,
        subtitles=subtitles,
        processing_stages_detailed=processing_stages_detailed,
        uploads=uploads if uploads else None,
    )


@router.post("", response_model=RecordingOperationResponse)
async def add_local_recording(
    file: UploadFile = File(...),
    display_name: str = Query(..., description="Recording name"),
    ctx: ServiceContext = Depends(get_service_context),
) -> RecordingOperationResponse:
    """Upload and create local video recording."""
    import shutil

    from file_storage.path_builder import StoragePathBuilder

    storage_builder = StoragePathBuilder()
    filename = file.filename or "uploaded_video.mp4"

    # TODO(S3): Replace with backend.save() when S3 support added
    # For now: direct file operations (LOCAL only)

    # Save to temp directory first
    temp_path = storage_builder.create_temp_file(suffix=".mp4")

    try:
        total_size = 0
        with temp_path.open("wb") as f:
            while chunk := await file.read(1024 * 1024):
                f.write(chunk)
                total_size += len(chunk)

        if not temp_path.exists():
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to save uploaded file",
            )

        actual_size = temp_path.stat().st_size
        if actual_size != total_size:
            logger.warning(f"File size mismatch: expected {total_size}, got {actual_size}")

        # Get user to access user_slug
        from sqlalchemy import select

        from database.auth_models import UserModel

        user_result = await ctx.session.execute(select(UserModel).where(UserModel.id == ctx.user_id))
        user = user_result.scalar_one()

        # Create recording in DB
        recording_repo = RecordingRepository(ctx.session)

        from models.recording import SourceType

        # Generate unique source key for local recording
        source_key = f"local_{ctx.user_id}_{datetime.now().timestamp()}"

        # Get user config for retention settings (merged with defaults)
        user_config_repo = UserConfigRepository(ctx.session)
        user_config = await user_config_repo.get_effective_config(ctx.user_id)

        created_recording = await recording_repo.create(
            user_id=ctx.user_id,
            input_source_id=None,
            display_name=display_name,
            start_time=datetime.now(),
            duration=0,
            source_type=SourceType.LOCAL_FILE,
            source_key=source_key,
            source_metadata={"uploaded_via_api": True, "original_filename": filename},
            user_config=user_config,
            status=ProcessingStatus.DOWNLOADED,
            local_video_path="",  # Will update after moving file
            video_file_size=actual_size,
        )

        await ctx.session.flush()  # Get recording.id

        final_path = storage_builder.recording_source(user.user_slug, created_recording.id)
        final_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(temp_path), str(final_path))

        created_recording.local_video_path = str(final_path)
        await ctx.session.commit()

        return {
            "success": True,
            "recording_id": created_recording.id,
            "display_name": created_recording.display_name,
            "local_video_path": str(final_path),
        }

    except Exception as e:
        logger.error(f"Failed to upload file: {e}", exc_info=True)
        if temp_path.exists():
            temp_path.unlink()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to upload file: {e!s}",
        )


# ============================================================================
# Metadata Endpoints
# ============================================================================


class StatusInfo(BaseModel):
    """Information about processing status."""

    value: str
    label: str
    description: str


@router.get("/statuses", response_model=list[StatusInfo])
async def get_available_statuses():
    """
    Get list of all available processing statuses for filtering.

    This endpoint provides a list of statuses that can be used in the `status` filter
    parameter for GET /recordings and bulk operations.

    Returns:
        List of status info with value, label and description
    """
    return [
        StatusInfo(
            value="PENDING_SOURCE",
            label="Pending Source",
            description="Source still processing on platform",
        ),
        StatusInfo(
            value="INITIALIZED",
            label="Initialized",
            description="Synced from source, awaiting processing",
        ),
        StatusInfo(
            value="DOWNLOADING",
            label="Downloading",
            description="In progress of downloading",
        ),
        StatusInfo(
            value="DOWNLOADED",
            label="Downloaded",
            description="Downloaded from source",
        ),
        StatusInfo(
            value="PROCESSING",
            label="Processing",
            description="In progress of video processing",
        ),
        StatusInfo(
            value="PROCESSED",
            label="Processed",
            description="All processing stages completed or skipped",
        ),
        StatusInfo(
            value="UPLOADING",
            label="Uploading",
            description="In progress of uploading to platforms",
        ),
        StatusInfo(
            value="UPLOADED",
            label="Uploaded",
            description="Uploaded to platforms",
        ),
        StatusInfo(
            value="READY",
            label="Ready",
            description="Ready (all stages completed)",
        ),
        StatusInfo(
            value="SKIPPED",
            label="Skipped",
            description="Skipped (blank or too short)",
        ),
        StatusInfo(
            value="EXPIRED",
            label="Expired",
            description="Expired (retention period ended)",
        ),
        StatusInfo(
            value="FAILED",
            label="Failed",
            description="Failed (pseudo-status: recording.failed = true)",
        ),
    ]


# ============================================================================
# Processing Endpoints
# ============================================================================


@router.post("/{recording_id}/download", response_model=RecordingOperationResponse)
async def download_recording(
    recording_id: int,
    force: bool = Query(False, description="Re-download if already downloaded"),
    ctx: ServiceContext = Depends(get_service_context),
) -> RecordingOperationResponse:
    """Download recording from Zoom (async task)."""
    from api.helpers.status_manager import should_allow_download
    from api.tasks.processing import download_recording_task

    recording_repo = RecordingRepository(ctx.session)
    recording = await recording_repo.get_by_id(recording_id, ctx.user_id)

    if not recording:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Recording {recording_id} not found or you don't have access",
        )

    # Check if we can download
    if not should_allow_download(recording):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Download not allowed for recording with status {recording.status}.",
        )

    # Check if we have download_url in source metadata
    download_url = None
    if recording.source and recording.source.meta:
        download_url = recording.source.meta.get("download_url")

    if not download_url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No download URL available for this recording. Please sync from Zoom first.",
        )

    # Check if not already downloaded
    if not force and recording.status == ProcessingStatus.DOWNLOADED and recording.local_video_path:
        if Path(recording.local_video_path).exists():
            return {
                "success": True,
                "message": "Recording already downloaded",
                "recording_id": recording_id,
                "local_video_path": recording.local_video_path,
                "task_id": None,
            }

    # Start async task
    task = download_recording_task.delay(
        recording_id=recording_id,
        user_id=ctx.user_id,
        force=force,
    )

    logger.info(f"Download task {task.id} created for recording {recording_id}, user {ctx.user_id}")

    return {
        "success": True,
        "task_id": task.id,
        "recording_id": recording_id,
        "status": "queued",
        "message": "Download task has been queued",
        "check_status_url": f"/api/v1/tasks/{task.id}",
    }


@router.post("/{recording_id}/trim", response_model=RecordingOperationResponse)
async def trim_recording(
    recording_id: int,
    config: TrimVideoRequest = TrimVideoRequest(),
    ctx: ServiceContext = Depends(get_service_context),
) -> RecordingOperationResponse:
    """Trim video using FFmpeg to remove silence (async task)."""
    from api.tasks.processing import trim_video_task

    recording_repo = RecordingRepository(ctx.session)
    recording = await recording_repo.get_by_id(recording_id, ctx.user_id)

    if not recording:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Recording {recording_id} not found or you don't have access",
        )

    # Check if we can process (trim allowed for PROCESSED status)
    if recording.status not in [ProcessingStatus.PROCESSED, ProcessingStatus.DOWNLOADED]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Trim not allowed for recording with status {recording.status}. Recording must be downloaded or processed first.",
        )

    # Check if original video is present
    if not recording.local_video_path:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No video file available. Please download the recording first.",
        )

    if not Path(recording.local_video_path).exists():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Video file not found at path: {recording.local_video_path}",
        )

    # Build manual override from config
    manual_override = {
        "processing": {
            "silence_threshold": config.silence_threshold,
            "min_silence_duration": config.min_silence_duration,
            "padding_before": config.padding_before,
            "padding_after": config.padding_after,
        }
    }

    # Start async task
    task = trim_video_task.delay(
        recording_id=recording_id,
        user_id=ctx.user_id,
        manual_override=manual_override,
    )

    logger.info(f"Trim task {task.id} created for recording {recording_id}, user {ctx.user_id}")

    return {
        "success": True,
        "task_id": task.id,
        "recording_id": recording_id,
        "status": "queued",
        "message": "Processing task has been queued",
        "check_status_url": f"/api/v1/tasks/{task.id}",
    }


@router.post("/bulk/run")
async def bulk_run_recordings(
    data: BulkRunRequest,
    dry_run: bool = Query(False, description="Dry-run: show which recordings will be run"),
    ctx: ServiceContext = Depends(get_service_context),
) -> RecordingBulkOperationResponse | BulkProcessDryRunResponse:
    """Bulk run full pipeline on multiple recordings (async tasks)."""

    if dry_run:
        return await _execute_dry_run_bulk(data.recording_ids, data.filters, data.limit, ctx)

    from api.tasks.processing import run_recording_task

    # Resolve recording IDs
    recording_ids = await _resolve_recording_ids(data.recording_ids, data.filters, data.limit, ctx)

    recording_repo = RecordingRepository(ctx.session)
    tasks = []

    # Build manual override from config_override
    manual_override = {}
    if data.template_id:
        manual_override["runtime_template_id"] = data.template_id
    if data.processing_config:
        manual_override["processing_config"] = data.processing_config
    if data.metadata_config:
        manual_override["metadata_config"] = data.metadata_config
    if data.output_config:
        manual_override["output_config"] = data.output_config

    # Validate template if bind_template is requested
    if data.template_id and data.bind_template:
        from api.repositories.template_repos import RecordingTemplateRepository

        template_repo = RecordingTemplateRepository(ctx.session)
        template = await template_repo.find_by_id(data.template_id, ctx.user_id)

        if not template:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Template {data.template_id} not found")

    recordings_map = await recording_repo.get_by_ids(recording_ids, ctx.user_id)

    for recording_id in recording_ids:
        try:
            recording = recordings_map.get(recording_id)

            if not recording:
                tasks.append(
                    {
                        "recording_id": recording_id,
                        "status": "error",
                        "error": "Recording not found or no access",
                        "task_id": None,
                    }
                )
                continue

            # Skip blank records
            if recording.blank_record:
                tasks.append(
                    {
                        "recording_id": recording_id,
                        "status": "skipped",
                        "error": "Blank record (too short or too small)",
                        "task_id": None,
                    }
                )
                continue

            # Start task for this recording (template-driven + manual override)
            task = run_recording_task.delay(
                recording_id=recording_id,
                user_id=ctx.user_id,
                manual_override=manual_override if manual_override else None,
            )

            # Only bind template after task is successfully created
            if data.template_id and data.bind_template:
                recording.template_id = data.template_id
                recording.is_mapped = True

                # Update status if currently SKIPPED
                if recording.status == ProcessingStatus.SKIPPED:
                    recording.status = ProcessingStatus.INITIALIZED  # type: ignore[assignment]

            tasks.append(
                {
                    "recording_id": recording_id,
                    "status": "queued",
                    "task_id": task.id,
                    "check_status_url": f"/api/v1/tasks/{task.id}",
                }
            )

        except Exception as e:
            logger.error(f"Failed to create task for recording {recording_id}: {e}")
            tasks.append(
                {
                    "recording_id": recording_id,
                    "status": "error",
                    "error": str(e),
                    "task_id": None,
                }
            )

    queued_count = len([t for t in tasks if t["status"] == "queued"])
    skipped_count = len([t for t in tasks if t["status"] == "skipped"])

    # Commit template bindings if any
    if data.template_id and data.bind_template:
        await ctx.session.commit()
        logger.info(f"Bound template {data.template_id} to {queued_count} recordings")

    return RecordingBulkOperationResponse(
        total=len(recording_ids),
        queued_count=queued_count,
        skipped_count=skipped_count,
        tasks=tasks,
    )


@router.post("/{recording_id}/run", response_model=RecordingOperationResponse | DryRunResponse)
async def run_recording(
    recording_id: int,
    config: ConfigOverrideRequest = ConfigOverrideRequest(),
    dry_run: bool = Query(False, description="Dry-run: show what will be done without actual execution"),
    ctx: ServiceContext = Depends(get_service_context),
) -> RecordingOperationResponse | DryRunResponse:
    """Run full pipeline: download → trim → transcribe → topics → upload (async task)."""
    if dry_run:
        return await _execute_dry_run_single(recording_id, config, ctx)

    from api.tasks.processing import run_recording_task

    recording_repo = RecordingRepository(ctx.session)
    recording = await recording_repo.get_by_id(recording_id, ctx.user_id)

    if not recording:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Recording {recording_id} not found or you don't have access",
        )

    # Validate template if binding is requested
    if config.template_id and config.bind_template:
        from api.repositories.template_repos import RecordingTemplateRepository

        template_repo = RecordingTemplateRepository(ctx.session)
        template = await template_repo.find_by_id(config.template_id, ctx.user_id)

        if not template:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=f"Template {config.template_id} not found"
            )

    manual_override = _build_override_from_flexible(config)

    # Start task first to ensure it can be created
    task = run_recording_task.delay(
        recording_id=recording_id,
        user_id=ctx.user_id,
        manual_override=manual_override,
    )

    # Only bind template after task is successfully created
    if config.template_id and config.bind_template:
        recording.template_id = config.template_id
        recording.is_mapped = True

        # Update status if currently SKIPPED
        if recording.status == ProcessingStatus.SKIPPED:
            recording.status = ProcessingStatus.INITIALIZED  # type: ignore[assignment]

        await ctx.session.commit()

        logger.info(f"Bound template (id={config.template_id}) to recording {recording_id}")

    logger.info(
        f"Run recording task {task.id} created for recording {recording_id}, user {ctx.user_id}, "
        f"overrides: {list(manual_override.keys())}"
    )

    return {
        "success": True,
        "task_id": task.id,
        "recording_id": recording_id,
        "status": "queued",
        "message": "Run task has been queued",
        "check_status_url": f"/api/v1/tasks/{task.id}",
        "config_overrides": manual_override if manual_override else None,
    }


@router.post("/{recording_id}/transcribe", response_model=RecordingOperationResponse)
async def transcribe_recording(
    recording_id: int,
    use_batch_api: bool = Query(False, description="Use Batch API (cheaper, but requires polling)"),
    ctx: ServiceContext = Depends(get_service_context),
) -> RecordingOperationResponse:
    """Transcribe recording using Fireworks API (async task). Use /topics endpoint for topic extraction."""
    from api.helpers.status_manager import should_allow_transcription
    from api.tasks.processing import batch_transcribe_recording_task, transcribe_recording_task

    # Get recording from DB
    recording_repo = RecordingRepository(ctx.session)
    recording = await recording_repo.get_by_id(recording_id, ctx.user_id)

    if not recording:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Recording {recording_id} not found or you don't have access"
        )

    # Check if transcription can be started
    if not should_allow_transcription(recording):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Transcription cannot be started. Current status: {recording.status}. "
            f"Transcription is already completed or in progress.",
        )

    # Check if file for processing exists
    if not recording.processed_video_path and not recording.local_video_path:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No video file available for transcription. Please download the recording first.",
        )

    audio_path = recording.processed_video_path or recording.local_video_path

    # Check if file exists
    if not Path(audio_path).exists():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"Video file not found at path: {audio_path}"
        )

    # Select mode: Batch API or synchronous API
    if use_batch_api:
        # Batch API mode: submit batch job, then polling
        from api.services.config_utils import resolve_full_config
        from fireworks_module import FireworksConfig, FireworksTranscriptionService

        fireworks_config = FireworksConfig.from_file("config/fireworks_creds.json")

        # Check if account_id exists
        if not fireworks_config.account_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Batch API is not available: account_id is not configured in config/fireworks_creds.json. "
                "Add account_id from Fireworks dashboard or use use_batch_api=false.",
            )

        fireworks_service = FireworksTranscriptionService(fireworks_config)

        # Resolve config from template hierarchy to get language and prompt
        full_config, _ = await resolve_full_config(ctx.session, recording_id, ctx.user_id, None)
        transcription_config = full_config.get("transcription", {})
        language = transcription_config.get("language", "ru")
        user_prompt = transcription_config.get("prompt", "")

        # Compose prompt with recording topic
        fireworks_prompt = fireworks_service.compose_fireworks_prompt(user_prompt, recording.display_name)

        # Submit batch job
        try:
            batch_result = await fireworks_service.submit_batch_transcription(
                audio_path=audio_path,
                language=language,
                prompt=fireworks_prompt,
            )
            batch_id = batch_result.get("batch_id")

            if not batch_id:
                raise ValueError("Batch API did not return batch_id")

            logger.info(
                f"Batch transcription submitted | batch_id={batch_id} | recording={recording_id} | user={ctx.user_id}"
            )

            # Start polling task
            task = batch_transcribe_recording_task.delay(
                recording_id=recording_id,
                user_id=ctx.user_id,
                batch_id=batch_id,
                poll_interval=10.0,  # 10 seconds
                max_wait_time=3600.0,  # 1 hour
            )

            logger.info(
                f"Batch polling task {task.id} created | batch_id={batch_id} | "
                f"recording={recording_id} | user={ctx.user_id}"
            )

            return {
                "success": True,
                "task_id": task.id,
                "recording_id": recording_id,
                "batch_id": batch_id,
                "mode": "batch_api",
                "status": "queued",
                "message": "Batch transcription submitted. Polling task queued.",
                "check_status_url": f"/api/v1/tasks/{task.id}",
            }

        except Exception as e:
            logger.error(f"Failed to submit batch transcription: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to submit batch transcription: {e!s}",
            )
    else:
        # Synchronous API mode
        task = transcribe_recording_task.delay(
            recording_id=recording_id,
            user_id=ctx.user_id,
        )

        logger.info(f"Transcription task {task.id} created for recording {recording_id}, user {ctx.user_id}")

        return {
            "success": True,
            "task_id": task.id,
            "recording_id": recording_id,
            "mode": "sync_api",
            "status": "queued",
            "message": "Transcription task has been queued",
            "check_status_url": f"/api/v1/tasks/{task.id}",
        }


@router.post("/{recording_id}/upload/{platform}", response_model=RecordingOperationResponse)
async def upload_recording(
    recording_id: int,
    platform: str,
    preset_id: int | None = None,
    ctx: ServiceContext = Depends(get_service_context),
) -> RecordingOperationResponse:
    """Upload recording to specified platform (async task)."""
    from api.helpers.status_manager import should_allow_upload
    from api.tasks.upload import upload_recording_to_platform
    from models.recording import TargetType

    # Get recording from DB
    recording_repo = RecordingRepository(ctx.session)
    recording = await recording_repo.get_by_id(recording_id, ctx.user_id)

    if not recording:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Recording {recording_id} not found or you don't have access"
        )

    # Check if upload can be started to this platform
    try:
        target_type_enum = TargetType[platform.upper()]
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid platform: {platform}. Supported: youtube, vk, etc.",
        )

    if not should_allow_upload(recording, target_type_enum.value):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Upload to {platform} cannot be started. Current status: {recording.status}. "
            f"Either upload is already completed/in progress, or recording is not ready for upload.",
        )

    # Check if processed video exists
    if not recording.processed_video_path:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No processed video available. Please process the recording first.",
        )

    video_path = recording.processed_video_path

    # Check if file exists
    if not Path(video_path).exists():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"Processed video file not found at path: {video_path}"
        )

    # Start async task
    task = upload_recording_to_platform.delay(
        recording_id=recording_id,
        user_id=ctx.user_id,
        platform=platform,
        preset_id=preset_id,
    )

    logger.info(f"Upload task {task.id} created for recording {recording_id} to {platform}, user {ctx.user_id}")

    return {
        "success": True,
        "task_id": task.id,
        "recording_id": recording_id,
        "platform": platform,
        "status": "queued",
        "message": f"Upload task to {platform} has been queued",
        "check_status_url": f"/api/v1/tasks/{task.id}",
    }


# ============================================================================
# NEW: Separate Transcription Pipeline Endpoints
# ============================================================================


@router.post("/{recording_id}/topics", response_model=RecordingOperationResponse)
async def extract_topics(
    recording_id: int,
    granularity: str = Query("long", description="Mode: 'short' or 'long'"),
    version_id: str | None = Query(None, description="Version ID (optional)"),
    ctx: ServiceContext = Depends(get_service_context),
) -> RecordingOperationResponse:
    """Extract topics from existing transcription (async task). Requires /transcribe first."""
    from api.tasks.processing import extract_topics_task

    # Get recording from DB
    recording_repo = RecordingRepository(ctx.session)
    recording = await recording_repo.get_by_id(recording_id, ctx.user_id)

    if not recording:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Recording {recording_id} not found or you don't have access",
        )

    # Check if transcription exists
    from transcription_module.manager import get_transcription_manager

    transcription_manager = get_transcription_manager()
    user_slug = recording.owner.user_slug
    if not transcription_manager.has_master(recording_id, user_slug):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No transcription found. Please run /transcribe first.",
        )

    # Start async task
    task = extract_topics_task.delay(
        recording_id=recording_id,
        user_id=ctx.user_id,
        granularity=granularity,
        version_id=version_id,
    )

    logger.info(
        f"Extract topics task {task.id} created for recording {recording_id}, "
        f"user {ctx.user_id}, granularity={granularity}"
    )

    return {
        "success": True,
        "task_id": task.id,
        "recording_id": recording_id,
        "status": "queued",
        "message": "Topic extraction task has been queued",
        "check_status_url": f"/api/v1/tasks/{task.id}",
    }


@router.post("/{recording_id}/subtitles", response_model=RecordingOperationResponse)
async def generate_subtitles(
    recording_id: int,
    formats: list[str] = Query(["srt", "vtt"], description="Formats: 'srt', 'vtt'"),
    ctx: ServiceContext = Depends(get_service_context),
) -> RecordingOperationResponse:
    """Generate subtitles from transcription (async task). Requires /transcribe first."""
    from api.tasks.processing import generate_subtitles_task

    # Get recording from DB
    recording_repo = RecordingRepository(ctx.session)
    recording = await recording_repo.get_by_id(recording_id, ctx.user_id)

    if not recording:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Recording {recording_id} not found or you don't have access",
        )

    # Check if transcription is present
    from transcription_module.manager import get_transcription_manager

    transcription_manager = get_transcription_manager()
    user_slug = recording.owner.user_slug
    if not transcription_manager.has_master(recording_id, user_slug):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No transcription found. Please run /transcribe first.",
        )

    # Start async task
    task = generate_subtitles_task.delay(
        recording_id=recording_id,
        user_id=ctx.user_id,
        formats=formats,
    )

    logger.info(
        f"Generate subtitles task {task.id} created for recording {recording_id}, user {ctx.user_id}, formats={formats}"
    )

    return {
        "success": True,
        "task_id": task.id,
        "recording_id": recording_id,
        "status": "queued",
        "message": "Subtitle generation task has been queued",
        "check_status_url": f"/api/v1/tasks/{task.id}",
    }


@router.post("/bulk/transcribe", response_model=RecordingBulkOperationResponse)
async def bulk_transcribe_recordings(
    data: BulkTranscribeRequest,
    ctx: ServiceContext = Depends(get_service_context),
) -> RecordingBulkOperationResponse:
    """Bulk transcription of multiple recordings (async tasks)."""
    from api.tasks.processing import batch_transcribe_recording_task, transcribe_recording_task

    # Resolve recording IDs
    recording_ids = await _resolve_recording_ids(data.recording_ids, data.filters, data.limit, ctx)

    if not recording_ids:
        return {
            "queued_count": 0,
            "skipped_count": 0,
            "error_count": 0,
            "tasks": [],
            "message": "No recordings matched the criteria",
        }

    recording_repo = RecordingRepository(ctx.session)
    tasks = []

    recordings_map = await recording_repo.get_by_ids(recording_ids, ctx.user_id)

    for recording_id in recording_ids:
        try:
            recording = recordings_map.get(recording_id)

            if not recording:
                tasks.append(
                    {
                        "recording_id": recording_id,
                        "status": "error",
                        "error": "Recording not found or no access",
                        "task_id": None,
                    }
                )
                continue

            if recording.blank_record:
                tasks.append(
                    {
                        "recording_id": recording_id,
                        "status": "skipped",
                        "reason": "Blank record (too short or too small)",
                        "task_id": None,
                    }
                )
                continue

            # Check if file is present
            if not recording.processed_video_path and not recording.local_video_path:
                tasks.append(
                    {
                        "recording_id": recording_id,
                        "status": "error",
                        "error": "No video file available",
                        "task_id": None,
                    }
                )
                continue

            # Select mode: Batch API or regular sync API
            if data.use_batch_api:
                # Fireworks Batch API mode
                task = batch_transcribe_recording_task.delay(
                    recording_id=recording_id,
                    user_id=ctx.user_id,
                    batch_id=None,  # Will be set by task
                    poll_interval=data.poll_interval,
                    max_wait_time=data.max_wait_time,
                )
                task_info = {
                    "recording_id": recording_id,
                    "status": "queued",
                    "task_id": task.id,
                    "mode": "batch_api",
                    "check_status_url": f"/api/v1/tasks/{task.id}",
                }
            else:
                # Sync API mode
                task = transcribe_recording_task.delay(
                    recording_id=recording_id,
                    user_id=ctx.user_id,
                )
                task_info = {
                    "recording_id": recording_id,
                    "status": "queued",
                    "task_id": task.id,
                    "mode": "sync_api",
                    "check_status_url": f"/api/v1/tasks/{task.id}",
                }

            tasks.append(task_info)

        except Exception as e:
            logger.error(f"Failed to create transcribe task for recording {recording_id}: {e}")
            tasks.append(
                {
                    "recording_id": recording_id,
                    "status": "error",
                    "error": str(e),
                    "task_id": None,
                }
            )

    queued_count = len([t for t in tasks if t["status"] == "queued"])
    skipped_count = len([t for t in tasks if t["status"] == "skipped"])
    error_count = len([t for t in tasks if t["status"] == "error"])

    return {
        "queued_count": queued_count,
        "skipped_count": skipped_count,
        "error_count": error_count,
        "mode": "batch_api" if data.use_batch_api else "sync_api",
        "tasks": tasks,
    }


@router.post("/{recording_id}/retry-upload", response_model=RetryUploadResponse)
async def retry_failed_uploads(
    recording_id: int,
    platforms: list[str] | None = None,
    ctx: ServiceContext = Depends(get_service_context),
) -> RetryUploadResponse:
    """Retry upload for failed output targets."""
    from api.tasks.upload import upload_recording_to_platform

    recording_repo = RecordingRepository(ctx.session)

    # Get recording from DB
    recording = await recording_repo.get_by_id(recording_id, ctx.user_id)
    if not recording:
        raise HTTPException(status_code=404, detail=f"Recording {recording_id} not found")

    # Get failed output_targets
    failed_targets = []
    for output in recording.outputs:
        if output.failed or output.status == TargetStatus.FAILED.value:
            # If specific platforms are specified, filter them
            if platforms:
                if output.target_type.lower() in [p.lower() for p in platforms]:
                    failed_targets.append(output)
            else:
                failed_targets.append(output)

    if not failed_targets:
        return {
            "message": "No failed uploads found for retry",
            "recording_id": recording_id,
            "tasks": [],
        }

    # Start retry for each failed target
    tasks = []
    for target in failed_targets:
        try:
            task = upload_recording_to_platform.delay(
                recording_id=recording_id,
                user_id=ctx.user_id,
                platform=target.target_type.value.lower(),
                preset_id=target.preset_id,
            )

            tasks.append(
                {
                    "platform": target.target_type.value,
                    "task_id": str(task.id),
                    "status": "queued",
                    "previous_attempts": target.retry_count,
                }
            )

            logger.info(
                f"Queued retry upload for recording {recording_id} to {target.target_type.value} "
                f"(attempt {target.retry_count + 1})"
            )

        except Exception as e:
            logger.error(f"Failed to queue retry for {target.target_type.value}: {e}")
            tasks.append(
                {
                    "platform": target.target_type.value,
                    "status": "error",
                    "error": str(e),
                }
            )

    return RetryUploadResponse(
        message=f"Retry queued for {len([t for t in tasks if t['status'] == 'queued'])} platforms",
        recording_id=recording_id,
        tasks=tasks,
    )


@router.get("/{recording_id}/config")
async def get_recording_config(
    recording_id: int,
    ctx: ServiceContext = Depends(get_service_context),
):
    """Get current resolved configuration for recording."""
    from api.schemas.recording.operations import RecordingConfigResponse
    from api.services.config_resolver import ConfigResolver

    recording_repo = RecordingRepository(ctx.session)

    # Get recording from DB
    recording = await recording_repo.get_by_id(recording_id, ctx.user_id)
    if not recording:
        raise HTTPException(status_code=404, detail=f"Recording {recording_id} not found")

    # Resolve configuration
    config_resolver = ConfigResolver(ctx.session)
    config_data = await config_resolver.get_base_config_for_edit(recording, ctx.user_id)

    return RecordingConfigResponse(
        recording_id=recording_id,
        is_mapped=recording.is_mapped,
        template_id=config_data["template_id"],
        template_name=config_data["template_name"],
        has_manual_override=config_data["has_manual_override"],
        processing_config=config_data["processing_config"],
        output_config=config_data["output_config"],
        metadata_config=config_data["metadata_config"],
    )


@router.put("/{recording_id}/config")
async def update_recording_config(
    recording_id: int,
    processing_config: dict | None = None,
    output_config: dict | None = None,
    ctx: ServiceContext = Depends(get_service_context),
) -> dict:
    """Save user configuration overrides in recording.processing_preferences."""
    from api.services.config_resolver import ConfigResolver

    recording_repo = RecordingRepository(ctx.session)

    # Get recording from DB
    recording = await recording_repo.get_by_id(recording_id, ctx.user_id)
    if not recording:
        raise HTTPException(status_code=404, detail=f"Recording {recording_id} not found")

    # Get config resolver
    config_resolver = ConfigResolver(ctx.session)

    # Save only user overrides (not full config)
    new_preferences = recording.processing_preferences or {}

    if processing_config is not None:
        if "processing_config" not in new_preferences:
            new_preferences["processing_config"] = {}
        new_preferences["processing_config"] = config_resolver._merge_configs(
            new_preferences.get("processing_config", {}), processing_config
        )

    if output_config is not None:
        if "output_config" not in new_preferences:
            new_preferences["output_config"] = {}
        new_preferences["output_config"] = config_resolver._merge_configs(
            new_preferences.get("output_config", {}), output_config
        )

    # Save overrides to recording.processing_preferences
    recording.processing_preferences = new_preferences if new_preferences else None

    # Sync stages with updated config
    from api.helpers.stage_sync import sync_stages_with_config

    effective_config = await config_resolver.resolve_processing_config(recording, ctx.user_id)
    await sync_stages_with_config(recording, effective_config)

    await ctx.session.commit()

    logger.info(f"Updated manual config for recording {recording_id}")

    from api.schemas.recording.operations import ConfigUpdateResponse

    return ConfigUpdateResponse(
        recording_id=recording_id,
        message="Configuration saved",
        has_manual_override=bool(new_preferences),
        overrides=new_preferences,
        effective_config=effective_config,
    )


@router.delete("/{recording_id}/config", response_model=ConfigSaveResponse)
async def reset_to_template(
    recording_id: int,
    ctx: ServiceContext = Depends(get_service_context),
) -> ConfigSaveResponse:
    """Reset user config overrides and return to template configuration."""
    from api.services.config_resolver import ConfigResolver

    recording_repo = RecordingRepository(ctx.session)

    # Get recording from DB
    recording = await recording_repo.get_by_id(recording_id, ctx.user_id)
    if not recording:
        raise HTTPException(status_code=404, detail=f"Recording {recording_id} not found")

    # Clear overrides
    recording.processing_preferences = None
    await ctx.session.commit()

    # Get effective config (from template)
    config_resolver = ConfigResolver(ctx.session)
    effective_config = await config_resolver.resolve_processing_config(recording, ctx.user_id)

    logger.info(f"Reset recording {recording_id} to template configuration")

    return ConfigSaveResponse(
        recording_id=recording_id,
        message="Reset to template configuration",
        has_manual_override=False,
        effective_config=effective_config,
    )


@router.post("/{recording_id}/reset", response_model=ResetRecordingResponse)
async def reset_recording(
    recording_id: int,
    delete_files: bool = Query(True, description="Delete all files (video, audio, transcription)"),
    ctx: ServiceContext = Depends(get_service_context),
) -> ResetRecordingResponse:
    """Reset recording to initial state, optionally deleting all processed files."""
    from pathlib import Path

    from sqlalchemy import delete

    from database.models import OutputTargetModel, ProcessingStageModel

    recording_repo = RecordingRepository(ctx.session)
    recording = await recording_repo.get_by_id(recording_id, ctx.user_id)

    if not recording:
        raise HTTPException(status_code=404, detail=f"Recording {recording_id} not found")

    if recording.deleted:
        raise HTTPException(
            status_code=400,
            detail="Cannot reset deleted recording. Please restore it first using POST /recordings/{id}/restore",
        )

    deleted_files = []
    errors = []

    # Delete files if requested
    if delete_files:
        files_to_delete = []

        # Local video
        if recording.local_video_path:
            files_to_delete.append(("local_video", recording.local_video_path))

        # Processed video
        if recording.processed_video_path:
            files_to_delete.append(("processed_video", recording.processed_video_path))

        # Processed audio file
        if recording.processed_audio_path:
            audio_file = Path(recording.processed_audio_path)
            if audio_file.exists():
                # Delete file and its parent directory if it is empty
                files_to_delete.append(("processed_audio_file", str(audio_file)))
                audio_dir = audio_file.parent
                if audio_dir.exists() and not any(audio_dir.iterdir()):
                    files_to_delete.append(("empty_audio_dir", str(audio_dir)))

        # Transcription directory
        if recording.transcription_dir:
            files_to_delete.append(("transcription_dir", recording.transcription_dir))

        # Delete files
        for file_type, file_path in files_to_delete:
            try:
                path = Path(file_path)
                if path.exists():
                    if path.is_dir():
                        import shutil

                        shutil.rmtree(path)
                        deleted_files.append({"type": file_type, "path": str(path), "is_dir": True})
                    else:
                        path.unlink()
                        deleted_files.append({"type": file_type, "path": str(path), "is_dir": False})
            except Exception as e:
                errors.append({"type": file_type, "path": file_path, "error": str(e)})
                logger.error(f"Failed to delete {file_type} at {file_path}: {e}")

    # Clear recording metadata
    recording.local_video_path = None
    recording.processed_video_path = None
    recording.processed_audio_path = None
    recording.transcription_dir = None
    recording.topic_timestamps = None
    recording.main_topics = None
    recording.transcription_info = None
    recording.failed = False
    recording.failed_reason = None

    # Set status based on source processing state and is_mapped
    if recording.source and recording.source.meta:
        zoom_processing_incomplete = recording.source.meta.get("zoom_processing_incomplete", False)
    else:
        zoom_processing_incomplete = False

    if zoom_processing_incomplete:
        recording.status = ProcessingStatus.PENDING_SOURCE
    elif recording.is_mapped:
        recording.status = ProcessingStatus.INITIALIZED
    else:
        recording.status = ProcessingStatus.SKIPPED

    # Update expire_at from user config (merged with defaults)
    user_config_repo = UserConfigRepository(ctx.session)
    user_config = await user_config_repo.get_effective_config(ctx.user_id)

    retention = user_config.get("retention", {})
    auto_expire_days = retention.get("auto_expire_days", 90)
    if auto_expire_days:
        recording.expire_at = datetime.now(UTC) + timedelta(days=auto_expire_days)

    # Delete output_targets
    await ctx.session.execute(delete(OutputTargetModel).where(OutputTargetModel.recording_id == recording_id))

    # Delete processing_stages
    await ctx.session.execute(delete(ProcessingStageModel).where(ProcessingStageModel.recording_id == recording_id))

    await ctx.session.commit()

    logger.info(
        f"Reset recording {recording_id}: deleted {len(deleted_files)} files, "
        f"{len(errors)} errors, status -> {recording.status}"
    )

    return ResetRecordingResponse(
        success=True,
        recording_id=recording_id,
        message="Recording reset to initial state",
        deleted_files=deleted_files if deleted_files else None,
        errors=errors if errors else None,
        status=recording.status,
        preserved={
            "template_id": recording.template_id,
            "is_mapped": recording.is_mapped,
            "processing_preferences": bool(recording.processing_preferences),
        },
        task_id=None,
    )


@router.post("/{recording_id}/template/{template_id}", response_model=RecordingOperationResponse)
async def bind_template_to_recording(
    recording_id: int,
    template_id: int,
    reset_preferences: bool = Query(False, description="Reset processing preferences to use template config"),
    ctx: ServiceContext = Depends(get_service_context),
) -> RecordingOperationResponse:
    """Bind template to recording."""
    from api.repositories.template_repos import RecordingTemplateRepository

    recording_repo = RecordingRepository(ctx.session)
    recording = await recording_repo.get_by_id(recording_id, ctx.user_id)

    if not recording:
        raise HTTPException(status_code=404, detail=f"Recording {recording_id} not found")

    # Validate template exists and belongs to user
    template_repo = RecordingTemplateRepository(ctx.session)
    template = await template_repo.find_by_id(template_id, ctx.user_id)

    if not template:
        raise HTTPException(status_code=404, detail=f"Template {template_id} not found")

    # Bind template
    recording.template_id = template_id
    recording.is_mapped = True

    # Reset preferences if requested
    if reset_preferences:
        recording.processing_preferences = None

    # Update status if needed (same logic as in run_recording)
    if recording.status == ProcessingStatus.SKIPPED:
        recording.status = ProcessingStatus.INITIALIZED

    await ctx.session.commit()

    logger.info(
        f"Template {template_id} ('{template.name}') bound to recording {recording_id}, "
        f"reset_preferences={reset_preferences}"
    )

    return RecordingOperationResponse(
        success=True,
        recording_id=recording_id,
        message=f"Template '{template.name}' bound successfully"
        + (" (preferences reset)" if reset_preferences else ""),
    )


@router.delete("/{recording_id}/template", response_model=RecordingOperationResponse)
async def unbind_template_from_recording(
    recording_id: int,
    ctx: ServiceContext = Depends(get_service_context),
) -> RecordingOperationResponse:
    """Unbind template from recording."""
    recording_repo = RecordingRepository(ctx.session)
    recording = await recording_repo.get_by_id(recording_id, ctx.user_id)

    if not recording:
        raise HTTPException(status_code=404, detail=f"Recording {recording_id} not found")

    if not recording.template_id:
        raise HTTPException(status_code=400, detail="Recording has no template bound")

    # Unbind template
    recording.template_id = None
    recording.is_mapped = False

    await ctx.session.commit()

    logger.info(f"Template unbound from recording {recording_id}")

    return RecordingOperationResponse(
        success=True,
        recording_id=recording_id,
        message="Template unbound successfully",
    )


# ============================================================================
# New Bulk Operations Endpoints
# ============================================================================


@router.post("/bulk/download", response_model=RecordingBulkOperationResponse)
async def bulk_download_recordings(
    data: BulkDownloadRequest,
    ctx: ServiceContext = Depends(get_service_context),
) -> RecordingBulkOperationResponse:
    """Bulk download recordings from Zoom."""
    from api.tasks.processing import download_recording_task

    # Resolve recording IDs
    recording_ids = await _resolve_recording_ids(data.recording_ids, data.filters, data.limit, ctx)

    recording_repo = RecordingRepository(ctx.session)
    tasks = []

    recordings_map = await recording_repo.get_by_ids(recording_ids, ctx.user_id)

    for recording_id in recording_ids:
        try:
            recording = recordings_map.get(recording_id)
            if not recording:
                tasks.append(
                    {
                        "recording_id": recording_id,
                        "status": "error",
                        "error": "Recording not found",
                        "task_id": None,
                    }
                )
                continue

            if recording.blank_record:
                tasks.append(
                    {
                        "recording_id": recording_id,
                        "status": "skipped",
                        "error": "Blank record",
                        "task_id": None,
                    }
                )
                continue

            task = download_recording_task.delay(
                recording_id=recording_id,
                user_id=ctx.user_id,
                force=data.force,
                manual_override=None,
            )

            tasks.append(
                {
                    "recording_id": recording_id,
                    "status": "queued",
                    "task_id": task.id,
                    "check_status_url": f"/api/v1/tasks/{task.id}",
                }
            )

        except Exception as e:
            logger.error(f"Failed to queue download for recording {recording_id}: {e}")
            tasks.append(
                {
                    "recording_id": recording_id,
                    "status": "error",
                    "error": str(e),
                    "task_id": None,
                }
            )

    queued_count = len([t for t in tasks if t["status"] == "queued"])

    return RecordingBulkOperationResponse(
        queued_count=queued_count,
        skipped_count=len([t for t in tasks if t["status"] == "skipped"]),
        tasks=tasks,
    )


@router.post("/bulk/trim", response_model=RecordingBulkOperationResponse)
async def bulk_trim_recordings(
    data: BulkTrimRequest,
    ctx: ServiceContext = Depends(get_service_context),
) -> RecordingBulkOperationResponse:
    """Bulk trim recordings to remove silence using FFmpeg."""
    from api.tasks.processing import trim_video_task

    # Resolve recording IDs
    recording_ids = await _resolve_recording_ids(data.recording_ids, data.filters, data.limit, ctx)

    # Build manual override
    manual_override = {
        "processing": {
            "silence_threshold": data.silence_threshold,
            "min_silence_duration": data.min_silence_duration,
            "padding_before": data.padding_before,
            "padding_after": data.padding_after,
        }
    }

    recording_repo = RecordingRepository(ctx.session)
    tasks = []

    recordings_map = await recording_repo.get_by_ids(recording_ids, ctx.user_id)

    for recording_id in recording_ids:
        try:
            recording = recordings_map.get(recording_id)
            if not recording or recording.blank_record:
                continue

            task = trim_video_task.delay(
                recording_id=recording_id,
                user_id=ctx.user_id,
                manual_override=manual_override,
            )

            tasks.append(
                {
                    "recording_id": recording_id,
                    "status": "queued",
                    "task_id": task.id,
                }
            )

        except Exception as e:
            logger.error(f"Failed to queue trim for recording {recording_id}: {e}")

    queued_count = len([t for t in tasks if t["status"] == "queued"])
    skipped_count = len([t for t in tasks if t["status"] == "skipped"])

    return {
        "queued_count": queued_count,
        "skipped_count": skipped_count,
        "tasks": tasks,
    }


@router.post("/bulk/topics", response_model=RecordingBulkOperationResponse)
async def bulk_extract_topics(
    data: BulkTopicsRequest,
    ctx: ServiceContext = Depends(get_service_context),
) -> RecordingBulkOperationResponse:
    """Bulk extract topics from transcriptions."""
    from api.tasks.processing import extract_topics_task

    # Resolve recording IDs
    recording_ids = await _resolve_recording_ids(data.recording_ids, data.filters, data.limit, ctx)

    recording_repo = RecordingRepository(ctx.session)
    tasks = []

    recordings_map = await recording_repo.get_by_ids(recording_ids, ctx.user_id)

    for recording_id in recording_ids:
        try:
            recording = recordings_map.get(recording_id)
            if not recording or recording.blank_record:
                continue

            task = extract_topics_task.delay(
                recording_id=recording_id,
                user_id=ctx.user_id,
                granularity=data.granularity,
                version_id=data.version_id,
            )

            tasks.append(
                {
                    "recording_id": recording_id,
                    "status": "queued",
                    "task_id": task.id,
                }
            )

        except Exception as e:
            logger.error(f"Failed to queue topics for recording {recording_id}: {e}")

    queued_count = len([t for t in tasks if t["status"] == "queued"])
    skipped_count = len([t for t in tasks if t["status"] == "skipped"])

    return {
        "queued_count": queued_count,
        "skipped_count": skipped_count,
        "tasks": tasks,
    }


@router.post("/bulk/subtitles", response_model=RecordingBulkOperationResponse)
async def bulk_generate_subtitles(
    data: BulkSubtitlesRequest,
    ctx: ServiceContext = Depends(get_service_context),
) -> RecordingBulkOperationResponse:
    """Bulk generate subtitles from transcriptions."""
    from api.tasks.processing import generate_subtitles_task

    # Resolve recording IDs
    recording_ids = await _resolve_recording_ids(data.recording_ids, data.filters, data.limit, ctx)

    recording_repo = RecordingRepository(ctx.session)
    tasks = []

    recordings_map = await recording_repo.get_by_ids(recording_ids, ctx.user_id)

    for recording_id in recording_ids:
        try:
            recording = recordings_map.get(recording_id)
            if not recording or recording.blank_record:
                continue

            task = generate_subtitles_task.delay(
                recording_id=recording_id,
                user_id=ctx.user_id,
                formats=data.formats,
            )

            tasks.append(
                {
                    "recording_id": recording_id,
                    "status": "queued",
                    "task_id": task.id,
                }
            )

        except Exception as e:
            logger.error(f"Failed to queue subtitles for recording {recording_id}: {e}")

    queued_count = len([t for t in tasks if t["status"] == "queued"])
    skipped_count = len([t for t in tasks if t["status"] == "skipped"])

    return {
        "queued_count": queued_count,
        "skipped_count": skipped_count,
        "tasks": tasks,
    }


@router.post("/bulk/upload", response_model=RecordingBulkOperationResponse)
async def bulk_upload_recordings(
    data: BulkUploadRequest,
    ctx: ServiceContext = Depends(get_service_context),
) -> RecordingBulkOperationResponse:
    """Bulk upload recordings to platforms."""
    from api.tasks.upload import upload_recording_to_platform

    # Resolve recording IDs
    recording_ids = await _resolve_recording_ids(data.recording_ids, data.filters, data.limit, ctx)

    recording_repo = RecordingRepository(ctx.session)
    tasks = []

    recordings_map = await recording_repo.get_by_ids(recording_ids, ctx.user_id)

    for recording_id in recording_ids:
        try:
            recording = recordings_map.get(recording_id)
            if not recording or recording.blank_record:
                continue

            platforms = data.platforms if data.platforms else ["youtube", "vk"]

            for platform in platforms:
                # Use preset_id from request, or let upload task auto-select from template
                # (auto-select logic is in upload_recording_to_platform task)
                task = upload_recording_to_platform.delay(
                    recording_id=recording_id,
                    user_id=ctx.user_id,
                    platform=platform,
                    preset_id=data.preset_id,  # Can be None - task will auto-select from template
                )

                tasks.append(
                    {
                        "recording_id": recording_id,
                        "platform": platform,
                        "status": "queued",
                        "task_id": task.id,
                    }
                )

        except Exception as e:
            logger.error(f"Failed to queue upload for recording {recording_id}: {e}")

    queued_count = len([t for t in tasks if t["status"] == "queued"])
    skipped_count = len([t for t in tasks if t["status"] == "skipped"])

    return {
        "queued_count": queued_count,
        "skipped_count": skipped_count,
        "tasks": tasks,
    }


# ============================================================================
# Soft Delete Endpoints
# ============================================================================


class DeleteRecordingResponse(BaseModel):
    """Response for soft delete recording."""

    message: str
    recording_id: int
    deleted_at: datetime
    hard_delete_at: datetime  # When recording will be completely removed from DB


class RestoreRecordingResponse(BaseModel):
    """Response for restore recording."""

    message: str
    recording_id: int
    restored_at: datetime
    expire_at: datetime


@router.delete("/{recording_id}", response_model=DeleteRecordingResponse)
async def delete_recording(
    recording_id: int,
    ctx: ServiceContext = Depends(get_service_context),
) -> DeleteRecordingResponse:
    """Soft delete recording (can be restored before hard deletion)."""
    recording_repo = RecordingRepository(ctx.session)
    recording = await recording_repo.get_by_id(recording_id, ctx.user_id)

    if not recording:
        raise HTTPException(status_code=404, detail=f"Recording {recording_id} not found")

    if recording.deleted:
        raise HTTPException(status_code=400, detail="Recording is already deleted")

    # Get user config (merged with defaults)
    user_config_repo = UserConfigRepository(ctx.session)
    user_config = await user_config_repo.get_effective_config(ctx.user_id)

    await recording_repo.soft_delete(recording, user_config)
    await ctx.session.commit()

    logger.info(f"Soft deleted recording {recording_id} by user {ctx.user_id}")

    return DeleteRecordingResponse(
        message="Recording deleted successfully",
        recording_id=recording.id,
        deleted_at=recording.deleted_at,
        hard_delete_at=recording.hard_delete_at,
    )


class BulkDeleteResponse(BaseModel):
    """Response for bulk delete operation."""

    message: str
    deleted_count: int
    skipped_count: int
    error_count: int
    details: list[dict]


@router.post("/bulk/delete", response_model=BulkDeleteResponse)
async def bulk_delete_recordings(
    data: BulkDeleteRequest,
    ctx: ServiceContext = Depends(get_service_context),
) -> BulkDeleteResponse:
    """Bulk soft delete recordings."""
    # Resolve recording IDs
    recording_ids = await _resolve_recording_ids(data.recording_ids, data.filters, data.limit, ctx)

    # Get user config once (merged with defaults)
    user_config_repo = UserConfigRepository(ctx.session)
    user_config = await user_config_repo.get_effective_config(ctx.user_id)

    recording_repo = RecordingRepository(ctx.session)
    deleted_count = 0
    skipped_count = 0
    error_count = 0
    details = []

    recordings_map = await recording_repo.get_by_ids(recording_ids, ctx.user_id)

    for recording_id in recording_ids:
        try:
            recording = recordings_map.get(recording_id)

            if not recording:
                error_count += 1
                details.append(
                    {
                        "recording_id": recording_id,
                        "status": "error",
                        "message": "Recording not found",
                    }
                )
                continue

            if recording.deleted:
                skipped_count += 1
                details.append(
                    {
                        "recording_id": recording_id,
                        "status": "skipped",
                        "message": "Already deleted",
                    }
                )
                continue

            await recording_repo.soft_delete(recording, user_config)
            deleted_count += 1
            details.append(
                {
                    "recording_id": recording_id,
                    "status": "deleted",
                    "deleted_at": recording.deleted_at.isoformat() if recording.deleted_at else None,
                    "hard_delete_at": recording.hard_delete_at.isoformat() if recording.hard_delete_at else None,
                }
            )

        except Exception as e:
            error_count += 1
            details.append(
                {
                    "recording_id": recording_id,
                    "status": "error",
                    "message": str(e),
                }
            )
            logger.error(f"Failed to delete recording {recording_id}: {e}")

    # Commit all changes
    try:
        await ctx.session.commit()
    except Exception as e:
        logger.error(f"Failed to commit bulk delete: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to commit bulk delete: {e!s}",
        )

    logger.info(
        f"Bulk delete completed by user {ctx.user_id}: "
        f"{deleted_count} deleted, {skipped_count} skipped, {error_count} errors"
    )

    return BulkDeleteResponse(
        message=f"Bulk delete completed: {deleted_count} recordings deleted",
        deleted_count=deleted_count,
        skipped_count=skipped_count,
        error_count=error_count,
        details=details,
    )


@router.post("/{recording_id}/restore", response_model=RestoreRecordingResponse)
async def restore_recording(
    recording_id: int,
    ctx: ServiceContext = Depends(get_service_context),
) -> RestoreRecordingResponse:
    """Restore soft deleted recording (only if files still present)."""
    recording_repo = RecordingRepository(ctx.session)
    recording = await recording_repo.get_by_id(recording_id, ctx.user_id, include_deleted=True)

    if not recording:
        raise HTTPException(status_code=404, detail=f"Recording {recording_id} not found")

    if not recording.deleted:
        raise HTTPException(status_code=400, detail="Recording is not deleted")

    if recording.delete_state != "soft":
        raise HTTPException(
            status_code=400,
            detail="Cannot restore: files already deleted. Recording can only be restored before files cleanup.",
        )

    # Get user config (merged with defaults)
    user_config_repo = UserConfigRepository(ctx.session)
    user_config = await user_config_repo.get_effective_config(ctx.user_id)

    await recording_repo.restore(recording, user_config)
    await ctx.session.commit()

    logger.info(f"Restored recording {recording_id} by user {ctx.user_id}")

    return RestoreRecordingResponse(
        message="Recording restored successfully",
        recording_id=recording.id,
        restored_at=datetime.now(UTC),
        expire_at=recording.expire_at,
    )
