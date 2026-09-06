"""Public share link endpoints — no authentication required for read access."""

from __future__ import annotations

import asyncio
import uuid
from enum import IntEnum
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import RedirectResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.core.context import ServiceContext
from api.core.dependencies import get_service_context
from api.dependencies import get_db_session
from api.helpers.playlist_description import render_playlist_description
from api.helpers.share_stats import build_share_stats_from_recording
from api.repositories.playlist_repo import PlaylistRepository
from api.repositories.recording_repos import RecordingRepository
from api.repositories.share_event_repo import ShareEventRepository
from api.schemas.playlist import PublicPlaylistItem, PublicPlaylistResponse
from api.schemas.share import (
    PublicRecordingResponse,
    ShareAnalyticsResponse,
    ShareCreateResponse,
    ShareDailyPoint,
)
from api.services.playlist_service import (
    SHARE_NOT_FOUND,
    assert_public_download,
    is_playable,
    item_unavailable_reason,
    poster_url_map,
)
from api.services.share_observability import ShareObservabilityService, fill_daily_series
from config.settings import get_settings
from database.models import RecordingModel
from database.share_models import ShareArtifactType
from logger import get_logger

router = APIRouter(tags=["Share"])
logger = get_logger()
_observability = ShareObservabilityService()

_SHARE_FILE_TYPES = Literal["srt", "vtt", "transcript_json", "transcript_txt", "transcript_words"]


class ShareAnalyticsDays(IntEnum):
    """Allowed analytics window sizes (query param coerces from string)."""

    WEEK = 7
    MONTH = 28


async def _get_recording_by_share_token(token: uuid.UUID, session: AsyncSession) -> RecordingModel:
    """Lookup a non-deleted recording with an enabled share link. Raises 404 if not found."""
    result = await session.execute(
        select(RecordingModel)
        .options(selectinload(RecordingModel.owner))
        .where(RecordingModel.share_token == token, RecordingModel.deleted == False)  # noqa: E712
    )
    recording = result.scalar_one_or_none()
    if not recording or not recording.share_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=SHARE_NOT_FOUND)
    return recording


async def _track_page_view_safe(recording: RecordingModel, request: Request) -> None:
    try:
        await _observability.record_page_view(recording, request)
    except Exception as exc:
        logger.warning("share page_view tracking failed (ignored): {!r}", exc)


async def _track_download_safe(recording: RecordingModel, request: Request, artifact_type: str) -> None:
    try:
        await _observability.record_download(recording, request, artifact_type)
    except Exception as exc:
        logger.warning("share download tracking failed (ignored): {!r}", exc)


async def _respond_page_view_beacon(recording: RecordingModel | None, request: Request) -> Response:
    """Always 204: missing/revoked links must not leak, tracking must not fail the page."""
    if recording is not None and not recording.deleted:
        await _track_page_view_safe(recording, request)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


async def _redirect_to_poster(session: AsyncSession, user_id: str, recordings: list) -> RedirectResponse:
    """302 to a presigned poster; 404 when none of the recordings have one."""
    posters = await poster_url_map(session, user_id, recordings)
    for rec in recordings:
        if rec is None:
            continue
        url = posters.get(rec.id)
        if url:
            return RedirectResponse(url=url, status_code=status.HTTP_302_FOUND)
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Poster not available")


async def _get_enabled_playlist(token: uuid.UUID, session: AsyncSession):
    playlist = await PlaylistRepository(session).get_by_share_token(token)
    if not playlist or not playlist.share_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=SHARE_NOT_FOUND)
    return playlist


async def _playlist_item_or_404(playlist, item_id: int):
    item = next((i for i in playlist.items if i.id == item_id), None)
    recording = item.recording if item else None
    if not item or recording is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Share link not found or has been revoked")
    return item, recording


