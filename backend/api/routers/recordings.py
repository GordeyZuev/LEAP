"""Recording endpoints with multi-tenancy support"""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, NamedTuple, TypedDict

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import Response, StreamingResponse
from sqlalchemy import select

from api.auth.dependencies import check_user_quotas, get_current_user, require_feature
from api.core.context import ServiceContext
from api.core.dependencies import get_service_context
from api.helpers.blank_record import positive_duration_seconds
from api.helpers.media_duration import display_duration_seconds
from api.helpers.share_stats import build_share_stats_for_detail, build_share_stats_summary
from api.helpers.text import collapse_whitespace
from api.repositories.config_repos import UserConfigRepository
from api.repositories.recording_repos import RecordingRepository
from api.repositories.template_repos import InputSourceRepository
from api.routers.recordings_helpers import (
    _CONFIG_RESOLUTION_HTTP_ERRORS,
    _build_export_row,
    _build_override_from_flexible,
    _build_processing_stages,
    _build_source_info,
    _build_uploads_dict,
    _collect_platforms_from_recordings,
    _execute_dry_run_bulk,
    _execute_dry_run_single,
    _generate_csv,
    _generate_xlsx_bytes,
    _get_export_column_order,
    _resolve_recording_ids,
)
from api.schemas.auth import UserInDB
from api.schemas.recording.config_update import RecordingConfigUpdateRequest
from api.schemas.recording.export import ExportRecordingsRequest
from api.schemas.recording.filters import OperationalState
from api.schemas.recording.operations import (
    BulkProcessDryRunResponse,
    ConfigSaveResponse,
    ConfigUpdateResponse,
    DeleteRecordingResponse,
    DryRunResponse,
    LocalRecordingUploadResponse,
    PauseRecordingResponse,
    RecordingBulkDeleteResponse,
    RecordingBulkOperationResponse,
    RecordingConfigResponse,
    RecordingOperationResponse,
    ResetRecordingResponse,
    RestoreRecordingResponse,
    TemplateBindResponse,
    TemplateUnbindResponse,
)
from api.schemas.recording.request import (
    AddPlaylistByUrlRequest,
    AddPlaylistResponse,
    AddPublicDiskLinkRequest,
    AddPublicDiskLinkResponse,
    AddVideoByUrlRequest,
    AddVideoByUrlResponse,
    BulkDeleteRequest,
    BulkDownloadRequest,
    BulkPauseRequest,
    BulkRunRequest,
    BulkSubtitlesRequest,
    BulkTopicsRequest,
    BulkTranscribeRequest,
    BulkTrimRequest,
    BulkUploadRequest,
    ConfigOverrideRequest,
    FormatsPreviewRequest,
    FormatsPreviewResponse,
    PublicDiskLinkRequest,
    RecordingUpdateRequest,
    ResumableUploadSettingsRequest,
    StartResumableUploadRequest,
    TopicsRenderRequest,
    TopicsUpdateRequest,
    TrimVideoRequest,
)
from api.schemas.recording.response import (
    DetailedRecordingResponse,
    OutputTargetResponse,
    PresetInfo,
    ProcessingStageResponse,
    RecordingListItem,
    RecordingListResponse,
    RecordingPipelineStatusResponse,
    SourceResponse,
)
from api.schemas.source_extras import SourceExtrasResponse
from api.services.config_utils import resolve_full_config
from api.services.quota_service import QuotaService
from api.services.resumable_upload import (
    CHUNK_BYTES,
    SESSION_TTL_SECONDS,
    create_session,
    lock_upload,
    read_session,
    save_session,
    session_status,
)
from api.shared.enums import Granularity
from config.settings import get_settings, storage_video_ingress_suffixes
from database.auth_models import UserModel
from database.models import RecordingModel
from file_storage.path_builder import StoragePathBuilder
from logger import format_details, get_logger, short_task_id, short_user_id
from models import ProcessingStatus
from models.recording import ProcessingStageStatus, SourceType, TargetStatus
from utils.pipeline_video_formats import ingress_validate_saved_media, strict_suffix_from_source_name
from video_processing_module.audio_detector import AudioDetector

router = APIRouter(prefix="/api/v1/recordings", tags=["Recordings"])
bulk_router = APIRouter()
logger = get_logger()


async def _track_recordings_created(ctx: ServiceContext, recording_ids: list[int]) -> None:
    """Best-effort: bump the monthly recording counter and log ``recording_created`` events.

    Called after the recordings are already committed, so tracking must never fail the
    request — any error is rolled back and logged, leaving the recordings intact.
    """
    if not recording_ids:
        return
    from api.repositories.usage_event_repo import UsageEventRepository
    from api.services.quota_service import QuotaService

    try:
        await QuotaService(ctx.session).track_recording_created(ctx.user_id, count=len(recording_ids))
        repo = UsageEventRepository(ctx.session)
        for rid in recording_ids:
            await repo.create(ctx.user_id, "recording_created", recording_id=rid)
        await ctx.session.commit()
    except Exception as exc:
        await ctx.session.rollback()
        logger.info(f"recording_created tracking failed (ignored): {exc!r}")


async def _track_recording_deleted(ctx: ServiceContext, recording_id: int) -> None:
    """Best-effort ``recording_deleted`` usage event (after the soft-delete commit)."""
    from api.repositories.usage_event_repo import UsageEventRepository

    try:
        await UsageEventRepository(ctx.session).create(ctx.user_id, "recording_deleted", recording_id=recording_id)
        await ctx.session.commit()
    except Exception as exc:
        await ctx.session.rollback()
        logger.info(f"recording_deleted tracking failed (ignored): {exc!r}")


_VIDEO_MEDIA_TYPES: dict[str, str] = {
    ".mp4": "video/mp4",
    ".webm": "video/webm",
    ".mov": "video/quicktime",
    ".mkv": "video/x-matroska",
}


def _recording_video_storage_key(recording: RecordingModel, media_kind: Literal["original", "processed"]) -> str | None:
    """Return the storage key for a recording's video, or None if missing.

    DB columns ``local_video_path`` / ``processed_video_path`` store storage keys
    (post-S3-migration). For legacy rows starting with ``storage/`` the backend
    ``_resolve`` strips the prefix.
    """
    raw = recording.local_video_path if media_kind == "original" else recording.processed_video_path
    return raw if raw else None


class _PosterPreview(NamedTuple):
    url: str
    source: Literal["thumbnail", "frame"]
    fallback_url: str | None = None
    asset_key: str = ""
    refresh_at_ms: int | None = None


class _PosterFields(TypedDict):
    poster_url: str | None
    poster_source: Literal["thumbnail", "frame"] | None
    poster_fallback_url: str | None
    poster_asset_key: str | None
    poster_refresh_at_ms: int | None


def _poster_asset_key(primary_storage_key: str, fallback_storage_key: str | None = None) -> str:
    """Stable client-side identity for poster object(s); unchanged across presign refreshes."""
    return f"{primary_storage_key}|{fallback_storage_key or ''}"


def _recording_poster_storage_key(recording: RecordingModel, user_slug: int | None = None) -> str | None:
    """Storage key for a recording's poster frame, by convention.

    Keyed off ``recording_root`` rather than a DB column, so posters need no
    migration and no backfill: the key is derivable, and the object is created
    lazily the first time a client asks for one that is missing.

    Returns None when the recording has no video at all — there is nothing to
    grab a frame from, so the card should show its placeholder and not ask.
    """
    if not (recording.local_video_path or recording.processed_video_path):
        return None
    if user_slug is None:
        owner = getattr(recording, "owner", None)
        user_slug = getattr(owner, "user_slug", None)
    if user_slug is None:
        return None
    from file_storage.path_builder import get_path_builder, to_storage_key

    return to_storage_key(get_path_builder().recording_root(user_slug, recording.id) / "poster.jpg")


def _look_thumbnail_name(looks: dict | None, recording_id: int) -> str | None:
    if not looks or recording_id not in looks:
        return None
    raw = getattr(looks[recording_id], "thumbnail_name", None)
    return raw if isinstance(raw, str) and raw else None


async def _poster_urls(
    session,
    user_id: str,
    recordings: list[RecordingModel],
    *,
    looks: dict | None = None,
) -> dict[int, _PosterPreview]:
    """Presign poster URLs from publication looks; unique S3 HEADs under one client."""
    from api.helpers.image_upload import presigned_image_refresh_at_ms
    from api.helpers.leap_publication import publication_looks_for_recordings
    from api.helpers.poster_thumbnail_cache import resolve_poster_thumbnails
    from api.observability import track_handler_section
    from config.settings import get_settings
    from database.auth_models import UserModel
    from file_storage.backends.s3 import S3StorageBackend
    from file_storage.factory import get_storage_backend
    from utils.thumbnail_manager import get_thumbnail_manager

    if not recordings:
        return {}

    with track_handler_section("poster_urls"):
        slug_row = await session.execute(select(UserModel.user_slug).where(UserModel.id == user_id))
        raw_slug = slug_row.scalar_one_or_none()
        user_slug = raw_slug if isinstance(raw_slug, int) else None

        if looks is None:
            with track_handler_section("poster_looks"):
                looks = await publication_looks_for_recordings(session, user_id, recordings)

        planned: list[tuple[int, str | None, str | None]] = []
        for recording in recordings:
            planned.append(
                (
                    recording.id,
                    _look_thumbnail_name(looks, recording.id),
                    _recording_poster_storage_key(recording, user_slug),
                )
            )

        unique_names = sorted({Path(name).name for _, name, _ in planned if name})
        thumbnail_manager = get_thumbnail_manager()
        storage = get_storage_backend()
        thumbnail_generation: str | None = None

        async with storage.shared_operations():
            thumb_by_name: dict[str, str | None] = {}
            if user_slug is not None and unique_names:
                with track_handler_section("poster_thumbnail_lookup"):

                    async def resolve_name(name: str) -> str | None:
                        return await thumbnail_manager.get_thumbnail_key(
                            user_slug=user_slug,
                            thumbnail_name=name,
                            fallback_to_template=True,
                        )

                    if isinstance(storage, S3StorageBackend):
                        thumb_by_name, thumbnail_generation = await resolve_poster_thumbnails(
                            user_slug, unique_names, resolve_name
                        )
                    else:
                        resolved = await asyncio.gather(*(resolve_name(name) for name in unique_names))
                        thumb_by_name = dict(zip(unique_names, resolved, strict=True))

            # (recording_id, storage_key, source, is_fallback_for_same_recording)
            pairs: list[tuple[int, str, Literal["thumbnail", "frame"], bool]] = []
            for rid, thumbnail_name, poster_key in planned:
                thumb_key = thumb_by_name.get(Path(thumbnail_name).name) if thumbnail_name else None
                if thumb_key:
                    pairs.append((rid, thumb_key, "thumbnail", False))
                    if poster_key:
                        pairs.append((rid, poster_key, "frame", True))
                    continue
                if poster_key:
                    pairs.append((rid, poster_key, "frame", False))

            if not pairs:
                return {}

            presign_expires = get_settings().storage.s3_presign_expires
            refresh_at_ms = presigned_image_refresh_at_ms(storage, presign_expires)
            with track_handler_section("poster_presign"):
                urls = await storage.presigned_urls(
                    [key for _, key, _, _ in pairs],
                    expires_in=presign_expires,
                )

        previews: dict[int, _PosterPreview] = {}
        fallback_urls: dict[int, str] = {}
        primary_keys: dict[int, str] = {}
        fallback_keys: dict[int, str] = {}
        for (rid, key, source, is_fallback), url in zip(pairs, urls, strict=True):
            if is_fallback:
                fallback_urls[rid] = url
                fallback_keys[rid] = key
            else:
                previews[rid] = _PosterPreview(url=url, source=source)
                primary_keys[rid] = key

        return {
            rid: preview._replace(
                fallback_url=fallback_urls.get(rid),
                asset_key=_poster_asset_key(primary_keys[rid], fallback_keys.get(rid))
                + (f"|rev:{thumbnail_generation}" if preview.source == "thumbnail" and thumbnail_generation else ""),
                refresh_at_ms=refresh_at_ms,
            )
            for rid, preview in previews.items()
        }


def _poster_fields(previews: dict[int, _PosterPreview], recording_id: int) -> _PosterFields:
    preview = previews.get(recording_id)
    if not preview:
        return {
            "poster_url": None,
            "poster_source": None,
            "poster_fallback_url": None,
            "poster_asset_key": None,
            "poster_refresh_at_ms": None,
        }
    return {
        "poster_url": preview.url,
        "poster_source": preview.source,
        "poster_fallback_url": preview.fallback_url,
        "poster_asset_key": preview.asset_key or None,
        "poster_refresh_at_ms": preview.refresh_at_ms,
    }


async def _storage_file_info(storage_key: str | None) -> dict[str, Any]:
    """Return ``{path, exists, size_mb}`` for a storage key (None ⇒ empty dict)."""
    if not storage_key:
        return {}
    from file_storage.factory import get_storage_backend

    storage = get_storage_backend()
    try:
        size = await storage.get_size(storage_key)
    except FileNotFoundError:
        return {"path": storage_key, "exists": False, "size_mb": None}
    return {"path": storage_key, "exists": True, "size_mb": round(size / (1024 * 1024), 2)}


# ============================================================================
# CRUD Endpoints
# ============================================================================


