"""Storage names and WebVTT cues for seek preview sprite sheets."""

from __future__ import annotations

import math
import secrets
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from fastapi import HTTPException
from fastapi.responses import RedirectResponse, Response

from file_storage.path_builder import StoragePathBuilder, to_storage_key
from logger import get_logger

if TYPE_CHECKING:
    from database.models import RecordingModel

PREVIEW_WIDTH = 320
PREVIEW_HEIGHT = 180
PREVIEW_COLUMNS = 10
PREVIEW_ROWS = 10
PREVIEW_CELLS = PREVIEW_COLUMNS * PREVIEW_ROWS
PREVIEW_MAX_FRAMES = 300
PREVIEW_QUEUE_LOCK_SECONDS = 3900
PREVIEW_FAILURE_COOLDOWN_SECONDS = 300
PREVIEW_MAX_ATTEMPTS = 3
_RELEASE_LOCK = "if redis.call('GET', KEYS[1]) == ARGV[1] then return redis.call('DEL', KEYS[1]) end return 0"
_RENEW_LOCK = "if redis.call('GET', KEYS[1]) == ARGV[1] then return redis.call('EXPIRE', KEYS[1], ARGV[2]) end return 0"
_CLAIM_LOCK = (
    "local value = redis.call('GET', KEYS[1]); "
    "if value == ARGV[1] then return redis.call('EXPIRE', KEYS[1], ARGV[2]) end; "
    "if not value then redis.call('SET', KEYS[1], ARGV[1], 'EX', ARGV[2]); return 1 end; "
    "return 0"
)
_START_POSTER_LOCK = (
    "local value = redis.call('GET', KEYS[1]); "
    "if not value or value == ARGV[1] then "
    "redis.call('SET', KEYS[1], ARGV[2], 'EX', ARGV[3]); return 1 end; "
    "return 0"
)


def preview_queue_key(recording_id: int) -> str:
    return f"share:preview:{recording_id}"


def poster_queue_key(recording_id: int) -> str:
    return f"share:poster:{recording_id}"


def preview_source_revision(recording: RecordingModel) -> tuple[str | None, datetime | None]:
    """Identify the processed video independently of metadata and view counts."""
    from models.recording import ProcessingStageType

    trimmed_at = next(
        (stage.completed_at for stage in recording.processing_stages if stage.stage_type == ProcessingStageType.TRIM),
        None,
    )
    return recording.processed_video_path, trimmed_at


async def preview_index_matches_source(recording: RecordingModel) -> bool:
    """Never serve an index left behind by a later trim or failed invalidation."""
    from sqlalchemy import and_, select

    from api.dependencies import get_async_session_maker
    from database.models import PreviewMakerStageModel, ProcessingStageModel, RecordingModel
    from models.recording import ProcessingStageType

    async with get_async_session_maker()() as session:
        row = (
            await session.execute(
                select(
                    PreviewMakerStageModel.status,
                    PreviewMakerStageModel.source_video_path,
                    PreviewMakerStageModel.source_trimmed_at,
                    RecordingModel.processed_video_path,
                    ProcessingStageModel.completed_at,
                )
                .join(RecordingModel, RecordingModel.id == PreviewMakerStageModel.recording_id)
                .outerjoin(
                    ProcessingStageModel,
                    and_(
                        ProcessingStageModel.recording_id == RecordingModel.id,
                        ProcessingStageModel.stage_type == ProcessingStageType.TRIM,
                    ),
                )
                .where(RecordingModel.id == recording.id, RecordingModel.user_id == recording.user_id)
            )
        ).one_or_none()
    return bool(row and row[0] == "COMPLETED" and (row[1], row[2]) == (row[3], row[4]))