async def _build_public_recording_response(
    recording: RecordingModel,
    session: AsyncSession,
    *,
    include_original: bool,
) -> PublicRecordingResponse:
    from file_storage.factory import get_storage_backend
    from file_storage.path_builder import StoragePathBuilder, to_storage_key
    from transcription_module.manager import get_transcription_manager

    user_slug = recording.owner.user_slug
    recording_id = recording.id

    storage = get_storage_backend()
    builder = StoragePathBuilder()
    cache_dir = builder.transcription_cache_dir(user_slug, recording_id)
    tx_dir = builder.transcription_dir(user_slug, recording_id)

    candidate_keys = {
        "transcript_json": to_storage_key(tx_dir / "master.json"),
        "transcript_txt": to_storage_key(cache_dir / "segments.txt"),
        "transcript_words": to_storage_key(cache_dir / "words.txt"),
        "srt": to_storage_key(cache_dir / "subtitles.srt"),
        "vtt": to_storage_key(cache_dir / "subtitles.vtt"),
    }
    candidate_exists = await asyncio.gather(*(storage.exists(path) for path in candidate_keys.values()))
    available_files = [
        key for (key, _path), exists in zip(candidate_keys.items(), candidate_exists, strict=True) if exists
    ]

    from api.helpers.template_renderer import TemplateRenderer, compute_metadata_preview

    summary: str | None = None
    questions: list[str] | None = None
    description: str | None = None
    topic_timestamps = recording.topic_timestamps
    main_topics = recording.main_topics
    active_version: dict | None = None

    tx_manager = get_transcription_manager()
    try:
        if await tx_manager.has_extracted(recording_id, user_slug):
            active_version = await tx_manager.get_active_extracted(recording_id, user_slug)
            if active_version:
                summary = active_version.get("summary") or None
                questions = active_version.get("questions") or None
                raw_desc = active_version.get("description") or None
                if raw_desc and "{{" not in raw_desc:
                    description = raw_desc
                if active_version.get("topic_timestamps"):
                    topic_timestamps = active_version["topic_timestamps"]
                if active_version.get("main_topics"):
                    main_topics = active_version["main_topics"]
    except Exception as exc:
        logger.debug("Could not load extracted for share | rec=%s err=%s", recording_id, exc)

    if not description:
        try:
            from api.services.config_resolver import ConfigResolver

            config_resolver = ConfigResolver(session)
            meta_cfg = await config_resolver.resolve_metadata_config(recording, recording.owner.id)
            desc_t = meta_cfg.get("description_template")
            if desc_t:
                render_ctx = TemplateRenderer.prepare_recording_context(recording, extracted_data=active_version)
                _, _, _, rendered = compute_metadata_preview(
                    title_template=None,
                    description_template=desc_t,
                    folder_path_template=None,
                    filename_template=None,
                    context=render_ctx,
                )
                description = rendered.get("description") or None
        except Exception as exc:
            logger.debug("Could not render description template for share | rec=%s err=%s", recording_id, exc)

    return PublicRecordingResponse(
        id=recording.id,
        display_name=recording.display_name,
        duration=recording.duration,
        start_time=recording.start_time,
        status=recording.status,
        topic_timestamps=topic_timestamps,
        main_topics=main_topics,
        summary=summary,
        questions=questions,
        description=description,
        available_files=available_files,
        has_processed_video=bool(recording.processed_video_path),
        has_original_video=bool(recording.local_video_path) if include_original else False,
        allow_video_download=bool(getattr(recording, "allow_video_download", True)),
        allow_files_download=bool(getattr(recording, "allow_files_download", True)),
    )


# ===========================================================================
# Owner-only endpoints (require auth)
# ===========================================================================


@router.post("/api/v1/recordings/{recording_id}/share", response_model=ShareCreateResponse)
async def create_share_link(
    recording_id: int,
    ctx: ServiceContext = Depends(get_service_context),
) -> ShareCreateResponse:
    """Enable the public share link. Mints a token once; re-enable keeps the same URL."""
    recording_repo = RecordingRepository(ctx.session)
    recording = await recording_repo.get_by_id(recording_id, ctx.user_id)
    if not recording:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recording not found")

    if not recording.share_token:
        recording.share_token = uuid.uuid4()
    recording.share_enabled = True
    await ctx.session.commit()
    await ctx.session.refresh(recording)

    if recording.share_token is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create share link")
    return ShareCreateResponse(share_token=recording.share_token, share_enabled=True)