@router.get("", response_model=RecordingListResponse)
async def list_recordings(
    search: str | None = Query(None, description="Search substring in display_name (case-insensitive)"),
    template_ids_query: list[int] = Query(
        default=[],
        alias="template_id",
        description="Filter by template IDs (repeat param: ?template_id=1&template_id=2)",
    ),
    source_ids_query: list[int] = Query(
        default=[],
        alias="source_id",
        description="Filter by source IDs (repeat param: ?source_id=1&source_id=2)",
    ),
    status_filter: list[ProcessingStatus] = Query(
        default=[],
        description="Filter by statuses (repeat param: ?status=READY&status=PROCESSING)",
        alias="status",
    ),
    failed: bool | None = Query(None, description="Only failed recordings"),
    operational_state: OperationalState | None = Query(None),
    include_posters: bool = Query(True, description="Include signed poster URLs"),
    is_mapped: bool | None = Query(None, description="Filter by is_mapped (true/false/null=all)"),
    include_blank: bool = Query(False, description="Include blank records (short/small)"),
    include_deleted: bool = Query(False, description="Include deleted recordings"),
    from_date: str | None = Query(None, description="Filter: start_time >= from_date (YYYY-MM-DD)"),
    to_date: str | None = Query(None, description="Filter: start_time <= to_date (YYYY-MM-DD)"),
    sort_by: Literal["created_at", "updated_at", "start_time", "display_name", "status", "view_count"] = Query(
        "start_time", description="Sort field (created_at, updated_at, start_time, display_name, status, view_count)"
    ),
    sort_order: Literal["asc", "desc"] = Query("desc", description="Sort direction"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    compact: bool = Query(
        False,
        description="Omit per-stage pipeline detail from list items (lighter JSON for grid views)",
    ),
    ctx: ServiceContext = Depends(get_service_context),
):
    """Get paginated list of recordings with filtering, search and sorting."""
    # Parse date strings to datetime
    from_dt = None
    to_dt = None

    if from_date:
        from utils.date_utils import InvalidDateFormatError, parse_from_date_to_datetime

        try:
            from_dt = parse_from_date_to_datetime(from_date)
        except InvalidDateFormatError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    if to_date:
        from utils.date_utils import InvalidDateFormatError, parse_to_date_to_datetime

        try:
            to_dt = parse_to_date_to_datetime(to_date)
        except InvalidDateFormatError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    recording_repo = RecordingRepository(ctx.session)
    statuses_str: list[str] | None = [s.value for s in status_filter] if status_filter else None
    template_ids = sorted({i for i in template_ids_query if i > 0}) or None
    source_ids = sorted({i for i in source_ids_query if i > 0}) or None
    from api.observability import track_handler_section

    with track_handler_section("recordings_list_db"):
        recordings, total = await recording_repo.list_filtered(
            ctx.user_id,
            template_ids=template_ids,
            source_ids=source_ids,
            statuses=statuses_str,
            failed=failed,
            operational_state=operational_state,
            is_mapped=is_mapped,
            exclude_blank=not include_blank,
            include_deleted=include_deleted,
            from_dt=from_dt,
            to_dt=to_dt,
            search=search,
            sort_by=sort_by,
            sort_order=sort_order,
            page=page,
            per_page=per_page,
            include_processing_stages=not compact,
        )

    total_pages = (total + per_page - 1) // per_page if total > 0 else 1

    poster_urls = await _poster_urls(ctx.session, ctx.user_id, recordings) if include_posters else {}
    from api.services.retention import effective_retention_exempt, template_retention_flags

    retention_flags = await template_retention_flags(ctx.session, recordings)

    items = []
    for r in recordings:
        items.append(
            RecordingListItem(
                **_poster_fields(poster_urls, r.id),
                id=r.id,
                display_name=r.display_name,
                start_time=r.start_time,
                duration=display_duration_seconds(r),
                status=r.status,
                failed=r.failed,
                failed_at_stage=r.failed_at_stage,
                is_mapped=r.is_mapped,
                on_pause=r.on_pause,
                on_air=r.on_air,
                template_id=r.template_id,
                template_name=r.template.name if r.template else None,
                source=_build_source_info(r),
                uploads=_build_uploads_dict(r.outputs),
                processing_stages=_build_processing_stages(r.processing_stages) if not compact else [],
                deleted=r.deleted,
                deleted_at=r.deleted_at,
                delete_state=r.delete_state,
                deletion_reason=r.deletion_reason,
                soft_deleted_at=r.soft_deleted_at,
                hard_delete_at=r.hard_delete_at,
                expire_at=r.expire_at,
                retention_exempt=r.retention_exempt,
                retention_exempt_effective=effective_retention_exempt(
                    r.retention_exempt, retention_flags.get(r.id, False)
                ),
                share_token=r.share_token,
                share_enabled=bool(r.share_enabled),
                share_stats=build_share_stats_summary(r),
                view_count=r.share_view_count or 0,
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


@router.post("/export")
async def export_recordings(
    data: ExportRecordingsRequest,
    ctx: ServiceContext = Depends(get_service_context),
    _feat: UserInDB = Depends(require_feature("can_export_data")),
):
    """Export recordings in JSON, CSV, or XLSX format with filters."""
    recording_ids = await _resolve_recording_ids(
        data.recording_ids,
        data.filters,
        data.limit,
        ctx,
    )
    include_deleted = data.filters.include_deleted if data.filters else False
    recording_repo = RecordingRepository(ctx.session)
    recordings_map = await recording_repo.get_by_ids(recording_ids, ctx.user_id, include_deleted=include_deleted)
    recordings = [recordings_map[rid] for rid in recording_ids if rid in recordings_map]

    platforms = _collect_platforms_from_recordings(recordings)
    questions_by_id: dict[int, list[str] | None] = {}
    if data.verbosity == "long":
        from transcription_module.manager import get_transcription_manager

        txn_mgr = get_transcription_manager()
        for r in recordings:
            try:
                active = await txn_mgr.get_active_extracted(r.id, r.owner.user_slug)
                q = active.get("questions") if active else None
                questions_by_id[r.id] = q if isinstance(q, list) else None
            except Exception:
                questions_by_id[r.id] = None
    rows = [
        _build_export_row(
            r, platforms, data.verbosity, questions=questions_by_id.get(r.id) if data.verbosity == "long" else None
        )
        for r in recordings
    ]
    columns = _get_export_column_order(platforms, data.verbosity)

    timestamp = datetime.now(UTC).strftime("%Y-%m-%d_%H%M%S")
    filename_base = f"recordings_export_{timestamp}"

    logger.info(f"Export | {format_details(total=len(rows), format=data.format, user=short_user_id(ctx.user_id))}")

    if data.format == "json":
        return {"total": len(rows), "items": rows}

    if data.format == "csv":
        csv_content = _generate_csv(rows, columns)
        return StreamingResponse(
            iter([csv_content.encode("utf-8")]),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename_base}.csv"'},
        )

    if data.format == "xlsx":
        xlsx_bytes = _generate_xlsx_bytes(rows, columns)
        return Response(
            content=xlsx_bytes,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{filename_base}.xlsx"'},
        )

    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid format")


@router.get("/{recording_id}/pipeline-status", response_model=RecordingPipelineStatusResponse)
async def get_recording_pipeline_status(
    recording_id: int,
    ctx: ServiceContext = Depends(get_service_context),
) -> RecordingPipelineStatusResponse:
    """Lightweight pipeline state for polling without loading transcription artifacts from storage."""
    recording_repo = RecordingRepository(ctx.session)
    recording = await recording_repo.get_by_id(recording_id, ctx.user_id)
    if not recording:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Recording {recording_id} not found or you don't have access",
        )
    return RecordingPipelineStatusResponse(
        id=recording.id,
        status=recording.status,
        on_air=bool(recording.on_air),
        on_pause=bool(recording.on_pause),
        failed=bool(recording.failed),
        failed_at_stage=recording.failed_at_stage,
        failed_reason=recording.failed_reason,
        processing_stages=_build_processing_stages(recording.processing_stages),
    )


@router.get("/{recording_id}/media")
async def get_recording_media(
    recording_id: int,
    media_kind: Literal["original", "processed"] = Query(
        "processed",
        alias="type",
        description="original = source/local file; processed = pipeline output when present",
    ),
    download: bool = Query(False, description="Return an attachment URL instead of inline playback"),
    ctx: ServiceContext = Depends(get_service_context),
) -> dict:
    """Return a time-limited presigned URL for direct video streaming.

    The frontend should plug the ``url`` into ``<video src={url}>`` — the browser
    will use HTTP Range requests against Object Storage natively, with no API
    proxying. The URL expires after ``expires_in`` seconds, after which the
    frontend can simply refetch this endpoint.

    ``download=true`` adds ``Content-Disposition: attachment`` to the presigned
    URL so the browser saves the file instead of playing it, letting a large
    recording go straight from Object Storage to disk without passing through
    the API or the page's memory.
    """
    from config.settings import get_settings
    from file_storage.factory import get_storage_backend

    recording_repo = RecordingRepository(ctx.session)
    recording = await recording_repo.get_by_id(recording_id, ctx.user_id)
    if not recording:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Recording {recording_id} not found or you don't have access",
        )

    storage_key = _recording_video_storage_key(recording, media_kind)
    if not storage_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Video file not available for this recording",
        )

    storage = get_storage_backend()
    expires_in = get_settings().storage.s3_presign_expires
    dl_filename = f"recording-{recording.id}.mp4" if download else None
    async with storage.shared_operations():
        url = await storage.presigned_url(storage_key, expires_in=expires_in, download_filename=dl_filename)
    return {"url": url, "expires_in": expires_in}


@router.post("/{recording_id}/poster", status_code=status.HTTP_202_ACCEPTED)
async def generate_recording_poster(
    recording_id: int,
    ctx: ServiceContext = Depends(get_service_context),
) -> dict:
    """Ensure a poster frame exists for this recording.

    Idempotent. The list response hands out a poster URL built by convention, so
    a client discovers a missing poster by the image failing to load and calls
    this once; the frame then exists for every later page view. That keeps the
    feature working for recordings that predate it without a backfill pass.
    """
    from api.tasks.processing import generate_poster

    recording_repo = RecordingRepository(ctx.session)
    recording = await recording_repo.get_by_id(recording_id, ctx.user_id)
    if not recording:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Recording {recording_id} not found or you don't have access",
        )

    poster_key = _recording_poster_storage_key(recording)
    if not poster_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Recording has no video to take a poster frame from",
        )

    from file_storage.factory import get_storage_backend

    if await get_storage_backend().exists(poster_key):
        return {"status": "ready"}

    generate_poster.delay(recording_id, ctx.user_id)
    return {"status": "queued"}


@router.get("/{recording_id}/source-extras", response_model=SourceExtrasResponse)
async def get_recording_source_extras(
    recording_id: int,
    ctx: ServiceContext = Depends(get_service_context),
) -> SourceExtrasResponse:
    """List companion files saved next to the source video, with download URLs.

    Currently produced by MTS Link ingestion: the session chat log and any materials
    uploaded to the event. Returns time-limited URLs rather than streaming, so a large
    presentation goes straight from storage to the browser.
    """
    from api.helpers.source_extras import list_source_extras

    recording_repo = RecordingRepository(ctx.session)
    recording = await recording_repo.get_by_id(recording_id, ctx.user_id)
    if not recording:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Recording {recording_id} not found or you don't have access",
        )

    return await list_source_extras(recording)


@router.get("/{recording_id}/files/{file_type}")
async def download_recording_artifact(
    recording_id: int,
    file_type: Literal["srt", "vtt", "transcript_json", "transcript_txt", "transcript_words", "description_txt"],
    ctx: ServiceContext = Depends(get_service_context),
) -> StreamingResponse:
    """Download subtitles or transcription artifacts (attachments).

    Small text artifacts are loaded from storage and streamed back; we don't redirect
    to a presigned URL here because callers expect a Content-Disposition attachment
    response (browser downloads dialog).
    """
    from file_storage.factory import get_storage_backend
    from file_storage.path_builder import StoragePathBuilder, to_storage_key

    recording_repo = RecordingRepository(ctx.session)
    recording = await recording_repo.get_by_id(recording_id, ctx.user_id)
    if not recording:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Recording {recording_id} not found or you don't have access",
        )

    user_slug = recording.owner.user_slug
    builder = StoragePathBuilder()
    tx_dir = builder.transcription_dir(user_slug, recording_id)
    cache_dir = builder.transcription_cache_dir(user_slug, recording_id)

    stem = f"recording-{recording_id}"

    if file_type == "srt":
        key = to_storage_key(cache_dir / "subtitles.srt")
        media_type = "application/x-subrip"
        attachment_name = f"{stem}.srt"
    elif file_type == "vtt":
        key = to_storage_key(cache_dir / "subtitles.vtt")
        media_type = "text/vtt"
        attachment_name = f"{stem}.vtt"
    elif file_type == "transcript_json":
        key = to_storage_key(tx_dir / "master.json")
        media_type = "application/json"
        attachment_name = f"{stem}_transcript.json"
    elif file_type == "transcript_txt":
        key = to_storage_key(cache_dir / "segments.txt")
        media_type = "text/plain; charset=utf-8"
        attachment_name = f"{stem}_transcript.txt"
    elif file_type == "transcript_words":
        key = to_storage_key(cache_dir / "words.txt")
        media_type = "text/plain; charset=utf-8"
        attachment_name = f"{stem}_words.txt"
    else:
        # description_txt: render title + description from metadata templates
        from api.helpers.template_renderer import TemplateRenderer, compute_metadata_preview
        from api.services.config_resolver import ConfigResolver
        from transcription_module.manager import get_transcription_manager

        config_resolver = ConfigResolver(ctx.session)
        config_data = await config_resolver.get_base_config_for_edit(recording, ctx.user_id)
        meta = config_data.get("metadata_config") or {}
        title_t = meta.get("title_template")
        desc_t = meta.get("description_template")

        if not title_t and not desc_t:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No metadata template configured for this recording",
            )

        extracted = None
        owner = getattr(recording, "owner", None)
        if owner and getattr(owner, "user_slug", None):
            try:
                extracted = await get_transcription_manager().get_active_extracted(recording.id, owner.user_slug)
            except Exception as exc:
                logger.debug("Could not load extracted for description_txt: %s", exc)

        render_ctx = TemplateRenderer.prepare_recording_context(recording, extracted_data=extracted)
        _, _, _, rendered = compute_metadata_preview(
            title_template=title_t,
            description_template=desc_t,
            folder_path_template=None,
            filename_template=None,
            context=render_ctx,
        )

        title = rendered.get("title") or ""
        description = rendered.get("description") or ""
        text = f"Заголовок:\n{title}\n\nОписание:\n{description}"

        return StreamingResponse(
            iter([text.encode("utf-8")]),
            media_type="text/plain; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{stem}_description.txt"'},
        )

    storage = get_storage_backend()
    if not await storage.exists(key):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    content = await storage.load(key)
    return StreamingResponse(
        iter([content]),
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{attachment_name}"'},
    )