async def mark_preview_maker_stage(
    recording_id: int,
    user_id: str,
    status: str,
    token: str,
    *,
    error: str | None = None,
    ignore_failure_cooldown: bool = False,
    expected_run_token: str | None = None,
    expected_status: str = "IN_PROGRESS",
) -> bool | None:
    """Persist the optional stage; None means this token is already running."""
    from api.dependencies import get_async_session_maker
    from api.repositories.recording_repos import RecordingRepository
    from database.models import PreviewMakerStageModel

    async with get_async_session_maker()() as session:
        recording = await RecordingRepository(session).get_by_id(recording_id, user_id)
        if not recording or not recording.processed_video_path:
            return False
        source_path, trimmed_at = preview_source_revision(recording)
        stage = await session.get(PreviewMakerStageModel, recording_id, with_for_update=True)
        now = datetime.now(UTC)
        if status == "PENDING":
            if expected_run_token is not None and (
                stage is None or stage.status != expected_status or stage.run_token != expected_run_token
            ):
                return False
            same_source = bool(
                stage is not None and stage.source_video_path == source_path and stage.source_trimmed_at == trimmed_at
            )
            if (
                not ignore_failure_cooldown
                and same_source
                and stage is not None
                and stage.status == "FAILED"
                and stage.attempt_count >= PREVIEW_MAX_ATTEMPTS
            ):
                return False
            if (
                not ignore_failure_cooldown
                and stage is not None
                and stage.status == "FAILED"
                and stage.source_video_path == source_path
                and stage.source_trimmed_at == trimmed_at
                and stage.failed_at is not None
                and now - stage.failed_at < timedelta(seconds=PREVIEW_FAILURE_COOLDOWN_SECONDS)
            ):
                return False
            if stage is None:
                stage = PreviewMakerStageModel(recording_id=recording_id)
                session.add(stage)
            stage.run_token = token
            stage.attempt_count = (stage.attempt_count or 0) + 1 if same_source else 1
            stage.queued_at = now
            stage.source_video_path = source_path
            stage.source_trimmed_at = trimmed_at
            stage.status = status
            stage.started_at = None
            stage.completed_at = None
            stage.failed_at = None
            stage.failed_reason = None
        elif (
            stage is None
            or stage.run_token != token
            or stage.source_video_path != source_path
            or stage.source_trimmed_at != trimmed_at
        ):
            return False
        elif status == "IN_PROGRESS":
            if stage.status == "IN_PROGRESS":
                return None
            if stage.status != "PENDING":
                return False
            stage.status = status
            stage.started_at = now
        elif status == "COMPLETED":
            if stage.status != expected_status:
                return False
            stage.status = status
            stage.completed_at = now
            stage.failed_at = None
            stage.failed_reason = None
        elif status == "FAILED":
            if stage.status != expected_status:
                return False
            stage.status = status
            stage.failed_at = now
            stage.failed_reason = (error or "Preview generation failed")[:1000]
        else:
            raise ValueError(f"Unknown preview stage status: {status}")
        await session.commit()
        return True


async def release_queue_lock(redis, key: str, token: str) -> None:
    """Release only the lock owned by this task, never a newer queue claim."""
    await redis.eval(_RELEASE_LOCK, 1, key, token)


async def release_preview_queue_lock(redis, recording_id: int, token: str) -> None:
    await release_queue_lock(redis, preview_queue_key(recording_id), token)


async def renew_preview_queue_lock(redis, recording_id: int, token: str) -> bool:
    """Extend a live claim only while this worker still owns it."""
    return bool(await redis.eval(_RENEW_LOCK, 1, preview_queue_key(recording_id), token, PREVIEW_QUEUE_LOCK_SECONDS))


async def claim_queue_lock(redis, key: str, token: str) -> bool:
    """Let a delayed message reclaim an expired queue lock, but never steal a newer one."""
    return bool(await redis.eval(_CLAIM_LOCK, 1, key, token, PREVIEW_QUEUE_LOCK_SECONDS))


async def claim_preview_queue_lock(redis, recording_id: int, token: str) -> bool:
    return await claim_queue_lock(redis, preview_queue_key(recording_id), token)


async def start_poster_queue_lock(redis, recording_id: int, token: str) -> bool:
    """Turn a queued claim into a running claim; duplicate deliveries cannot start twice."""
    return bool(
        await redis.eval(
            _START_POSTER_LOCK,
            1,
            poster_queue_key(recording_id),
            token,
            f"{token}:running",
            PREVIEW_QUEUE_LOCK_SECONDS,
        )
    )


async def release_poster_queue_lock(redis, recording_id: int, token: str) -> None:
    await release_queue_lock(redis, poster_queue_key(recording_id), f"{token}:running")


async def enqueue_poster(redis, recording_id: int, user_id: str) -> bool:
    """Publish one legacy poster fallback per recording across API instances."""
    import asyncio

    from api.tasks.processing import generate_poster

    token = secrets.token_hex(16)
    key = poster_queue_key(recording_id)
    if not await redis.set(key, token, nx=True, ex=PREVIEW_QUEUE_LOCK_SECONDS):
        return False
    try:
        await asyncio.to_thread(generate_poster.delay, recording_id, user_id, token)
    except Exception:
        await release_queue_lock(redis, key, token)
        raise
    return True