@router.delete("/api/v1/recordings/{recording_id}/share", status_code=status.HTTP_204_NO_CONTENT)
async def disable_share_link(
    recording_id: int,
    ctx: ServiceContext = Depends(get_service_context),
) -> None:
    """Disable the public share link. The token is kept so Enable restores the same URL."""
    recording_repo = RecordingRepository(ctx.session)
    recording = await recording_repo.get_by_id(recording_id, ctx.user_id)
    if not recording:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recording not found")

    recording.share_enabled = False
    await ctx.session.commit()


@router.post("/api/v1/recordings/{recording_id}/share/rotate", response_model=ShareCreateResponse)
async def rotate_share_link(
    recording_id: int,
    ctx: ServiceContext = Depends(get_service_context),
) -> ShareCreateResponse:
    """Replace the share token. The previous URL returns 404."""
    recording_repo = RecordingRepository(ctx.session)
    recording = await recording_repo.get_by_id(recording_id, ctx.user_id)
    if not recording:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recording not found")

    recording.share_token = uuid.uuid4()
    recording.share_enabled = True
    await ctx.session.commit()
    await ctx.session.refresh(recording)

    if recording.share_token is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to rotate share link")
    return ShareCreateResponse(share_token=recording.share_token, share_enabled=True)


@router.get("/api/v1/recordings/{recording_id}/share/analytics", response_model=ShareAnalyticsResponse)
async def get_share_analytics(
    recording_id: int,
    days: ShareAnalyticsDays = Query(ShareAnalyticsDays.MONTH),
    ctx: ServiceContext = Depends(get_service_context),
) -> ShareAnalyticsResponse:
    """Share view/download analytics for a recording. Owner only."""
    period_days = int(days)
    recording_repo = RecordingRepository(ctx.session)
    recording = await recording_repo.get_by_id(recording_id, ctx.user_id)
    if not recording:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recording not found")

    repo = ShareEventRepository(ctx.session)
    aggregates = await repo.daily_aggregates(recording.id, days=period_days)
    downloads_by_type = await repo.downloads_by_type(recording.id, days=period_days)
    daily = [
        ShareDailyPoint(date=day, views=views, downloads=downloads)
        for day, views, downloads in fill_daily_series(aggregates, days=period_days)
    ]

    return ShareAnalyticsResponse(
        summary=build_share_stats_from_recording(recording),
        daily=daily,
        downloads_by_type=downloads_by_type,
    )


# ===========================================================================
# Public endpoints (no auth)
# ===========================================================================