@router.get("/upload-policy")
async def get_upload_policy(_ctx: ServiceContext = Depends(get_service_context)) -> dict[str, Any]:
    """Expose upload limits so the file picker matches the active backend configuration."""
    storage = get_settings().storage
    return {
        "max_upload_bytes": min(storage.max_upload_size_mb, 5000) * 1024 * 1024,
        "extensions": sorted(storage_video_ingress_suffixes()),
        "resume_hours": SESSION_TTL_SECONDS // 3600,
    }


@router.get("/{recording_id}", response_model=RecordingListItem | DetailedRecordingResponse)
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

    from api.services.retention import effective_retention_exempt, template_retention_flags

    retention_flags = await template_retention_flags(ctx.session, [recording])
    retention_effective = effective_retention_exempt(
        recording.retention_exempt, retention_flags.get(recording.id, False)
    )

    if not detailed:
        return RecordingListItem(
            **_poster_fields(await _poster_urls(ctx.session, ctx.user_id, [recording]), recording.id),
            id=recording.id,
            display_name=recording.display_name,
            start_time=recording.start_time,
            duration=display_duration_seconds(recording),
            status=recording.status,
            failed=recording.failed,
            failed_at_stage=recording.failed_at_stage,
            is_mapped=recording.is_mapped,
            on_pause=recording.on_pause,
            on_air=recording.on_air,
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
            retention_exempt=recording.retention_exempt,
            retention_exempt_effective=retention_effective,
            share_token=recording.share_token,
            share_enabled=bool(recording.share_enabled),
            share_stats=build_share_stats_summary(recording),
            created_at=recording.created_at,
            updated_at=recording.updated_at,
        )

    # Detailed information
    from transcription_module.manager import get_transcription_manager

    transcription_manager = get_transcription_manager()

    # Base information (common fields)
    base_data: dict[str, Any] = {
        "id": recording.id,
        "display_name": recording.display_name,
        "start_time": recording.start_time,
        "duration": display_duration_seconds(recording),
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
                started_at=output.started_at,
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
                started_at=stage.started_at,
                completed_at=stage.completed_at,
            )
            for stage in recording.processing_stages
        ],
        "on_pause": recording.on_pause,
        "on_air": recording.on_air,
        "pause_requested_at": recording.pause_requested_at,
        "failed": recording.failed,
        "failed_at": recording.failed_at,
        "failed_reason": recording.failed_reason,
        "failed_at_stage": recording.failed_at_stage,
        "download_started_at": recording.download_started_at,
        "downloaded_at": recording.downloaded_at,
        "pipeline_started_at": recording.pipeline_started_at,
        "pipeline_completed_at": recording.pipeline_completed_at,
        "pipeline_duration_seconds": recording.pipeline_duration_seconds,
        "video_file_size": recording.video_file_size,
        "deleted": recording.deleted,
        "deleted_at": recording.deleted_at,
        "delete_state": recording.delete_state,
        "deletion_reason": recording.deletion_reason,
        "soft_deleted_at": recording.soft_deleted_at,
        "hard_delete_at": recording.hard_delete_at,
        "expire_at": recording.expire_at,
        "retention_exempt": recording.retention_exempt,
        "retention_exempt_effective": retention_effective,
        "share_token": recording.share_token,
        "share_enabled": bool(recording.share_enabled),
        "share_stats": build_share_stats_for_detail(recording),
        "allow_video_download": recording.allow_video_download,
        "allow_files_download": recording.allow_files_download,
        "created_at": recording.created_at,
        "updated_at": recording.updated_at,
    }

    # Video files (storage keys, looked up via backend)
    media_kinds: list[tuple[str, str]] = []
    if recording.local_video_path:
        media_kinds.append(("original", recording.local_video_path))
    if recording.processed_video_path:
        media_kinds.append(("processed", recording.processed_video_path))

    media_info, audio_info = await asyncio.gather(
        asyncio.gather(*(_storage_file_info(path) for _kind, path in media_kinds)),
        _storage_file_info(recording.processed_audio_path),
    )
    videos = {kind: info for (kind, _path), info in zip(media_kinds, media_info, strict=True)}

    # Get user_slug for transcription paths
    user_slug = recording.owner.user_slug

    # Pre-compute storage keys for transcription artifacts (used both for "files" map and for size lookups).
    from file_storage.factory import get_storage_backend
    from file_storage.path_builder import to_storage_key

    storage = get_storage_backend()
    tx_dir = transcription_manager.get_dir(recording_id, user_slug)
    master_key = to_storage_key(tx_dir / "master.json")
    segments_key = to_storage_key(tx_dir / "cache" / "segments.txt")
    words_key = to_storage_key(tx_dir / "cache" / "words.txt")

    # Transcription (hide _metadata and model from user)
    if await transcription_manager.has_master(recording_id, user_slug):
        try:
            master = await transcription_manager.load_master(recording_id, user_slug)
            transcription_data = {
                "exists": True,
                "created_at": master.get("created_at"),
                "language": master.get("language"),
                # Hide model from user (exists in _metadata for admin)
                "stats": master.get("stats"),
                "files": {
                    "master": master_key,
                    "segments_txt": segments_key,
                    "words_txt": words_key,
                },
            }
        except Exception as e:
            logger.warning(f"Failed to load transcription | {format_details(rec=recording_id, error=str(e))}")
            transcription_data = {"exists": False}
    else:
        transcription_data = {"exists": False}

    # Topics (all versions) from extracted.json - hide _metadata from user
    if await transcription_manager.has_extracted(recording_id, user_slug):
        try:
            extracted_file = await transcription_manager.load_extracted(recording_id, user_slug)

            # Clean versions from administrative metadata
            versions_clean = [
                {k: v for k, v in version.items() if k != "_metadata"} for version in extracted_file.get("versions", [])
            ]

            topics_data = {
                "exists": True,
                "active_version": extracted_file.get("active_version"),
                "versions": versions_clean,
            }
        except Exception as e:
            logger.warning(f"Failed to load extracted | {format_details(rec=recording_id, error=str(e))}")
            topics_data = {"exists": False}
    else:
        topics_data = {"exists": False}

    # Subtitles
    subtitle_keys = {fmt: to_storage_key(tx_dir / "cache" / f"subtitles.{fmt}") for fmt in ("srt", "vtt")}

    async def subtitle_info(key: str) -> dict[str, Any]:
        try:
            size_bytes = await storage.get_size(key)
        except FileNotFoundError:
            return {"path": None, "exists": False, "size_kb": None}
        return {"path": key, "exists": True, "size_kb": round(size_bytes / 1024, 2)}

    subtitle_values = await asyncio.gather(*(subtitle_info(key) for key in subtitle_keys.values()))
    subtitles = dict(zip(subtitle_keys, subtitle_values, strict=True))

    # Processing stages detailed (with metadata and timestamps)
    processing_stages_detailed = None
    if hasattr(recording, "processing_stages") and recording.processing_stages:
        processing_stages_detailed = [
            {
                "type": stage.stage_type.value if hasattr(stage.stage_type, "value") else str(stage.stage_type),
                "status": stage.status.value if hasattr(stage.status, "value") else str(stage.status),
                "created_at": stage.created_at.isoformat() if stage.created_at else None,
                "started_at": stage.started_at.isoformat() if stage.started_at else None,
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
                "started_at": target.started_at.isoformat() if target.started_at else None,
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

    from api.repositories.channel_repo import ChannelRepository
    from api.repositories.playlist_repo import PlaylistRepository
    from api.schemas.channel import ChannelSummary
    from api.schemas.playlist import PlaylistSummary

    playlist_rows = await PlaylistRepository(ctx.session).summaries_for_recording(recording.id, ctx.user_id)
    playlists = [PlaylistSummary(id=p.id, name=p.name, item_id=item_id) for p, item_id in playlist_rows]
    channel_rows = await ChannelRepository(ctx.session).summaries_for_recording(recording.id, ctx.user_id)
    channels = [ChannelSummary(id=ch.id, name=ch.name, slug=ch.slug, membership_id=mid) for ch, mid in channel_rows]

    # Create response model
    return DetailedRecordingResponse(
        **base_data,
        playlists=playlists,
        channels=channels,
        videos=videos if videos else None,
        audio=audio_info if audio_info else None,
        transcription=transcription_data,
        topics=topics_data,
        subtitles=subtitles,
        processing_stages_detailed=processing_stages_detailed,
        uploads=uploads if uploads else None,
    )


@router.patch("/{recording_id}", response_model=RecordingListItem)
async def update_recording(
    recording_id: int,
    data: RecordingUpdateRequest,
    ctx: ServiceContext = Depends(get_service_context),
) -> RecordingListItem:
    """Partially update recording metadata (e.g. display_name)."""
    recording_repo = RecordingRepository(ctx.session)

    recording = await recording_repo.get_by_id(recording_id, ctx.user_id)
    if not recording:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Recording {recording_id} not found")

    updates = data.model_dump(exclude_unset=True)
    exempt = updates.pop("retention_exempt", None)
    for field, value in updates.items():
        setattr(recording, field, value)
    if "retention_exempt" in data.model_fields_set:
        user_config = await UserConfigRepository(ctx.session).get_effective_config(ctx.user_id)
        await recording_repo.assign_retention_exempt(
            recording, exempt if isinstance(exempt, bool) else None, user_config
        )

    await recording_repo.update(recording)
    await ctx.session.commit()

    logger.info(f"Updated recording metadata | {format_details(rec=recording_id)}")

    from api.services.retention import effective_retention_exempt, template_retention_flags

    retention_flags = await template_retention_flags(ctx.session, [recording])
    retention_effective = effective_retention_exempt(
        recording.retention_exempt, retention_flags.get(recording.id, False)
    )

    return RecordingListItem(
        **_poster_fields(await _poster_urls(ctx.session, ctx.user_id, [recording]), recording.id),
        id=recording.id,
        display_name=recording.display_name,
        start_time=recording.start_time,
        duration=display_duration_seconds(recording),
        status=recording.status,
        failed=recording.failed,
        failed_at_stage=recording.failed_at_stage,
        is_mapped=recording.is_mapped,
        on_pause=recording.on_pause,
        on_air=recording.on_air,
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
        retention_exempt=recording.retention_exempt,
        retention_exempt_effective=retention_effective,
        share_token=recording.share_token,
        share_enabled=bool(recording.share_enabled),
        share_stats=build_share_stats_summary(recording),
        created_at=recording.created_at,
        updated_at=recording.updated_at,
    )


@router.post("", response_model=LocalRecordingUploadResponse)
async def add_local_recording(
    file: UploadFile = File(...),
    display_name: str = Query(..., min_length=1, max_length=500, description="Recording name"),
    ctx: ServiceContext = Depends(get_service_context),
    _quota: UserInDB = Depends(check_user_quotas),
    auto_run: bool = False,
) -> LocalRecordingUploadResponse:
    """Upload and create local video recording."""
    storage_builder = StoragePathBuilder()
    filename = file.filename or "uploaded_video.mp4"
    storage_settings = get_settings().storage
    allowed_suffixes = storage_video_ingress_suffixes()

    try:
        source_suffix = strict_suffix_from_source_name(filename, allowed_suffixes)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    display_name = collapse_whitespace(display_name)
    if not display_name:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Recording name is required")

    max_upload_bytes = min(storage_settings.max_upload_size_mb, 5000) * 1024 * 1024
    temp_path = storage_builder.create_temp_file(suffix=source_suffix)
    try:
        total_size = 0
        with temp_path.open("wb") as f:
            while chunk := await file.read(1024 * 1024):
                total_size += len(chunk)
                if total_size > max_upload_bytes:
                    raise HTTPException(
                        status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                        detail=f"Video exceeds the {max_upload_bytes // (1024 * 1024)} MiB upload limit",
                    )
                f.write(chunk)

        return await _finalize_local_video(
            temp_path,
            filename,
            display_name,
            ctx,
            auto_run=auto_run,
            source_suffix=source_suffix,
        )
    finally:
        await file.close()
        temp_path.unlink(missing_ok=True)


async def _finalize_local_video(
    temp_path: Path,
    filename: str,
    display_name: str,
    ctx: ServiceContext,
    *,
    auto_run: bool,
    source_suffix: str,
    source_key: str | None = None,
) -> LocalRecordingUploadResponse:
    """Validate a complete temporary video and save one recording."""
    from file_storage.factory import get_storage_backend
    from file_storage.path_builder import to_storage_key

    if not temp_path.exists():
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Upload data is no longer available")
    actual_size = temp_path.stat().st_size
    if not ingress_validate_saved_media(
        temp_path, actual_size, actual_size, filename, get_settings().storage.supported_video_formats
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or unsupported media file (ingress whitelist / container sniff)",
        )
    file_duration = positive_duration_seconds(await AudioDetector().get_duration_seconds(str(temp_path)))
    if file_duration is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Could not read video duration")

    user_result = await ctx.session.execute(select(UserModel).where(UserModel.id == ctx.user_id))
    user = user_result.scalar_one()
    allowed, quota_error = await QuotaService(ctx.session).check_storage_quota(
        ctx.user_id, user.user_slug, incoming_bytes=actual_size
    )
    if not allowed:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=quota_error)

    recording_repo = RecordingRepository(ctx.session)
    source_key = source_key or f"local_{ctx.user_id}_{datetime.now().timestamp()}"
    user_config = await UserConfigRepository(ctx.session).get_effective_config(ctx.user_id)
    target_key: str | None = None
    committed = False
    try:
        created_recording = await recording_repo.create(
            user_id=ctx.user_id,
            input_source_id=None,
            display_name=display_name,
            start_time=datetime.now(),
            duration=max(1, int(file_duration)),
            source_type=SourceType.LOCAL_FILE,
            source_key=source_key,
            source_metadata={"uploaded_via_api": True, "original_filename": filename},
            user_config=user_config,
            status=ProcessingStatus.DOWNLOADED,
            local_video_path="",
            video_file_size=actual_size,
        )
        await ctx.session.flush()
        target_key = to_storage_key(
            StoragePathBuilder().recording_source(user.user_slug, created_recording.id, suffix=source_suffix)
        )
        await get_storage_backend().save_file(target_key, temp_path)
        created_recording.local_video_path = target_key
        await ctx.session.commit()
        committed = True
        await _track_recordings_created(ctx, [created_recording.id])
        task_id = None
        if auto_run:
            try:
                task_id = await _auto_run_recording(created_recording.id, ctx.user_id)
            except Exception:
                logger.exception("Uploaded video saved but auto-run could not be queued")
        return LocalRecordingUploadResponse(
            success=True,
            recording_id=created_recording.id,
            display_name=created_recording.display_name,
            local_video_path=target_key,
            task_id=task_id,
            auto_run_requested=auto_run,
        )
    except Exception:
        await ctx.session.rollback()
        if not committed and target_key:
            try:
                await get_storage_backend().delete(target_key)
            except Exception:
                logger.warning("Failed to clean up uploaded video after a database error")
        raise


@router.post("/uploads", status_code=status.HTTP_201_CREATED)
async def start_resumable_upload(
    data: StartResumableUploadRequest,
    ctx: ServiceContext = Depends(get_service_context),
    _quota: UserInDB = Depends(check_user_quotas),
) -> dict[str, Any]:
    """Create an owner-scoped temporary upload; completed files still use normal ingress validation."""
    try:
        strict_suffix_from_source_name(data.filename, storage_video_ingress_suffixes())
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    max_bytes = min(get_settings().storage.max_upload_size_mb, 5000) * 1024 * 1024
    if data.size > max_bytes:
        raise HTTPException(status_code=status.HTTP_413_CONTENT_TOO_LARGE, detail="Video exceeds the upload limit")
    return create_session(ctx.user_id, data.filename, data.size, data.display_name, data.auto_run, data.fingerprint)


@router.get("/uploads/{upload_id}")
async def get_resumable_upload(upload_id: str, ctx: ServiceContext = Depends(get_service_context)) -> dict[str, Any]:
    data, part_path = read_session(upload_id, ctx.user_id)
    return session_status(data, part_path)


@router.patch("/uploads/{upload_id}")
async def update_resumable_upload(
    upload_id: str,
    settings: ResumableUploadSettingsRequest,
    ctx: ServiceContext = Depends(get_service_context),
) -> dict[str, Any]:
    with lock_upload(upload_id):
        data, part_path = read_session(upload_id, ctx.user_id)
        if data.get("recording_id"):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Upload already completed")
        data.update(display_name=settings.display_name, auto_run=settings.auto_run, updated_at=time.time())
        save_session(upload_id, data)
        return session_status(data, part_path)


@router.put("/uploads/{upload_id}/chunk")
async def append_resumable_chunk(
    upload_id: str,
    request: Request,
    offset: int = Query(..., ge=0),
    ctx: ServiceContext = Depends(get_service_context),
) -> dict[str, Any]:
    """Append at the exact server offset; a partial request remains resumable."""
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            too_large = int(content_length) > CHUNK_BYTES
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid chunk length") from exc
        if too_large:
            raise HTTPException(status_code=status.HTTP_413_CONTENT_TOO_LARGE, detail="Chunk is too large")
    with lock_upload(upload_id):
        data, part_path = read_session(upload_id, ctx.user_id)
        if data.get("recording_id"):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Upload already completed")
        current = part_path.stat().st_size if part_path.exists() else 0
        if current != offset:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Expected offset {current}")
        written = 0
        with part_path.open("ab") as output:
            async for chunk in request.stream():
                if written + len(chunk) > CHUNK_BYTES or current + written + len(chunk) > data["size"]:
                    output.truncate(current)
                    raise HTTPException(
                        status_code=status.HTTP_413_CONTENT_TOO_LARGE, detail="Chunk exceeds upload size"
                    )
                output.write(chunk)
                written += len(chunk)
        if not written:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty chunk")
        data["updated_at"] = time.time()
        save_session(upload_id, data)
        return session_status(data, part_path)


@router.post("/uploads/{upload_id}/complete", response_model=LocalRecordingUploadResponse)
async def complete_resumable_upload(
    upload_id: str,
    ctx: ServiceContext = Depends(get_service_context),
    current_user: UserInDB = Depends(get_current_user),
) -> LocalRecordingUploadResponse:
    """Finish a complete temporary file once, even when a client retries the response."""
    with lock_upload(upload_id):
        data, part_path = read_session(upload_id, ctx.user_id)
        source_key = f"local_{ctx.user_id}_{upload_id}"
        existing = await RecordingRepository(ctx.session).find_by_source_key(
            ctx.user_id, SourceType.LOCAL_FILE, source_key, require_start_time_in_lookup=False
        )
        if existing:
            if not existing.local_video_path:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Recording has no saved video")
            return LocalRecordingUploadResponse(
                success=True,
                recording_id=existing.id,
                display_name=existing.display_name,
                local_video_path=existing.local_video_path,
                task_id=data.get("task_id"),
                auto_run_requested=data["auto_run"],
            )
        await check_user_quotas(current_user, ctx.session)
        if not part_path.exists() or part_path.stat().st_size != data["size"]:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Upload is incomplete")
        suffix = strict_suffix_from_source_name(data["filename"], storage_video_ingress_suffixes())
        result = await _finalize_local_video(
            part_path,
            data["filename"],
            data["display_name"],
            ctx,
            auto_run=data["auto_run"],
            source_suffix=suffix,
            source_key=source_key,
        )
        data.update(recording_id=result.recording_id, task_id=result.task_id, updated_at=time.time())
        save_session(upload_id, data)
        part_path.unlink(missing_ok=True)
        return result


# ============================================================================
# Add by URL Endpoints
# ============================================================================


@router.post("/add-disk-link", response_model=AddPublicDiskLinkResponse, status_code=status.HTTP_201_CREATED)
async def add_public_disk_link(
    data: AddPublicDiskLinkRequest,
    ctx: ServiceContext = Depends(get_service_context),
) -> AddPublicDiskLinkResponse:
    """Save a public Disk link as a reusable source and queue its first sync."""
    from api.tasks.sync_tasks import sync_single_source_task
    from yandex_disk_module.client import YandexDiskClient

    try:
        meta = await YandexDiskClient().get_public_meta(data.public_url)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Could not read public Disk link"
        ) from exc
    if data.resource_type is not None and meta.get("type") != data.resource_type:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"This Disk link points to a {meta.get('type') or 'different resource'}, not the selected type",
        )

    repo = InputSourceRepository(ctx.session)
    sources = await repo.find_by_user(ctx.user_id)
    source = next(
        (
            item
            for item in sources
            if item.source_type == "YANDEX_DISK"
            and (item.config or {}).get("public_url") == data.public_url
            and not (item.config or {}).get("file_pattern")
            and (meta.get("type") != "dir" or (item.config or {}).get("recursive", True))
        ),
        None,
    )
    reused = source is not None
    if source and not source.is_active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Disk source is inactive. Enable it in Sources."
        )
    if source is None:
        duplicate = await repo.find_duplicate(ctx.user_id, data.name, "YANDEX_DISK", None)
        if duplicate:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Source name is already used")
        source = await repo.create(
            user_id=ctx.user_id,
            name=data.name,
            source_type="YANDEX_DISK",
            config={"public_url": data.public_url, "recursive": True},
        )
        await ctx.session.commit()

    try:
        task = sync_single_source_task.apply_async(
            kwargs={"source_id": source.id, "user_id": ctx.user_id, "auto_run": data.auto_run}
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Disk source was saved, but sync could not be queued. Retry this link.",
        ) from exc
    return AddPublicDiskLinkResponse(source_id=source.id, task_id=task.id, reused=reused)


