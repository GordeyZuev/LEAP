"""Public share link endpoints — no authentication required for read access."""

from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.core.context import ServiceContext
from api.core.dependencies import get_service_context
from api.dependencies import get_db_session
from api.repositories.recording_repos import RecordingRepository
from api.schemas.share import PublicRecordingResponse, ShareCreateResponse
from config.settings import get_settings
from database.models import RecordingModel
from logger import get_logger

router = APIRouter(tags=["Share"])
logger = get_logger()

_SHARE_FILE_TYPES = Literal["srt", "vtt", "transcript_json", "transcript_txt", "transcript_words"]


async def _get_recording_by_share_token(token: uuid.UUID, session: AsyncSession) -> RecordingModel:
    """Lookup a non-deleted recording by share_token. Raises 404 if not found."""
    result = await session.execute(
        select(RecordingModel)
        .options(selectinload(RecordingModel.owner))
        .where(RecordingModel.share_token == token, RecordingModel.deleted == False)  # noqa: E712
    )
    recording = result.scalar_one_or_none()
    if not recording:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Share link not found or has been revoked")
    return recording


# ===========================================================================
# Owner-only endpoints (require auth)
# ===========================================================================


@router.post("/api/v1/recordings/{recording_id}/share", response_model=ShareCreateResponse)
async def create_share_link(
    recording_id: int,
    ctx: ServiceContext = Depends(get_service_context),
) -> ShareCreateResponse:
    """Generate a public share token for a recording. Owner only."""
    recording_repo = RecordingRepository(ctx.session)
    recording = await recording_repo.get_by_id(recording_id, ctx.user_id)
    if not recording:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recording not found")

    if not recording.share_token:
        recording.share_token = uuid.uuid4()
        await ctx.session.commit()
        await ctx.session.refresh(recording)

    return ShareCreateResponse(share_token=recording.share_token)


@router.delete("/api/v1/recordings/{recording_id}/share", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_share_link(
    recording_id: int,
    ctx: ServiceContext = Depends(get_service_context),
) -> None:
    """Revoke the public share token for a recording. Owner only."""
    recording_repo = RecordingRepository(ctx.session)
    recording = await recording_repo.get_by_id(recording_id, ctx.user_id)
    if not recording:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recording not found")

    recording.share_token = None
    await ctx.session.commit()


# ===========================================================================
# Public endpoints (no auth)
# ===========================================================================


@router.get("/api/v1/share/{share_token}", response_model=PublicRecordingResponse)
async def get_public_recording(
    share_token: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
) -> PublicRecordingResponse:
    """Return public recording metadata for the share page."""
    from file_storage.factory import get_storage_backend
    from file_storage.path_builder import StoragePathBuilder, to_storage_key
    from transcription_module.manager import get_transcription_manager

    recording = await _get_recording_by_share_token(share_token, session)
    user_slug = recording.owner.user_slug
    recording_id = recording.id

    storage = get_storage_backend()
    builder = StoragePathBuilder()
    cache_dir = builder.transcription_cache_dir(user_slug, recording_id)
    tx_dir = builder.transcription_dir(user_slug, recording_id)

    # Check which artifacts exist in storage
    candidate_keys = {
        "srt": to_storage_key(cache_dir / "subtitles.srt"),
        "vtt": to_storage_key(cache_dir / "subtitles.vtt"),
        "transcript_json": to_storage_key(tx_dir / "master.json"),
        "transcript_txt": to_storage_key(cache_dir / "segments.txt"),
        "transcript_words": to_storage_key(cache_dir / "words.txt"),
    }
    available_files = [key for key, path in candidate_keys.items() if await storage.exists(path)]

    # Load active topic version from extracted.json for summary, questions, description
    from api.helpers.template_renderer import TemplateRenderer, compute_metadata_preview

    summary: str | None = None
    questions: list[str] | None = None
    description: str | None = None
    topic_timestamps = recording.topic_timestamps
    main_topics = recording.main_topics
    active_version: dict | None = None  # active version dict for TemplateRenderer context

    tx_manager = get_transcription_manager()
    try:
        if await tx_manager.has_extracted(recording_id, user_slug):
            active_version = await tx_manager.get_active_extracted(recording_id, user_slug)
            if active_version:
                summary = active_version.get("summary") or None
                questions = active_version.get("questions") or None
                raw_desc = active_version.get("description") or None
                # Jinja templates in description field are rendered below
                if raw_desc and "{{" not in raw_desc:
                    description = raw_desc
                # Prefer extracted data over denormalized model fields
                if active_version.get("topic_timestamps"):
                    topic_timestamps = active_version["topic_timestamps"]
                if active_version.get("main_topics"):
                    main_topics = active_version["main_topics"]
    except Exception as exc:
        logger.debug("Could not load extracted for share | rec=%s err=%s", recording_id, exc)

    # If no plain-text description, render from resolved metadata config (user defaults → template → preferences)
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
                logger.debug("Rendered description from template | rec=%s len=%s", recording_id, len(description or ""))
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
        has_original_video=bool(recording.local_video_path),
    )


@router.get("/api/v1/share/{share_token}/media")
async def get_share_media(
    share_token: uuid.UUID,
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

    raw_key = recording.local_video_path if media_kind == "original" else recording.processed_video_path
    if not raw_key:
        # Fallback: try the other variant
        raw_key = recording.processed_video_path if media_kind == "original" else recording.local_video_path
    if not raw_key:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video not available")

    storage = get_storage_backend()
    if not await storage.exists(raw_key):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video not available")

    expires_in = get_settings().storage.s3_presign_expires
    stem = f"recording-{recording.id}"
    dl_filename = f"{stem}.mp4" if download else None
    url = await storage.presigned_url(raw_key, expires_in=expires_in, download_filename=dl_filename)
    return {"url": url, "expires_in": expires_in}


@router.get("/api/v1/share/{share_token}/files/{file_type}")
async def download_share_file(
    share_token: uuid.UUID,
    file_type: _SHARE_FILE_TYPES,
    session: AsyncSession = Depends(get_db_session),
) -> StreamingResponse:
    """Download a transcription/subtitle artifact from a public share."""
    from file_storage.factory import get_storage_backend
    from file_storage.path_builder import StoragePathBuilder, to_storage_key

    recording = await _get_recording_by_share_token(share_token, session)
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

    content = await storage.load(storage_key)
    return StreamingResponse(
        iter([content]),
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{attachment_name}"'},
    )