@router.post("/api/v1/share/{share_token}/beacon", status_code=status.HTTP_204_NO_CONTENT)
async def share_page_beacon(
    share_token: uuid.UUID,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    """Record an anonymous page view from the public share page."""
    try:
        recording = await _get_recording_by_share_token(share_token, session)
    except HTTPException:
        recording = None
    return await _respond_page_view_beacon(recording, request)


@router.get("/api/v1/share/{share_token}", response_model=PublicRecordingResponse)
async def get_public_recording(
    share_token: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
) -> PublicRecordingResponse:
    """Return public recording metadata for the share page."""
    recording = await _get_recording_by_share_token(share_token, session)
    return await _build_public_recording_response(recording, session, include_original=True)


@router.get("/api/v1/share/{share_token}/poster")
async def get_share_poster(
    share_token: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
) -> RedirectResponse:
    """Presigned poster for Open Graph / Telegram. Revoked links 404 like other public share routes."""
    recording = await _get_recording_by_share_token(share_token, session)
    return await _redirect_to_poster(session, recording.user_id, [recording])


@router.get("/api/v1/share/{share_token}/media")
async def get_share_media(
    share_token: uuid.UUID,
    request: Request,
    media_kind: Literal["original", "processed"] = Query("processed", alias="type"),
    download: bool = Query(False),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    """Return a presigned video URL for the public share page.

    ``download=true`` generates a URL with ``Content-Disposition: attachment``
    so browsers trigger a file download rather than inline playback.
    """
    from file_storage.factory import get_storage_backend

    recording = await _get_recording_by_share_token(share_token, session)

    if download:
        assert_public_download(
            allow_video=bool(getattr(recording, "allow_video_download", True)),
            allow_files=True,
            kind="video",
        )

    raw_key = recording.local_video_path if media_kind == "original" else recording.processed_video_path
    if not raw_key:
        # Fallback: try the other variant
        raw_key = recording.processed_video_path if media_kind == "original" else recording.local_video_path
    if not raw_key:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video not available")

    storage = get_storage_backend()
    if not await storage.exists(raw_key):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video not available")

    if download:
        artifact = ShareArtifactType.VIDEO_ORIGINAL if media_kind == "original" else ShareArtifactType.VIDEO_PROCESSED
        await _track_download_safe(recording, request, artifact)

    expires_in = get_settings().storage.s3_presign_expires
    stem = f"recording-{recording.id}"
    dl_filename = f"{stem}.mp4" if download else None
    url = await storage.presigned_url(raw_key, expires_in=expires_in, download_filename=dl_filename)
    return {"url": url, "expires_in": expires_in}


async def _stream_share_file(
    recording: RecordingModel,
    file_type: _SHARE_FILE_TYPES,
    request: Request,
    inline: bool,
) -> StreamingResponse:
    from file_storage.factory import get_storage_backend
    from file_storage.path_builder import StoragePathBuilder, to_storage_key

    assert_public_download(
        allow_video=True,
        allow_files=bool(getattr(recording, "allow_files_download", True)),
        kind="files",
        inline=inline,
    )
    user_slug = recording.owner.user_slug
    recording_id = recording.id

    builder = StoragePathBuilder()
    cache_dir = builder.transcription_cache_dir(user_slug, recording_id)
    tx_dir = builder.transcription_dir(user_slug, recording_id)
    stem = f"recording-{recording_id}"

    file_map = {
        "srt": (to_storage_key(cache_dir / "subtitles.srt"), "application/x-subrip", f"{stem}.srt"),
        "vtt": (to_storage_key(cache_dir / "subtitles.vtt"), "text/vtt", f"{stem}.vtt"),
        "transcript_json": (to_storage_key(tx_dir / "master.json"), "application/json", f"{stem}_transcript.json"),
        "transcript_txt": (
            to_storage_key(cache_dir / "segments.txt"),
            "text/plain; charset=utf-8",
            f"{stem}_transcript.txt",
        ),
        "transcript_words": (
            to_storage_key(cache_dir / "words.txt"),
            "text/plain; charset=utf-8",
            f"{stem}_words.txt",
        ),
    }

    storage_key, media_type, attachment_name = file_map[file_type]
    storage = get_storage_backend()
    if not await storage.exists(storage_key):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    if not inline:
        await _track_download_safe(recording, request, file_type)

    content = await storage.load(storage_key)
    disposition = "inline" if inline else "attachment"
    return StreamingResponse(
        iter([content]),
        media_type=media_type,
        headers={"Content-Disposition": f'{disposition}; filename="{attachment_name}"'},
    )


@router.get("/api/v1/share/{share_token}/files/{file_type}")
async def download_share_file(
    share_token: uuid.UUID,
    file_type: _SHARE_FILE_TYPES,
    request: Request,
    inline: bool = Query(False, description="Player/subtitle fetch; not counted as a user download"),
    session: AsyncSession = Depends(get_db_session),
) -> StreamingResponse:
    """Download a transcription/subtitle artifact from a public share."""
    recording = await _get_recording_by_share_token(share_token, session)
    return await _stream_share_file(recording, file_type, request, inline)


def _public_playlist_items(playlist, posters: dict[int, str] | None = None) -> list[PublicPlaylistItem]:
    items: list[PublicPlaylistItem] = []
    for item in sorted(playlist.items, key=lambda i: i.position):
        rec = item.recording
        reason = item_unavailable_reason(rec) if rec else "deleted"
        items.append(
            PublicPlaylistItem(
                id=item.id,
                position=item.position,
                title=rec.display_name if rec else "Unknown",
                duration=(rec.final_duration or rec.duration) if rec else 0.0,
                start_time=rec.start_time if rec else item.created_at,
                playable=is_playable(rec) if rec else False,
                unavailable_reason=reason,
                poster_url=posters.get(rec.id) if posters and rec is not None else None,
            )
        )
    return items


@router.get("/api/v1/share/p/{share_token}", response_model=PublicPlaylistResponse)
async def get_public_playlist(
    share_token: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
) -> PublicPlaylistResponse:
    """Public playlist metadata. Empty playlists return 200 with items=[]."""
    playlist = await _get_enabled_playlist(share_token, session)
    posters = await poster_url_map(session, playlist.user_id, [i.recording for i in playlist.items])
    return PublicPlaylistResponse(
        name=playlist.name,
        description=render_playlist_description(playlist.description, playlist),
        items=_public_playlist_items(playlist, posters),
    )


@router.get("/api/v1/share/p/{share_token}/poster")
async def get_playlist_share_poster(
    share_token: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
) -> RedirectResponse:
    """Poster of the first playlist item that has one."""
    playlist = await _get_enabled_playlist(share_token, session)
    ordered = [i.recording for i in sorted(playlist.items, key=lambda i: i.position)]
    return await _redirect_to_poster(session, playlist.user_id, ordered)


@router.get("/api/v1/share/p/{share_token}/items/{item_id}", response_model=PublicRecordingResponse)
async def get_public_playlist_item(
    share_token: uuid.UUID,
    item_id: int,
    session: AsyncSession = Depends(get_db_session),
) -> PublicRecordingResponse:
    playlist = await _get_enabled_playlist(share_token, session)
    _item, recording = await _playlist_item_or_404(playlist, item_id)
    return await _build_public_recording_response(recording, session, include_original=False)


@router.post("/api/v1/share/p/{share_token}/items/{item_id}/beacon", status_code=status.HTTP_204_NO_CONTENT)
async def playlist_item_share_beacon(
    share_token: uuid.UUID,
    item_id: int,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    """Count a playlist watch as a page view on that recording (same counters / 30-min dedup)."""
    try:
        playlist = await _get_enabled_playlist(share_token, session)
        _item, recording = await _playlist_item_or_404(playlist, item_id)
    except HTTPException:
        recording = None
    if recording is not None and not is_playable(recording):
        recording = None
    return await _respond_page_view_beacon(recording, request)


@router.get("/api/v1/share/p/{share_token}/items/{item_id}/media")
async def get_public_playlist_item_media(
    share_token: uuid.UUID,
    item_id: int,
    request: Request,
    _media_kind: Literal["processed"] = Query("processed", alias="type"),
    download: bool = Query(False),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    from file_storage.factory import get_storage_backend

    playlist = await _get_enabled_playlist(share_token, session)
    _item, recording = await _playlist_item_or_404(playlist, item_id)
    if recording.deleted or recording.delete_state != "active":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video not available")
    if download:
        assert_public_download(
            allow_video=bool(getattr(recording, "allow_video_download", True)),
            allow_files=True,
            kind="video",
        )
    raw_key = recording.processed_video_path
    if not raw_key:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video not available")
    storage = get_storage_backend()
    if not await storage.exists(raw_key):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video not available")
    if download:
        await _track_download_safe(recording, request, ShareArtifactType.VIDEO_PROCESSED)
    expires_in = get_settings().storage.s3_presign_expires
    dl_filename = f"recording-{recording.id}.mp4" if download else None
    url = await storage.presigned_url(raw_key, expires_in=expires_in, download_filename=dl_filename)
    return {"url": url, "expires_in": expires_in}


@router.get("/api/v1/share/p/{share_token}/items/{item_id}/files/{file_type}")
async def download_public_playlist_file(
    share_token: uuid.UUID,
    item_id: int,
    file_type: _SHARE_FILE_TYPES,
    request: Request,
    inline: bool = Query(False),
    session: AsyncSession = Depends(get_db_session),
) -> StreamingResponse:
    playlist = await _get_enabled_playlist(share_token, session)
    _item, recording = await _playlist_item_or_404(playlist, item_id)
    if recording.deleted or recording.delete_state != "active":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    return await _stream_share_file(recording, file_type, request, inline)