@router.post("/disk-preview")
async def preview_public_disk_link(
    data: PublicDiskLinkRequest,
    _ctx: ServiceContext = Depends(get_service_context),
) -> dict[str, Any]:
    """Show whether a public Disk link is one video or a folder, before adding it."""
    from yandex_disk_module.client import YandexDiskClient

    client = YandexDiskClient()
    try:
        meta = await client.get_public_meta(data.public_url)
        kind = meta.get("type")
        if kind not in {"file", "dir"}:
            raise ValueError("Unsupported Disk resource type")
        videos = await client.list_public_video_files(data.public_url)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Could not inspect public Disk link"
        ) from exc
    return {
        "resource_type": kind,
        "name": meta.get("name") or "Yandex Disk",
        "video_count": len(videos),
        "sample_names": [item.get("name") or "Video" for item in videos[:5]],
    }


@router.post("/playlist-preview")
async def preview_playlist(
    data: FormatsPreviewRequest,
    _ctx: ServiceContext = Depends(get_service_context),
) -> dict[str, Any]:
    """Show playlist size and sample titles before creating any recordings."""
    from video_download_module.platforms.ytdlp.metadata import extract_playlist_entries

    try:
        entries = await extract_playlist_entries(data.url)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Could not inspect playlist"
        ) from exc
    available = [entry for entry in entries if not entry.get("unavailable")]
    return {
        "video_count": len(available),
        "unavailable_count": len(entries) - len(available),
        "sample_titles": [entry.get("title") or "Video" for entry in available[:5]],
    }


@router.post("/formats-preview", response_model=FormatsPreviewResponse)
async def preview_video_formats(
    data: FormatsPreviewRequest,
    _ctx: ServiceContext = Depends(get_service_context),
) -> FormatsPreviewResponse:
    """Return available video formats for a URL without creating a recording.

    Calls yt-dlp with download=False and returns the list of video streams
    sorted by resolution descending. Use this before /add-url to let the user
    pick from actually available qualities.
    """
    from video_download_module.platforms.ytdlp.metadata import extract_available_formats

    try:
        result = await extract_available_formats(data.url)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)) from e

    return FormatsPreviewResponse(**result)


@router.post("/add-url", response_model=AddVideoByUrlResponse, status_code=status.HTTP_201_CREATED)
async def add_video_by_url(
    data: AddVideoByUrlRequest,
    ctx: ServiceContext = Depends(get_service_context),
    _quota: UserInDB = Depends(check_user_quotas),
) -> AddVideoByUrlResponse:
    """Add single video by URL (YouTube, VK, Rutube, etc.).

    Extracts metadata via yt-dlp, creates a Recording, and optionally
    starts the full pipeline (download → process → upload).
    No InputSource or credentials required.
    """
    from video_download_module.platforms.ytdlp.metadata import detect_platform, extract_video_info

    try:
        info = await extract_video_info(data.url)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Failed to extract video info from URL: {e}",
        )

    platform = info.get("platform") or detect_platform(data.url)
    original_title = (collapse_whitespace(info.get("title") or "Unknown") or "Unknown")[:500]
    display_name = (collapse_whitespace(data.display_name or original_title) or original_title)[:500]
    video_id = info.get("id", "")
    duration = info.get("duration") or 0
    video_url = info.get("url") or data.url

    source_key = f"{platform}:{video_id}" if video_id else video_url
    recording_repo = RecordingRepository(ctx.session)
    existing = await recording_repo.find_by_source_key(
        ctx.user_id, SourceType.EXTERNAL_URL, source_key, require_start_time_in_lookup=False
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Video already added as recording #{existing.id}",
        )
    source_metadata = {
        "url": video_url,
        "platform": platform,
        "video_id": video_id,
        "title": original_title,
        "duration": duration,
        "thumbnail": info.get("thumbnail"),
        "uploader": info.get("uploader"),
        "upload_date": info.get("upload_date"),
        "quality": data.quality,
        "format_preference": data.format_preference,
    }

    user_config_repo = UserConfigRepository(ctx.session)
    user_config = await user_config_repo.get_effective_config(ctx.user_id)

    template = None
    if data.template_id:
        from api.repositories.template_repos import RecordingTemplateRepository

        template_repo = RecordingTemplateRepository(ctx.session)
        template = await template_repo.find_by_id(data.template_id, ctx.user_id)
        if template is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")

    recording = await recording_repo.create(
        user_id=ctx.user_id,
        input_source_id=None,
        display_name=display_name,
        start_time=datetime.now(UTC),
        duration=duration,
        source_type=SourceType.EXTERNAL_URL,
        source_key=source_key,
        source_metadata=source_metadata,
        user_config=user_config,
        is_mapped=data.template_id is not None,
    )

    await ctx.session.flush()

    # Bind template if specified
    if data.template_id:
        assert template is not None
        recording.template_id = data.template_id
        recording.is_mapped = True
        await template_repo.increment_usage(template)

    await ctx.session.commit()

    await _track_recordings_created(ctx, [recording.id])

    task_id = None
    if data.auto_run:
        try:
            task_id = await _auto_run_recording(recording.id, ctx.user_id)
        except Exception:
            logger.exception("Video URL saved but auto-run could not be queued")

    logger.info(f"Added video by URL | {format_details(rec=recording.id, platform=platform, auto_run=data.auto_run)}")

    return AddVideoByUrlResponse(
        success=True,
        recording_id=recording.id,
        display_name=display_name,
        platform=platform,
        task_id=task_id,
        message=f"Video added from {platform}" + (" — pipeline started" if task_id else ""),
    )