async def enqueue_video_previews(
    redis,
    recording_id: int,
    user_id: str,
    *,
    force: bool = False,
    expected_run_token: str | None = None,
    expected_status: str = "IN_PROGRESS",
) -> bool:
    """Deduplicate API and post-trim requests before publishing CPU work."""
    import asyncio

    from api.tasks.processing import generate_video_previews

    token = secrets.token_hex(16)
    if not await redis.set(preview_queue_key(recording_id), token, nx=True, ex=PREVIEW_QUEUE_LOCK_SECONDS):
        return False
    try:
        if not await mark_preview_maker_stage(
            recording_id,
            user_id,
            "PENDING",
            token,
            expected_run_token=expected_run_token,
            expected_status=expected_status,
        ):
            await release_preview_queue_lock(redis, recording_id, token)
            return False
    except Exception:
        await release_preview_queue_lock(redis, recording_id, token)
        raise
    try:
        # Celery publishing is synchronous; never block the FastAPI event loop.
        await asyncio.to_thread(generate_video_previews.delay, recording_id, user_id, force, token)
    except Exception as exc:
        await release_preview_queue_lock(redis, recording_id, token)
        try:
            await mark_preview_maker_stage(recording_id, user_id, "FAILED", token, error=str(exc))
        except Exception as stage_exc:
            get_logger(__name__).warning("Could not mark PREVIEW_MAKER failed for {}: {}", recording_id, stage_exc)
        raise
    return True


def preview_step(duration: float) -> int:
    """Keep long lectures bounded to at most 300 preview frames."""
    return max(20, math.ceil(duration / PREVIEW_MAX_FRAMES))


def preview_key(user_slug: int, recording_id: int, name: str) -> str:
    root = StoragePathBuilder().recording_root(user_slug, recording_id)
    return to_storage_key(root / "previews" / name)


def preview_vtt(duration: float, step: int) -> str:
    cues = ["WEBVTT", ""]
    for index in range(math.ceil(duration / step)):
        start = index * step
        end = min((index + 1) * step, duration)
        sheet = index // PREVIEW_CELLS
        cell = index % PREVIEW_CELLS
        x = (cell % PREVIEW_COLUMNS) * PREVIEW_WIDTH
        y = (cell // PREVIEW_COLUMNS) * PREVIEW_HEIGHT
        cues.extend(
            [
                f"{_timestamp(start)} --> {_timestamp(end)}",
                f"preview/{sheet}.jpg#xywh={x},{y},{PREVIEW_WIDTH},{PREVIEW_HEIGHT}",
                "",
            ]
        )
    return "\n".join(cues)


def _timestamp(seconds: float) -> str:
    milliseconds = round(seconds * 1000)
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"


async def serve_preview_vtt(recording: RecordingModel) -> Response:
    """Return the completed VTT or queue a bounded background build."""
    from api.dependencies import get_redis
    from file_storage.factory import get_storage_backend
    from logger import get_logger

    if not recording.processed_video_path or not recording.user_id:
        raise HTTPException(status_code=404, detail="Video not available")
    key = preview_key(recording.owner.user_slug, recording.id, "storyboard.vtt")
    storage = get_storage_backend()
    index_exists = await storage.exists(key)
    if index_exists and await preview_index_matches_source(recording):
        return Response(
            content=await storage.load(key), media_type="text/vtt", headers={"Cache-Control": "private, max-age=60"}
        )

    try:
        redis = await get_redis()
        await enqueue_video_previews(redis, recording.id, recording.user_id, force=index_exists)
    except Exception as exc:
        # The public endpoint must not enqueue unbounded CPU work if deduplication is unavailable.
        get_logger(__name__).warning("Could not queue video previews for recording {}: {}", recording.id, exc)
    return Response(status_code=202, headers={"Retry-After": "5", "Cache-Control": "no-store"})


async def redirect_preview_sheet(recording: RecordingModel, sheet: int) -> Response:
    """Resolve one sprite through the same owner or share authorization as video."""
    from config.settings import get_settings
    from file_storage.backends.local import LocalStorageBackend
    from file_storage.factory import get_storage_backend

    if sheet < 0 or sheet >= 3 or not recording.processed_video_path:
        raise HTTPException(status_code=404, detail="Preview not available")
    if not await preview_index_matches_source(recording):
        raise HTTPException(status_code=404, detail="Preview not available")
    key = preview_key(recording.owner.user_slug, recording.id, f"{sheet}.jpg")
    storage = get_storage_backend()
    if not await storage.exists(key):
        raise HTTPException(status_code=404, detail="Preview not available")
    if isinstance(storage, LocalStorageBackend):
        return Response(
            content=await storage.load(key), media_type="image/jpeg", headers={"Cache-Control": "private, max-age=60"}
        )
    url = await storage.presigned_url(key, expires_in=get_settings().storage.s3_presign_expires, inline=True)
    return RedirectResponse(url, status_code=302, headers={"Cache-Control": "private, max-age=60"})