@router.post("/add-playlist", response_model=AddPlaylistResponse, status_code=status.HTTP_201_CREATED)
async def add_playlist_by_url(
    data: AddPlaylistByUrlRequest,
    ctx: ServiceContext = Depends(get_service_context),
    _quota: UserInDB = Depends(check_user_quotas),
) -> AddPlaylistResponse:
    """Add all videos from a playlist or channel URL.

    Extracts playlist entries via yt-dlp, creates a Recording per video,
    and optionally starts the pipeline for each.
    """
    from video_download_module.platforms.ytdlp.metadata import detect_platform, extract_playlist_entries

    try:
        entries = await extract_playlist_entries(data.url)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Failed to extract playlist from URL: {e}",
        )

    if not entries:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No videos found in playlist",
        )

    platform = detect_platform(data.url)
    recording_repo = RecordingRepository(ctx.session)
    user_config_repo = UserConfigRepository(ctx.session)
    user_config = await user_config_repo.get_effective_config(ctx.user_id)
    remaining_new = await QuotaService(ctx.session).remaining_recordings_quota(ctx.user_id)
    if data.template_id:
        from api.repositories.template_repos import RecordingTemplateRepository

        template = await RecordingTemplateRepository(ctx.session).find_by_id(data.template_id, ctx.user_id)
        if template is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")

    created_recordings: list[dict] = []
    created_count = 0
    updated_count = 0
    failed_count = 0
    task_ids: list[str] = []

    for entry in entries:
        if entry.get("unavailable"):
            failed_count += 1
            continue
        try:
            video_id = entry.get("id", "")
            title = (collapse_whitespace(entry.get("title") or "Unknown") or "Unknown")[:500]
            duration = entry.get("duration") or 0
            video_url = entry.get("url", data.url)
            entry_platform = entry.get("platform", platform)

            source_key = f"{entry_platform}:{video_id}" if video_id else video_url
            if remaining_new is not None and created_count >= remaining_new:
                existing = await recording_repo.find_by_source_key(
                    ctx.user_id, SourceType.EXTERNAL_URL, source_key, require_start_time_in_lookup=False
                )
                if existing is None:
                    failed_count += 1
                    continue
            source_metadata = {
                "url": video_url,
                "platform": entry_platform,
                "video_id": video_id,
                "title": title,
                "duration": duration,
                "quality": data.quality,
                "format_preference": data.format_preference,
                "playlist_url": data.url,
            }

            recording, is_new = await recording_repo.create_or_update(
                user_id=ctx.user_id,
                input_source_id=None,
                display_name=title,
                start_time=datetime.now(UTC),
                duration=duration,
                source_type=SourceType.EXTERNAL_URL,
                source_key=source_key,
                source_metadata=source_metadata,
                user_config=user_config,
                is_mapped=data.template_id is not None,
                template_id=data.template_id,
                require_start_time_in_lookup=False,
            )

            if is_new:
                created_count += 1
            else:
                updated_count += 1

            created_recordings.append(
                {
                    "recording_id": recording.id,
                    "display_name": recording.display_name,
                    "is_new": is_new,
                }
            )

        except Exception as e:
            failed_count += 1
            logger.warning(
                f"Failed to add playlist entry | {format_details(title=entry.get('title', '?'), error=str(e))}"
            )
            continue

    if not created_recordings:
        await ctx.session.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="No playlist videos could be added"
        )

    await ctx.session.commit()

    await _track_recordings_created(ctx, [rec["recording_id"] for rec in created_recordings if rec.get("is_new")])

    # Auto-run all newly created recordings
    if data.auto_run:
        for rec in created_recordings:
            if rec.get("is_new"):
                try:
                    tid = await _auto_run_recording(rec["recording_id"], ctx.user_id)
                    if tid:
                        task_ids.append(tid)
                except Exception as e:
                    logger.warning(f"Failed to auto-run | {format_details(rec=rec['recording_id'], error=str(e))}")

    logger.info(
        f"Added playlist | {format_details(total=len(entries), created=created_count, updated=updated_count, auto_run=data.auto_run)}"
    )

    return AddPlaylistResponse(
        success=True,
        total_videos=len(entries),
        recordings_created=created_count,
        recordings_updated=updated_count,
        recordings_failed=failed_count,
        recordings=created_recordings,
        task_ids=task_ids,
        message=f"Playlist processed: {created_count} new, {updated_count} updated"
        + (f", {len(task_ids)} pipelines started" if task_ids else ""),
    )


async def _auto_run_recording(recording_id: int, user_id: str) -> str | None:
    """Start full pipeline for a recording. Returns task_id or None."""
    from api.tasks.processing import run_recording_task

    task = run_recording_task.apply_async(
        kwargs={
            "recording_id": recording_id,
            "user_id": user_id,
        }
    )
    logger.info(f"Auto-run pipeline | {format_details(rec=recording_id, task=short_task_id(task.id))}")
    return task.id


@bulk_router.post("/bulk/run", response_model=RecordingBulkOperationResponse | BulkProcessDryRunResponse)
async def bulk_run_recordings(
    data: BulkRunRequest,
    dry_run: bool = Query(False, description="Dry-run: show which recordings will be run"),
    ctx: ServiceContext = Depends(get_service_context),
    _feat: UserInDB = Depends(require_feature("can_process_video")),
) -> RecordingBulkOperationResponse | BulkProcessDryRunResponse:
    """Bulk run full pipeline on multiple recordings (async tasks)."""

    if dry_run:
        return await _execute_dry_run_bulk(data.recording_ids, data.filters, data.limit, ctx)

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

            # Template binding before smart run
            if data.template_id and data.bind_template:
                recording.template_id = data.template_id
                recording.is_mapped = True
                if recording.status == ProcessingStatus.SKIPPED:
                    recording.status = ProcessingStatus.INITIALIZED
                await template_repo.increment_usage(template)

            # Smart run: determine action by current status
            result = await _execute_smart_run(
                recording,
                recording_id,
                ctx,
                manual_override=manual_override if manual_override else None,
            )

            tasks.append(
                {
                    "recording_id": recording_id,
                    "status": ("queued" if result.task_id else ("awaiting" if result.awaiting_source else "completed")),
                    "task_id": result.task_id,
                    "message": result.message,
                    "awaiting_source": result.awaiting_source,
                    "recording_status": result.recording_status,
                    "mts": result.mts,
                    "check_status_url": f"/api/v1/tasks/{result.task_id}" if result.task_id else None,
                }
            )

        except HTTPException as he:
            # Smart run raises HTTPException for rejected statuses (409, etc.)
            tasks.append(
                {
                    "recording_id": recording_id,
                    "status": "skipped",
                    "error": he.detail,
                    "task_id": None,
                }
            )

        except Exception as e:
            logger.error(f"Failed to create task | {format_details(rec=recording_id, error=str(e))}")
            tasks.append(
                {
                    "recording_id": recording_id,
                    "status": "error",
                    "error": str(e),
                    "task_id": None,
                }
            )

    queued_count = len([t for t in tasks if t["status"] == "queued"])
    skipped_count = len([t for t in tasks if t["status"] in ("skipped", "completed")])

    # Commit template bindings if any
    if data.template_id and data.bind_template:
        await ctx.session.commit()
        logger.info(f"Bound template | {format_details(template=data.template_id, queued=queued_count)}")

    return RecordingBulkOperationResponse(
        total=len(recording_ids),
        queued_count=queued_count,
        skipped_count=skipped_count,
        tasks=tasks,
    )


@bulk_router.post("/bulk/transcribe", response_model=RecordingBulkOperationResponse)
async def bulk_transcribe_recordings(
    data: BulkTranscribeRequest,
    ctx: ServiceContext = Depends(get_service_context),
    _feat: UserInDB = Depends(require_feature("can_transcribe")),
) -> RecordingBulkOperationResponse:
    """Bulk transcription of multiple recordings (async tasks)."""
    from api.helpers.status_manager import should_allow_transcription
    from api.tasks.processing import transcribe_recording_task

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

            if not should_allow_transcription(recording):
                tasks.append(
                    {
                        "recording_id": recording_id,
                        "status": "skipped",
                        "reason": f"Transcription not allowed (status: {recording.status})",
                        "task_id": None,
                    }
                )
                continue

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

            task = transcribe_recording_task.delay(
                recording_id=recording_id,
                user_id=ctx.user_id,
            )
            task_info = {
                "recording_id": recording_id,
                "status": "queued",
                "task_id": task.id,
                "check_status_url": f"/api/v1/tasks/{task.id}",
            }

            tasks.append(task_info)

        except Exception as e:
            logger.error(f"Failed to create transcribe task | {format_details(rec=recording_id, error=str(e))}")
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
        "tasks": tasks,
    }


@bulk_router.post("/bulk/pause", response_model=RecordingBulkOperationResponse)
async def bulk_pause_recordings(
    data: BulkPauseRequest,
    ctx: ServiceContext = Depends(get_service_context),
) -> RecordingBulkOperationResponse:
    """Bulk pause recordings. Only pauses recordings that are actively processing."""
    from datetime import UTC, datetime

    from api.helpers.status_manager import can_pause

    recording_ids = await _resolve_recording_ids(data.recording_ids, data.filters, data.limit, ctx)

    recording_repo = RecordingRepository(ctx.session)
    recordings_map = await recording_repo.get_by_ids(recording_ids, ctx.user_id)

    tasks = []
    paused_count = 0

    for recording_id in recording_ids:
        recording = recordings_map.get(recording_id)

        if not recording:
            tasks.append({"recording_id": recording_id, "status": "error", "error": "Not found", "task_id": None})
            continue

        if recording.on_pause:
            tasks.append(
                {
                    "recording_id": recording_id,
                    "status": "skipped",
                    "error": "Already paused",
                    "task_id": None,
                }
            )
            continue

        if not can_pause(recording):
            tasks.append(
                {
                    "recording_id": recording_id,
                    "status": "skipped",
                    "error": "No active pipeline (on_air=False)",
                    "task_id": None,
                }
            )
            continue

        # Hard pause: revoke chain, rollback status, clear on_air
        if recording.pipeline_task_id:
            from api.celery_app import celery_app

            celery_app.control.revoke(recording.pipeline_task_id, terminate=False)

        _pause_rollback = {
            ProcessingStatus.DOWNLOADING: (
                ProcessingStatus.DOWNLOADED if recording.local_video_path else ProcessingStatus.INITIALIZED
            ),
            ProcessingStatus.PROCESSING: ProcessingStatus.DOWNLOADED,
            ProcessingStatus.UPLOADING: ProcessingStatus.PROCESSED,
        }
        recording.status = _pause_rollback.get(recording.status, recording.status)

        for stage in recording.processing_stages:
            if stage.status == ProcessingStageStatus.IN_PROGRESS:
                stage.status = ProcessingStageStatus.PENDING
                stage.started_at = None

        recording.on_air = False
        recording.on_pause = True
        recording.pipeline_task_id = None
        recording.pause_requested_at = datetime.now(UTC)
        paused_count += 1

        tasks.append(
            {
                "recording_id": recording_id,
                "status": "queued",
                "task_id": None,
                "message": "Pause requested",
            }
        )

    if paused_count > 0:
        await ctx.session.commit()

    logger.info(f"Bulk pause | {format_details(paused=paused_count, total=len(recording_ids))}")

    return RecordingBulkOperationResponse(
        total=len(recording_ids),
        queued_count=paused_count,
        skipped_count=len(recording_ids) - paused_count,
        tasks=tasks,
    )


# ============================================================================
# New Bulk Operations Endpoints
# ============================================================================


@bulk_router.post("/bulk/download", response_model=RecordingBulkOperationResponse)
async def bulk_download_recordings(
    data: BulkDownloadRequest,
    ctx: ServiceContext = Depends(get_service_context),
    _feat: UserInDB = Depends(require_feature("can_process_video")),
) -> RecordingBulkOperationResponse:
    """Bulk download recordings from source."""
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

            source_type = recording.source.source_type if recording.source else None
            if source_type == SourceType.MTS_LINK:
                tasks.append(
                    {
                        "recording_id": recording_id,
                        "status": "skipped",
                        "error": "MTS Link recordings must use POST /run to prepare and download.",
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
            logger.error(f"Failed to queue download | {format_details(rec=recording_id, error=str(e))}")
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


@bulk_router.post("/bulk/trim", response_model=RecordingBulkOperationResponse)
async def bulk_trim_recordings(
    data: BulkTrimRequest,
    ctx: ServiceContext = Depends(get_service_context),
    _feat: UserInDB = Depends(require_feature("can_process_video")),
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
            logger.error(f"Failed to queue trim | {format_details(rec=recording_id, error=str(e))}")

    queued_count = len([t for t in tasks if t["status"] == "queued"])
    skipped_count = len([t for t in tasks if t["status"] == "skipped"])

    return {
        "queued_count": queued_count,
        "skipped_count": skipped_count,
        "tasks": tasks,
    }


@bulk_router.post("/bulk/topics", response_model=RecordingBulkOperationResponse)
async def bulk_extract_topics(
    data: BulkTopicsRequest,
    ctx: ServiceContext = Depends(get_service_context),
    _feat: UserInDB = Depends(require_feature("can_process_video")),
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
                granularity=data.granularity.value if data.granularity is not None else None,
                version_id=data.version_id,
                force=True,
            )

            tasks.append(
                {
                    "recording_id": recording_id,
                    "status": "queued",
                    "task_id": task.id,
                }
            )

        except Exception as e:
            logger.error(f"Failed to queue topics | {format_details(rec=recording_id, error=str(e))}")

    queued_count = len([t for t in tasks if t["status"] == "queued"])
    skipped_count = len([t for t in tasks if t["status"] == "skipped"])

    return {
        "queued_count": queued_count,
        "skipped_count": skipped_count,
        "tasks": tasks,
    }


@bulk_router.post("/bulk/subtitles", response_model=RecordingBulkOperationResponse)
async def bulk_generate_subtitles(
    data: BulkSubtitlesRequest,
    ctx: ServiceContext = Depends(get_service_context),
    _feat: UserInDB = Depends(require_feature("can_process_video")),
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
            logger.error(f"Failed to queue subtitles | {format_details(rec=recording_id, error=str(e))}")

    queued_count = len([t for t in tasks if t["status"] == "queued"])
    skipped_count = len([t for t in tasks if t["status"] == "skipped"])

    return {
        "queued_count": queued_count,
        "skipped_count": skipped_count,
        "tasks": tasks,
    }


@bulk_router.post("/bulk/upload", response_model=RecordingBulkOperationResponse)
async def bulk_upload_recordings(
    data: BulkUploadRequest,
    ctx: ServiceContext = Depends(get_service_context),
    _feat: UserInDB = Depends(require_feature("can_upload")),
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
            logger.error(f"Failed to queue upload | {format_details(rec=recording_id, error=str(e))}")

    queued_count = len([t for t in tasks if t["status"] == "queued"])
    skipped_count = len([t for t in tasks if t["status"] == "skipped"])

    return {
        "queued_count": queued_count,
        "skipped_count": skipped_count,
        "tasks": tasks,
    }


@bulk_router.post("/bulk/delete", response_model=RecordingBulkDeleteResponse)
async def bulk_delete_recordings(
    data: BulkDeleteRequest,
    ctx: ServiceContext = Depends(get_service_context),
) -> RecordingBulkDeleteResponse:
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
            logger.error(f"Failed to delete recording | {format_details(rec=recording_id, error=str(e))}")

    # Commit all changes
    try:
        await ctx.session.commit()
    except Exception as e:
        logger.error(f"Failed to commit bulk delete | {format_details(error=str(e))}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to commit bulk delete: {e!s}",
        )

    logger.info(
        f"Bulk delete completed | {format_details(user=short_user_id(ctx.user_id), deleted=deleted_count, skipped=skipped_count, errors=error_count)}"
    )

    return RecordingBulkDeleteResponse(
        message=f"Bulk delete completed: {deleted_count} recordings deleted",
        deleted_count=deleted_count,
        skipped_count=skipped_count,
        error_count=error_count,
        details=details,
    )


router.include_router(bulk_router)

# ============================================================================
# Processing Endpoints
# ============================================================================


@router.post("/{recording_id}/download", response_model=RecordingOperationResponse)
async def download_recording(
    recording_id: int,
    force: bool = Query(False, description="Re-download if already downloaded"),
    ctx: ServiceContext = Depends(get_service_context),
    _feat: UserInDB = Depends(require_feature("can_process_video")),
) -> RecordingOperationResponse:
    """Download recording from source (Zoom, yt-dlp, Yandex Disk, etc.)."""
    from api.helpers.status_manager import should_allow_download
    from api.tasks.processing import download_recording_task
    from models.recording import SourceType

    recording_repo = RecordingRepository(ctx.session)
    recording = await recording_repo.get_by_id(recording_id, ctx.user_id)

    if not recording:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Recording {recording_id} not found or you don't have access",
        )

    source_type = recording.source.source_type if recording.source else None

    # Check if we can download
    if not should_allow_download(recording):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Download not allowed for recording with status {recording.status}.",
        )

    if source_type == SourceType.MTS_LINK:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="MTS Link recordings must use POST /run to prepare and download.",
        )

    source_meta = recording.source.meta if recording.source and recording.source.meta else {}

    # Each source type stores download info under a different metadata key
    has_download_info = bool(
        source_meta.get("download_url")
        or source_meta.get("url")
        or source_meta.get("path")
        or source_meta.get("public_key")
    )

    if not has_download_info:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"No download source available for this recording (source_type={source_type}).",
        )

    if not force and recording.status == ProcessingStatus.DOWNLOADED and recording.local_video_path:
        from file_storage.factory import get_storage_backend as _storage_for_skip

        if await _storage_for_skip().exists(recording.local_video_path):
            return {
                "success": True,
                "message": "Recording already downloaded",
                "recording_id": recording_id,
                "local_video_path": recording.local_video_path,
                "task_id": None,
            }

    task = download_recording_task.delay(
        recording_id=recording_id,
        user_id=ctx.user_id,
        force=force,
    )

    logger.info(
        f"Download task created | {format_details(task=short_task_id(task.id), rec=recording_id, user=short_user_id(ctx.user_id))}"
    )

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
    _feat: UserInDB = Depends(require_feature("can_process_video")),
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

    from file_storage.factory import get_storage_backend as _storage_for_trim

    if not await _storage_for_trim().exists(recording.local_video_path):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Video file not found at storage key: {recording.local_video_path}",
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

    logger.info(
        f"Trim task created | {format_details(task=short_task_id(task.id), rec=recording_id, user=short_user_id(ctx.user_id))}"
    )

    return {
        "success": True,
        "task_id": task.id,
        "recording_id": recording_id,
        "status": "queued",
        "message": "Processing task has been queued",
        "check_status_url": f"/api/v1/tasks/{task.id}",
    }


@router.post("/{recording_id}/run", response_model=RecordingOperationResponse | DryRunResponse)
async def run_recording(
    recording_id: int,
    config: ConfigOverrideRequest = ConfigOverrideRequest(),
    dry_run: bool = Query(False, description="Dry-run: show what will be done without actual execution"),
    ctx: ServiceContext = Depends(get_service_context),
    _feat: UserInDB = Depends(require_feature("can_process_video")),
) -> RecordingOperationResponse | DryRunResponse:
    """
    Smart run: always does the right thing based on current recording state.

    - INITIALIZED/SKIPPED → full pipeline (download → process → upload)
    - DOWNLOADED → processing pipeline (skip download)
    - DOWNLOADING/PROCESSING/UPLOADING + paused → clear pause, continue
    - DOWNLOADING/PROCESSING/UPLOADING + not paused → 409 (already running)
    - PROCESSED/UPLOADED → retry failed/pending uploads
    - READY → already complete
    - EXPIRED/PENDING_SOURCE → 409 (cannot process)

    For a full restart: use /reset first, then /run.
    """
    if dry_run:
        return await _execute_dry_run_single(recording_id, config, ctx)

    recording_repo = RecordingRepository(ctx.session)
    recording = await recording_repo.get_by_id(recording_id, ctx.user_id)

    if not recording:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Recording {recording_id} not found or you don't have access",
        )

    # Template binding (before smart run, so override is available)
    if config.template_id and config.bind_template:
        from api.repositories.template_repos import RecordingTemplateRepository

        template_repo = RecordingTemplateRepository(ctx.session)
        template = await template_repo.find_by_id(config.template_id, ctx.user_id)

        if not template:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=f"Template {config.template_id} not found"
            )

        recording.template_id = config.template_id
        recording.is_mapped = True

        # Update status if currently SKIPPED
        if recording.status == ProcessingStatus.SKIPPED:
            recording.status = ProcessingStatus.INITIALIZED

        await ctx.session.commit()
        logger.info(f"Bound template | {format_details(template=config.template_id, rec=recording_id)}")

    manual_override = _build_override_from_flexible(config)

    return await _execute_smart_run(recording, recording_id, ctx, manual_override)


async def _check_processing_quota_or_raise(ctx: ServiceContext) -> None:
    from api.services.quota_service import QuotaService

    allowed, err = await QuotaService(ctx.session).check_processing_quota(ctx.user_id)
    if not allowed:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=err)


async def _dispatch_full_pipeline(
    recording,
    recording_id: int,
    ctx: ServiceContext,
    manual_override: dict | None,
    *,
    message: str,
) -> RecordingOperationResponse:
    from api.tasks.processing import run_recording_task

    await _check_processing_quota_or_raise(ctx)

    recording.on_air = True
    await ctx.session.commit()
    try:
        task = run_recording_task.delay(
            recording_id=recording_id,
            user_id=ctx.user_id,
            manual_override=manual_override,
        )
    except Exception as exc:
        recording.on_air = False
        await ctx.session.commit()
        logger.error(f"Smart run: failed to dispatch pipeline | {format_details(rec=recording_id, error=exc)}")
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Failed to dispatch pipeline task") from exc
    recording.pipeline_task_id = task.id
    await ctx.session.commit()
    return RecordingOperationResponse(
        success=True,
        task_id=task.id,
        recording_id=recording_id,
        message=message,
        awaiting_source=False,
        recording_status=recording.status,
    )


async def _execute_smart_run(
    recording,
    recording_id: int,
    ctx: ServiceContext,
    manual_override: dict | None = None,
) -> RecordingOperationResponse:
    """
    Unified smart run: determine the right action based on current state.

    State machine:
    - on_air=True → 409 (pipeline already active)
    - INITIALIZED/SKIPPED → start full pipeline (download → process → upload)
    - DOWNLOADED → start processing pipeline (skip download)
    - PROCESSED/UPLOADED → resume the pipeline when a stage is PENDING or FAILED
      (completed stages skip themselves); otherwise upload pending/failed targets.
      A leftover failure flag is cleared only if that trim, transcription, topics,
      or subtitles stage has since completed. Download and upload failures stay.
    - READY → already complete
    - EXPIRED/PENDING_SOURCE → reject

    on_pause is cleared here so a paused recording resumes normally through the
    status-based routing below (status is already stable after hard pause).
    """
    from api.tasks.processing import _launch_uploads_task
    from models.recording import SourceType

    current_status = recording.status

    # --- Guard: pipeline already active ---
    if recording.on_air:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Recording already has an active pipeline. Use /pause to stop it.",
        )

    # --- Reject terminal/unprocessable statuses ---
    if current_status == ProcessingStatus.EXPIRED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot run expired recording.",
        )
    if current_status == ProcessingStatus.PENDING_SOURCE:
        source_type = recording.source.source_type if recording.source else None
        if source_type != SourceType.MTS_LINK:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Recording is waiting for source. Cannot run yet.",
            )

    # --- Clear pause flag if set (after hard pause status is already stable) ---
    _was_paused = recording.on_pause
    if recording.on_pause:
        recording.on_pause = False
        recording.pause_requested_at = None

    _fresh_start_statuses = [
        ProcessingStatus.INITIALIZED,
        ProcessingStatus.SKIPPED,
        ProcessingStatus.PENDING_CONVERSION,
        ProcessingStatus.PENDING_SOURCE,
    ]

    if current_status in _fresh_start_statuses or current_status == ProcessingStatus.DOWNLOADED:
        try:
            await resolve_full_config(
                ctx.session,
                recording_id,
                ctx.user_id,
                manual_override=manual_override,
                include_output_config=True,
            )
        except _CONFIG_RESOLUTION_HTTP_ERRORS as e:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e

    # 1. Fresh start: INITIALIZED, SKIPPED, or MTS pending → full pipeline
    # MTS prepare runs inside the Celery task (not in HTTP) so /run returns quickly.
    if current_status in _fresh_start_statuses:
        logger.info(f"Smart run: starting full pipeline | {format_details(rec=recording_id, status=current_status)}")
        return await _dispatch_full_pipeline(
            recording,
            recording_id,
            ctx,
            manual_override,
            message="Pipeline started",
        )

    # 2. Processing: DOWNLOADED → start processing (skip download)
    if current_status == ProcessingStatus.DOWNLOADED:
        logger.info(f"Smart run: continuing processing | {format_details(rec=recording_id)}")
        return await _dispatch_full_pipeline(
            recording,
            recording_id,
            ctx,
            manual_override,
            message="Processing pipeline started (download already complete)",
        )

    # 3. Upload phase: PROCESSED, UPLOADED → ensure targets from config, then upload pending/failed
    if current_status in [ProcessingStatus.PROCESSED, ProcessingStatus.UPLOADED]:
        from api.tasks.processing import run_recording_task

        await ctx.session.refresh(recording, ["processing_stages"])
        open_stages = [
            s
            for s in recording.processing_stages
            if s.status in (ProcessingStageStatus.PENDING, ProcessingStageStatus.FAILED)
        ]
        if open_stages:
            recording.on_air = True
            await ctx.session.commit()
            try:
                task = run_recording_task.delay(
                    recording_id=recording_id,
                    user_id=ctx.user_id,
                    manual_override=manual_override,
                )
            except Exception as exc:
                recording.on_air = False
                await ctx.session.commit()
                logger.error(f"Smart run: failed to dispatch pipeline | {format_details(rec=recording_id, error=exc)}")
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY, detail="Failed to dispatch pipeline task"
                ) from exc
            recording.pipeline_task_id = task.id
            await ctx.session.commit()
            logger.info(
                f"Smart run: re-entering pipeline (incomplete stages) | {format_details(rec=recording_id, open=len(open_stages))}"
            )
            return RecordingOperationResponse(
                success=True,
                task_id=task.id,
                recording_id=recording_id,
                message=f"Resuming processing pipeline ({len(open_stages)} stage(s) not finished)",
            )

        from api.helpers.pipeline_initializer import ensure_output_targets

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

        if recording.failed and recording.failed_at_stage in {
            "trim",
            "transcribe",
            "extract_topics",
            "generate_subtitles",
        }:
            finished = next(
                (
                    s
                    for s in recording.processing_stages
                    if str(getattr(s.stage_type, "value", s.stage_type)).lower() == recording.failed_at_stage
                    and s.status == ProcessingStageStatus.COMPLETED
                    and not s.failed
                ),
                None,
            )
            if finished is not None:
                from api.helpers.failure_reset import reset_recording_failure

                reset_recording_failure(recording, recording.failed_at_stage)
                await ctx.session.commit()

        if output_config:
            include_copy = bool(output_config.get("auto_upload"))
            await ensure_output_targets(
                ctx.session,
                recording,
                output_config,
                include_copy=include_copy,
                metadata_config=full_config.get("metadata_config"),
            )
            await ctx.session.commit()

        # Reload to pick up freshly created targets
        await ctx.session.refresh(recording, ["outputs"])

        failed_outputs = [o for o in recording.outputs if o.status == TargetStatus.FAILED]
        pending_outputs = [o for o in recording.outputs if o.status == TargetStatus.NOT_UPLOADED]
        targets = failed_outputs + pending_outputs

        if targets:
            platforms = []
            preset_map = {}
            for output in targets:
                target_type = output.target_type
                platform = target_type.lower() if isinstance(target_type, str) else target_type.value.lower()
                platforms.append(platform)
                if output.preset_id:
                    preset_map[platform] = output.preset_id

            from celery import chain as celery_chain

            from api.tasks.base import bind_task_owner
            from api.tasks.processing import _finalize_pipeline_task

            recording.on_air = True
            await ctx.session.commit()
            # Chain finalize after launch so on_air is cleared when all uploads are dispatched.
            try:
                task = celery_chain(
                    _launch_uploads_task.si(
                        recording_id=recording_id,
                        user_id=ctx.user_id,
                        platforms=platforms,
                        preset_map=preset_map,
                        metadata_override=full_config.get("metadata_config"),
                    ),
                    _finalize_pipeline_task.si(recording_id, ctx.user_id),
                ).apply_async()
                try:
                    bind_task_owner(str(task.id), ctx.user_id)
                except Exception as bind_exc:
                    logger.warning(f"Failed to bind smart-run chain owner | task={task.id} | {bind_exc}")
            except Exception as exc:
                recording.on_air = False
                await ctx.session.commit()
                logger.error(f"Smart run: failed to dispatch uploads | {format_details(rec=recording_id, error=exc)}")
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY, detail="Failed to dispatch upload task"
                ) from exc
            recording.pipeline_task_id = task.id
            await ctx.session.commit()

            logger.info(f"Smart run: uploading targets | {format_details(count=len(targets), rec=recording_id)}")
            return RecordingOperationResponse(
                success=True,
                task_id=task.id,
                recording_id=recording_id,
                message=f"Uploading {len(targets)} target(s)",
            )

        if _was_paused:
            await ctx.session.commit()
        return RecordingOperationResponse(
            success=True,
            recording_id=recording_id,
            message="Processing complete. No pending or failed uploads found.",
        )

    # 4. Already complete
    if current_status == ProcessingStatus.READY:
        if _was_paused:
            await ctx.session.commit()
        return RecordingOperationResponse(
            success=True,
            recording_id=recording_id,
            message="Recording already complete. No action needed.",
        )

    # Fallback: unexpected status
    if _was_paused:
        await ctx.session.commit()
    return RecordingOperationResponse(
        success=True,
        recording_id=recording_id,
        message=f"No action available for status {current_status}. Use /reset to start over.",
    )


@router.post("/{recording_id}/transcribe", response_model=RecordingOperationResponse)
async def transcribe_recording(
    recording_id: int,
    ctx: ServiceContext = Depends(get_service_context),
    _feat: UserInDB = Depends(require_feature("can_transcribe")),
) -> RecordingOperationResponse:
    """Transcribe recording via AssemblyAI (async task). Use /topics endpoint for topic extraction."""
    from api.helpers.status_manager import should_allow_transcription
    from api.services.quota_service import QuotaService
    from api.tasks.processing import transcribe_recording_task

    recording_repo = RecordingRepository(ctx.session)
    recording = await recording_repo.get_by_id(recording_id, ctx.user_id)

    if not recording:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Recording {recording_id} not found or you don't have access"
        )

    _allowed, _err = await QuotaService(ctx.session).check_transcriptions_quota(ctx.user_id)
    if not _allowed:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=_err)

    if not should_allow_transcription(recording):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Transcription cannot be started. Current status: {recording.status}. "
            f"Transcription is already completed or in progress.",
        )

    if not recording.processed_video_path and not recording.local_video_path:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No video file available for transcription. Please download the recording first.",
        )

    audio_path = recording.processed_video_path or recording.local_video_path

    from file_storage.factory import get_storage_backend as _storage_for_transcribe

    if not await _storage_for_transcribe().exists(audio_path):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"Video file not found in storage: {audio_path}"
        )

    task = transcribe_recording_task.delay(
        recording_id=recording_id,
        user_id=ctx.user_id,
    )

    logger.info(
        f"Transcription task created | {format_details(task=short_task_id(task.id), rec=recording_id, user=short_user_id(ctx.user_id))}"
    )

    return {
        "success": True,
        "task_id": task.id,
        "recording_id": recording_id,
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
    _feat: UserInDB = Depends(require_feature("can_upload")),
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

    # Check if file exists in storage backend
    from file_storage.factory import get_storage_backend as _storage_for_upload

    if not await _storage_for_upload().exists(video_path):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Processed video file not found in storage: {video_path}",
        )

    # Start async task
    task = upload_recording_to_platform.delay(
        recording_id=recording_id,
        user_id=ctx.user_id,
        platform=platform,
        preset_id=preset_id,
    )

    logger.info(
        f"Upload task created | {format_details(task=short_task_id(task.id), rec=recording_id, platform=platform, user=short_user_id(ctx.user_id))}"
    )

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
    granularity: Granularity | None = Query(
        None,
        description="Topics granularity: short, medium, or long (omit = recording config)",
    ),
    version_id: str | None = Query(None, description="Version ID (optional)"),
    ctx: ServiceContext = Depends(get_service_context),
    _feat: UserInDB = Depends(require_feature("can_process_video")),
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
    if not await transcription_manager.has_master(recording_id, user_slug):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No transcription found. Please run /transcribe first.",
        )

    gran = granularity.value if granularity is not None else None
    task = extract_topics_task.delay(
        recording_id=recording_id,
        user_id=ctx.user_id,
        granularity=gran,
        version_id=version_id,
        force=True,
    )

    logger.info(
        f"Extract topics task created | {format_details(task=short_task_id(task.id), rec=recording_id, user=short_user_id(ctx.user_id), granularity=granularity)}"
    )

    return {
        "success": True,
        "task_id": task.id,
        "recording_id": recording_id,
        "status": "queued",
        "message": "Topic extraction task has been queued",
        "check_status_url": f"/api/v1/tasks/{task.id}",
    }


@router.patch("/{recording_id}/topics", response_model=dict)
async def update_topics(
    recording_id: int,
    data: TopicsUpdateRequest,
    ctx: ServiceContext = Depends(get_service_context),
) -> dict:
    """Partially update AI-generated content (summary, questions, main_topics, topic_timestamps)
    of the active extracted.json version. Sets manually_edited=True on the version."""
    from transcription_module.manager import get_transcription_manager

    recording_repo = RecordingRepository(ctx.session)
    recording = await recording_repo.get_by_id(recording_id, ctx.user_id)
    if not recording:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Recording {recording_id} not found")

    transcription_manager = get_transcription_manager()
    user_slug = recording.owner.user_slug

    if not await transcription_manager.has_extracted(recording_id, user_slug):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No topics found for this recording")

    payload = data.model_dump(exclude_unset=True)

    # Convert topic_timestamps pydantic models to plain dicts
    if "topic_timestamps" in payload:
        payload["topic_timestamps"] = [t.model_dump(exclude_none=True) for t in (data.topic_timestamps or [])]

    updated_version = await transcription_manager.update_active_version(recording_id, user_slug, payload)

    # Keep DB cache in sync if main_topics changed
    if data.main_topics is not None:
        recording.main_topics = data.main_topics
        await recording_repo.update(recording)
        await ctx.session.commit()

    logger.info(f"Topics manually updated | {format_details(rec=recording_id, fields=list(payload))}")
    return {k: v for k, v in updated_version.items() if k != "_metadata"}


@router.post("/{recording_id}/topics/render", response_model=dict)
async def render_topics_template(
    recording_id: int,
    data: TopicsRenderRequest,
    ctx: ServiceContext = Depends(get_service_context),
) -> dict:
    """Render a Jinja template string using the recording's context variables.
    Used by the frontend 'Convert to text' action."""
    from api.helpers.template_renderer import TemplateRenderer, render_jinja

    recording_repo = RecordingRepository(ctx.session)
    recording = await recording_repo.get_by_id(recording_id, ctx.user_id)
    if not recording:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Recording {recording_id} not found")

    from transcription_module.manager import get_transcription_manager

    extracted = None
    owner = getattr(recording, "owner", None)
    if owner and getattr(owner, "user_slug", None):
        try:
            extracted = await get_transcription_manager().get_active_extracted(recording_id, owner.user_slug)
        except Exception as exc:
            logger.debug("Could not load extracted for topics render: %s", exc)

    from api.services.config_resolver import ConfigResolver

    meta_cfg = await ConfigResolver(ctx.session).resolve_metadata_config(recording, ctx.user_id)
    render_ctx = TemplateRenderer.prepare_recording_context(
        recording,
        extracted_data=extracted,
        topics_display=meta_cfg.get("topics_display"),
        questions_display=meta_cfg.get("questions_display"),
    )
    try:
        rendered = render_jinja(data.template, render_ctx)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Template render error: {e}")

    return {"rendered": rendered}


@router.post("/{recording_id}/subtitles", response_model=RecordingOperationResponse)
async def generate_subtitles(
    recording_id: int,
    formats: list[Literal["srt", "vtt"]] = Query(
        ["srt", "vtt"],
        description="Subtitle formats to generate: srt, vtt",
    ),
    ctx: ServiceContext = Depends(get_service_context),
    _feat: UserInDB = Depends(require_feature("can_process_video")),
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
    if not await transcription_manager.has_master(recording_id, user_slug):
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
        f"Generate subtitles task created | {format_details(task=short_task_id(task.id), rec=recording_id, user=short_user_id(ctx.user_id), formats=formats)}"
    )

    return {
        "success": True,
        "task_id": task.id,
        "recording_id": recording_id,
        "status": "queued",
        "message": "Subtitle generation task has been queued",
        "check_status_url": f"/api/v1/tasks/{task.id}",
    }


@router.get("/{recording_id}/config", response_model=RecordingConfigResponse)
async def get_recording_config(
    recording_id: int,
    ctx: ServiceContext = Depends(get_service_context),
) -> RecordingConfigResponse:
    """Get current resolved configuration for recording."""
    from api.services.config_resolver import ConfigResolver

    recording_repo = RecordingRepository(ctx.session)

    # Get recording from DB
    recording = await recording_repo.get_by_id(recording_id, ctx.user_id)
    if not recording:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Recording {recording_id} not found")

    # Resolve configuration
    config_resolver = ConfigResolver(ctx.session)
    config_data = await config_resolver.get_base_config_for_edit(recording, ctx.user_id)

    return RecordingConfigResponse(
        recording_id=recording_id,
        is_mapped=recording.is_mapped,
        template_id=config_data["template_id"],
        template_name=config_data["template_name"],
        has_manual_override=config_data["has_manual_override"],
        manual_override_sections=config_data["manual_override_sections"],
        processing_config=config_data["processing_config"],
        output_config=config_data["output_config"],
        metadata_config=config_data["metadata_config"],
        inherited=config_data["inherited"],
    )


@router.patch("/{recording_id}/config", response_model=ConfigUpdateResponse)
async def update_recording_config(
    recording_id: int,
    data: RecordingConfigUpdateRequest,
    ctx: ServiceContext = Depends(get_service_context),
) -> ConfigUpdateResponse:
    """Save user configuration overrides in recording.processing_preferences."""
    from api.services.config_resolver import ConfigResolver

    recording_repo = RecordingRepository(ctx.session)

    # Get recording from DB
    recording = await recording_repo.get_by_id(recording_id, ctx.user_id)
    if not recording:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Recording {recording_id} not found")

    # Get config resolver
    config_resolver = ConfigResolver(ctx.session)

    # Copy so JSONB mutation is a new object (in-place edits are not persisted).
    prefs = recording.processing_preferences
    new_preferences = dict(prefs) if isinstance(prefs, dict) else {}

    if data.processing_config is not None:
        processing_config_dict = data.processing_config.model_dump(exclude_none=True)
        if "processing_config" not in new_preferences:
            new_preferences["processing_config"] = {}
        # Flatten: schema has transcription nested, store as {transcription: {...}}
        new_preferences["processing_config"] = config_resolver._merge_configs(
            new_preferences.get("processing_config", {}), processing_config_dict
        )

    if data.output_config is not None:
        output_config_dict = data.output_config.model_dump(exclude_none=True)
        if "output_config" not in new_preferences:
            new_preferences["output_config"] = {}
        new_preferences["output_config"] = config_resolver._merge_configs(
            new_preferences.get("output_config", {}), output_config_dict
        )

    if data.metadata_config is not None:
        metadata_config_dict = data.metadata_config.model_dump(exclude_none=True)
        if "metadata_config" not in new_preferences:
            new_preferences["metadata_config"] = {}
        new_preferences["metadata_config"] = config_resolver._merge_configs(
            new_preferences.get("metadata_config", {}), metadata_config_dict
        )

    # Save overrides to recording.processing_preferences
    recording.processing_preferences = new_preferences if new_preferences else None

    if data.output_config is not None:
        from api.services.config_resolver import ResolveContext
        from api.services.config_utils import InvalidOutputPresetsError, validate_effective_output_config

        resolved_output = await config_resolver.resolve(ResolveContext(user_id=ctx.user_id, recording=recording))
        try:
            await validate_effective_output_config(ctx.session, ctx.user_id, resolved_output.output)
        except InvalidOutputPresetsError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    # Sync stages with updated config
    from api.helpers.stage_sync import sync_stages_with_config

    effective_config = await config_resolver.resolve_processing_config(recording, ctx.user_id)
    await sync_stages_with_config(recording, effective_config)

    await ctx.session.commit()

    logger.info(f"Updated manual config | {format_details(rec=recording_id)}")

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
    """Drop this recording's overrides. The confirmation lists which ones."""
    from api.helpers.stage_sync import sync_stages_with_config
    from api.services.config_resolver import ConfigResolver

    recording_repo = RecordingRepository(ctx.session)

    recording = await recording_repo.get_by_id(recording_id, ctx.user_id)
    if not recording:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Recording {recording_id} not found")

    recording.processing_preferences = None
    user_config = await UserConfigRepository(ctx.session).get_effective_config(ctx.user_id)
    await recording_repo.assign_retention_exempt(recording, None, user_config)

    config_resolver = ConfigResolver(ctx.session)
    effective_config = await config_resolver.resolve_processing_config(recording, ctx.user_id)
    await sync_stages_with_config(recording, effective_config)
    await ctx.session.commit()

    logger.info(f"Reset to template configuration | {format_details(rec=recording_id)}")

    return ConfigSaveResponse(
        recording_id=recording_id,
        message="Reset to template configuration",
        has_manual_override=False,
        effective_config=effective_config,
    )


@router.post("/{recording_id}/pause", response_model=PauseRecordingResponse)
async def pause_recording(
    recording_id: int,
    ctx: ServiceContext = Depends(get_service_context),
) -> PauseRecordingResponse:
    """
    Hard pause: immediately marks pipeline as inactive and rolls back to a stable
    status. The currently-running Celery task completes naturally, but no further
    tasks in the chain will execute (revoked). Resume via POST /{id}/run.
    """
    from datetime import UTC, datetime

    from api.helpers.status_manager import can_pause

    recording_repo = RecordingRepository(ctx.session)
    recording = await recording_repo.get_by_id(recording_id, ctx.user_id)

    if not recording:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Recording {recording_id} not found")

    if recording.on_pause:
        return PauseRecordingResponse(
            success=True,
            recording_id=recording_id,
            message="Recording is already paused",
            status=recording.status,
            on_pause=True,
        )

    if not can_pause(recording):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot pause recording: no active pipeline (on_air=False).",
        )

    # Soft-revoke the chain so queued tasks won't start; running task finishes cleanly
    if recording.pipeline_task_id:
        from api.celery_app import celery_app

        celery_app.control.revoke(recording.pipeline_task_id, terminate=False)

    # Immediate rollback to stable status so smart_run can resume correctly
    _pause_rollback = {
        ProcessingStatus.DOWNLOADING: (
            ProcessingStatus.DOWNLOADED if recording.local_video_path else ProcessingStatus.INITIALIZED
        ),
        ProcessingStatus.PROCESSING: ProcessingStatus.DOWNLOADED,
        ProcessingStatus.UPLOADING: ProcessingStatus.PROCESSED,
    }
    stable_status = _pause_rollback.get(recording.status, recording.status)
    recording.status = stable_status

    # Reset any IN_PROGRESS stages to PENDING so they re-run on resume
    for stage in recording.processing_stages:
        if stage.status == ProcessingStageStatus.IN_PROGRESS:
            stage.status = ProcessingStageStatus.PENDING
            stage.started_at = None

    recording.on_air = False
    recording.on_pause = True
    recording.pipeline_task_id = None
    recording.pause_requested_at = datetime.now(UTC)
    await ctx.session.commit()

    logger.info(f"Paused (hard) | {format_details(rec=recording_id, rolled_back_to=stable_status)}")

    return PauseRecordingResponse(
        success=True,
        recording_id=recording_id,
        message="Pipeline paused. Use /run to resume.",
        status=stable_status,
        on_pause=True,
    )


@router.post("/{recording_id}/reset", response_model=ResetRecordingResponse)
async def reset_recording(
    recording_id: int,
    delete_files: bool = Query(True, description="Delete all files (video, audio, transcription)"),
    ctx: ServiceContext = Depends(get_service_context),
) -> ResetRecordingResponse:
    """Reset recording to initial state, optionally deleting all processed files."""
    from sqlalchemy import delete

    from database.models import OutputTargetModel, ProcessingStageModel

    recording_repo = RecordingRepository(ctx.session)
    recording = await recording_repo.get_by_id(recording_id, ctx.user_id)

    if not recording:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Recording {recording_id} not found")

    if recording.deleted:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot reset deleted recording. Please restore it first using POST /recordings/{id}/restore",
        )

    deleted_files = []
    errors = []

    if delete_files:
        wiped, wipe_errors = await recording_repo.wipe_recording_storage(recording)
        deleted_files.extend(wiped)
        errors.extend(wipe_errors)

    # If pipeline is active, revoke it before resetting so no orphan tasks run.
    if recording.on_air and recording.pipeline_task_id:
        from api.celery_app import celery_app

        celery_app.control.revoke(recording.pipeline_task_id, terminate=False)
        logger.info(f"Reset: revoked active chain | rec={recording_id} task={recording.pipeline_task_id}")

    recording.topic_timestamps = None
    recording.main_topics = None
    recording.transcription_info = None
    recording.failed = False
    recording.failed_reason = None
    recording.on_pause = False
    recording.pause_requested_at = None
    recording.on_air = False
    recording.pipeline_task_id = None

    source_processing_incomplete = (
        recording.source.meta.get("source_processing_incomplete", False)
        if recording.source and recording.source.meta
        else False
    )

    if not delete_files and recording.local_video_path:
        recording.status = ProcessingStatus.DOWNLOADED
    elif recording.status == ProcessingStatus.PENDING_CONVERSION:
        recording.status = ProcessingStatus.INITIALIZED if recording.is_mapped else ProcessingStatus.SKIPPED
        if recording.source and isinstance(recording.source.meta, dict):
            meta = dict(recording.source.meta)
            for key in (
                "conversion_id",
                "conversion_state",
                "conversion_progress",
                "conversion_ordered_view",
                "mts_prepare_checked_at",
            ):
                meta.pop(key, None)
            meta["needs_mp4"] = True
            recording.source.meta = meta
    elif source_processing_incomplete:
        recording.status = ProcessingStatus.PENDING_SOURCE
    elif recording.is_mapped:
        recording.status = ProcessingStatus.INITIALIZED
    else:
        recording.status = ProcessingStatus.SKIPPED

    user_config_repo = UserConfigRepository(ctx.session)
    user_config = await user_config_repo.get_effective_config(ctx.user_id)

    recording.expire_at = None
    await recording_repo.sync_retention_deadline(recording, user_config)

    # Delete output_targets
    await ctx.session.execute(delete(OutputTargetModel).where(OutputTargetModel.recording_id == recording_id))

    # Delete processing_stages
    await ctx.session.execute(delete(ProcessingStageModel).where(ProcessingStageModel.recording_id == recording_id))

    await ctx.session.commit()

    logger.info(
        f"Reset | {format_details(rec=recording_id, deleted=len(deleted_files), errors=len(errors), status=recording.status)}"
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


@router.post("/{recording_id}/template/{template_id}", response_model=TemplateBindResponse)
async def bind_template_to_recording(
    recording_id: int,
    template_id: int,
    reset_preferences: bool = Query(False, description="Reset processing preferences to use template config"),
    ctx: ServiceContext = Depends(get_service_context),
) -> TemplateBindResponse:
    """Bind template to recording."""
    from api.repositories.template_repos import RecordingTemplateRepository

    recording_repo = RecordingRepository(ctx.session)
    recording = await recording_repo.get_by_id(recording_id, ctx.user_id)

    if not recording:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Recording {recording_id} not found")

    template_repo = RecordingTemplateRepository(ctx.session)
    template = await template_repo.find_by_id(template_id, ctx.user_id)

    if not template:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Template {template_id} not found")

    recording.template_id = template_id
    recording.is_mapped = True

    if reset_preferences:
        recording.processing_preferences = None

    user_config = await UserConfigRepository(ctx.session).get_effective_config(ctx.user_id)
    await recording_repo.sync_retention_deadline(recording, user_config)

    if recording.status == ProcessingStatus.SKIPPED:
        recording.status = ProcessingStatus.INITIALIZED

    await ctx.session.commit()

    logger.info(
        f"Template bound | {format_details(template=template_id, rec=recording_id, reset_preferences=reset_preferences)}"
    )

    return TemplateBindResponse(
        success=True,
        recording_id=recording_id,
        template={"id": template.id, "name": template.name},
        preferences_reset=reset_preferences,
        message=f"Template '{template.name}' bound successfully"
        + (" (preferences reset)" if reset_preferences else ""),
    )


@router.delete("/{recording_id}/template", response_model=TemplateUnbindResponse)
async def unbind_template_from_recording(
    recording_id: int,
    ctx: ServiceContext = Depends(get_service_context),
) -> TemplateUnbindResponse:
    """Unbind template from recording."""
    recording_repo = RecordingRepository(ctx.session)
    recording = await recording_repo.get_by_id(recording_id, ctx.user_id)

    if not recording:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Recording {recording_id} not found")

    if not recording.template_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Recording has no template bound")

    recording.template_id = None
    recording.is_mapped = False

    await ctx.session.commit()

    logger.info(f"Template unbound | {format_details(rec=recording_id)}")

    return TemplateUnbindResponse(
        success=True,
        recording_id=recording_id,
        message="Template unbound successfully",
    )


# ============================================================================
# Soft Delete Endpoints
# ============================================================================


@router.delete("/{recording_id}", response_model=DeleteRecordingResponse)
async def delete_recording(
    recording_id: int,
    ctx: ServiceContext = Depends(get_service_context),
) -> DeleteRecordingResponse:
    """Soft delete recording (can be restored before hard deletion)."""
    recording_repo = RecordingRepository(ctx.session)
    recording = await recording_repo.get_by_id(recording_id, ctx.user_id)

    if not recording:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Recording {recording_id} not found")

    if recording.deleted:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Recording is already deleted")

    # Get user config (merged with defaults)
    user_config_repo = UserConfigRepository(ctx.session)
    user_config = await user_config_repo.get_effective_config(ctx.user_id)

    await recording_repo.soft_delete(recording, user_config)
    await ctx.session.commit()

    await _track_recording_deleted(ctx, recording.id)

    logger.info(f"Soft deleted | {format_details(rec=recording_id, user=short_user_id(ctx.user_id))}")

    return DeleteRecordingResponse(
        message="Recording deleted successfully",
        recording_id=recording.id,
        deleted_at=recording.deleted_at,
        hard_delete_at=recording.hard_delete_at,
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
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Recording {recording_id} not found")

    if not recording.deleted:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Recording is not deleted")

    if recording.delete_state != "soft":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot restore: files already deleted. Recording can only be restored before files cleanup.",
        )

    # Get user config (merged with defaults)
    user_config_repo = UserConfigRepository(ctx.session)
    user_config = await user_config_repo.get_effective_config(ctx.user_id)

    await recording_repo.restore(recording, user_config)
    await ctx.session.commit()

    logger.info(f"Restored | {format_details(rec=recording_id, user=short_user_id(ctx.user_id))}")

    return RestoreRecordingResponse(
        message="Recording restored successfully",
        recording_id=recording.id,
        restored_at=datetime.now(UTC),
        expire_at=recording.expire_at,
    )
