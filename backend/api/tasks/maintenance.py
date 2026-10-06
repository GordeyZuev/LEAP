"""Celery tasks for system maintenance."""

import asyncio
from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import selectinload

from api.celery_app import celery_app
from api.dependencies import get_async_session_maker
from api.repositories.auth_repos import RefreshTokenRepository
from api.repositories.config_repos import UserConfigRepository
from api.repositories.recording_repos import RecordingRepository
from config.settings import get_settings
from database.models import RecordingModel
from logger import get_logger

logger = get_logger()
settings = get_settings()


@celery_app.task(
    name="maintenance.cleanup_expired_tokens",
    max_retries=settings.celery.maintenance_max_retries,
    default_retry_delay=settings.celery.maintenance_retry_delay,
)
def cleanup_expired_tokens_task():
    """
    Periodic task for cleaning expired refresh tokens.

    Runs daily (configured in Celery Beat).
    """
    try:
        logger.info("Starting cleanup of expired refresh tokens...")

        # Start async cleanup
        async def cleanup():
            session_maker = get_async_session_maker()

            async with session_maker() as session:
                token_repo = RefreshTokenRepository(session)
                return await token_repo.delete_expired()

        # Use asyncio.run() for proper event loop isolation
        deleted_count = asyncio.run(cleanup())

        logger.info(f"Cleanup completed: {deleted_count} expired tokens deleted")

        return {
            "status": "success",
            "deleted_tokens": deleted_count,
            "message": f"Cleaned up {deleted_count} expired refresh tokens",
        }

    except Exception as e:
        logger.opt(exception=True).error("Failed to cleanup expired tokens: {}", e)
        return {"status": "error", "error": str(e)}


@celery_app.task(
    name="maintenance.auto_expire_recordings",
    max_retries=settings.celery.maintenance_max_retries,
    default_retry_delay=settings.celery.maintenance_retry_delay,
)
def auto_expire_recordings_task():
    """
    Auto-expire active recordings where expire_at has passed.

    Runs daily at 3:30 UTC (configured in Celery Beat).
    """
    try:
        logger.info("Starting auto-expire of recordings...")

        async def expire():
            session_maker = get_async_session_maker()

            expired_count = 0
            errors = []

            now = datetime.now(UTC)
            async with session_maker() as session:
                query = (
                    select(RecordingModel)
                    .where(
                        RecordingModel.deleted == False,  # noqa: E712
                        RecordingModel.retention_exempt.is_not(True),
                        or_(
                            RecordingModel.expire_at.is_(None),
                            RecordingModel.expire_at < now,
                            RecordingModel.retention_exempt.is_(None),
                        ),
                    )
                    .options(selectinload(RecordingModel.owner))
                )
                result = await session.execute(query)
                recordings = result.scalars().all()

            logger.info(f"Found {len(recordings)} recordings to check for auto-expire")

            from api.services.retention import (
                apply_retention_deadline,
                effective_retention_exempt,
                template_retention_flags,
            )

            async with session_maker() as session:
                flags = await template_retention_flags(session, recordings)

            # Process each in separate transaction
            for recording in recordings:
                try:
                    async with session_maker() as tx_session:
                        recording_repo = RecordingRepository(tx_session)
                        user_config_repo = UserConfigRepository(tx_session)

                        rec = await tx_session.get(RecordingModel, recording.id)
                        if not rec or rec.deleted:
                            continue
                        template_exempt = flags.get(rec.id, False)
                        if effective_retention_exempt(rec.retention_exempt, template_exempt):
                            if rec.expire_at is not None:
                                rec.expire_at = None
                                await tx_session.commit()
                            continue

                        checked_at = datetime.now(UTC)
                        if rec.expire_at is not None and rec.expire_at >= checked_at:
                            continue
                        user_config = await user_config_repo.get_effective_config(rec.user_id)
                        if rec.expire_at is None:
                            apply_retention_deadline(rec, template_exempt, user_config, checked_at)
                            await tx_session.commit()
                            continue

                        await recording_repo.auto_expire(rec, user_config, template_exempt=template_exempt)
                        await tx_session.commit()
                        expired_count += 1

                except Exception as e:
                    error_msg = f"Failed to auto-expire recording {recording.id}: {e}"
                    logger.error(error_msg)
                    errors.append(error_msg)

            return expired_count, errors

        # Execute async function
        # Use asyncio.run() for proper event loop isolation
        expired_count, errors = asyncio.run(expire())

        if errors:
            logger.warning(f"Auto-expire completed with {len(errors)} errors")

        logger.info(f"Auto-expire completed: {expired_count} recordings expired")

        return {
            "status": "success" if not errors else "partial_success",
            "expired": expired_count,
            "errors_count": len(errors),
            "errors": errors[:10] if errors else [],
            "message": f"Auto-expired {expired_count} recordings",
        }

    except Exception as e:
        logger.opt(exception=True).error("Failed to auto-expire recordings: {}", e)
        return {"status": "error", "error": str(e)}


@celery_app.task(
    name="maintenance.hard_delete_recordings",
    max_retries=settings.celery.maintenance_max_retries,
    default_retry_delay=settings.celery.maintenance_retry_delay,
)
def hard_delete_recordings_task():
    """
    Level 2: Hard delete recordings where hard_delete_at passed.

    Complete removal from DB (including transcription_dir with master.json).
    Runs daily at 5:00 UTC (configured in Celery Beat).
    """
    try:
        logger.info("Starting hard delete of recordings...")

        async def cleanup():
            session_maker = get_async_session_maker()

            deleted_count = 0
            errors = []

            # Find recordings where hard_delete_at passed
            async with session_maker() as session:
                query = (
                    select(RecordingModel)
                    .where(
                        RecordingModel.hard_delete_at.isnot(None),
                        RecordingModel.hard_delete_at < datetime.now(UTC),
                        RecordingModel.delete_state.in_(("soft", "hard")),
                    )
                    .options(selectinload(RecordingModel.owner))
                )
                result = await session.execute(query)
                recordings = result.scalars().all()

            logger.info(f"Found {len(recordings)} recordings for hard delete")

            # Delete each in separate transaction
            for recording in recordings:
                try:
                    async with session_maker() as tx_session:
                        recording_repo = RecordingRepository(tx_session)

                        # Refetch recording
                        rec = await tx_session.get(RecordingModel, recording.id)
                        if not rec:
                            logger.warning(f"Recording {recording.id} not found, skipping")
                            continue
                        from api.services.retention import still_due_for_hard_delete

                        if not still_due_for_hard_delete(rec, datetime.now(UTC)):
                            logger.info(f"Skipping hard delete | rec={recording.id} no longer due")
                            continue

                        logger.debug(
                            f"Hard deleting recording {rec.id} "
                            f"(user={rec.user_id}, deleted_at={rec.deleted_at}, "
                            f"hard_delete_at={rec.hard_delete_at})"
                        )

                        # Hard delete
                        await recording_repo.delete(rec)
                        await tx_session.commit()
                        deleted_count += 1

                except Exception as e:
                    error_msg = f"Failed to hard delete recording {recording.id}: {e}"
                    logger.error(error_msg)
                    errors.append(error_msg)

            return deleted_count, errors

        # Execute async function
        # Use asyncio.run() for proper event loop isolation
        deleted_count, errors = asyncio.run(cleanup())

        if errors:
            logger.warning(f"Hard delete completed with {len(errors)} errors")

        logger.info(f"Hard delete completed: {deleted_count} recordings deleted")

        return {
            "status": "success" if not errors else "partial_success",
            "hard_deleted": deleted_count,
            "errors_count": len(errors),
            "errors": errors[:10] if errors else [],
            "message": f"Hard deleted {deleted_count} recordings",
        }

    except Exception as e:
        logger.opt(exception=True).error("Failed to hard delete recordings: {}", e)
        return {"status": "error", "error": str(e)}


@celery_app.task(
    name="maintenance.cleanup_playlist_blank_items",
    max_retries=settings.celery.maintenance_max_retries,
    default_retry_delay=settings.celery.maintenance_retry_delay,
)
def cleanup_playlist_blank_items_task():
    """Remove playlist items that point at blank or not-yet-playable recordings (legacy early membership)."""

    from api.services.playlist_service import item_unavailable_reason
    from database.playlist_models import PlaylistItemModel

    async def _cleanup() -> int:
        session_maker = get_async_session_maker()
        async with session_maker() as session:
            result = await session.execute(
                select(PlaylistItemModel, RecordingModel).join(
                    RecordingModel, PlaylistItemModel.recording_id == RecordingModel.id
                )
            )
            removed = 0
            for item, recording in result.all():
                if item_unavailable_reason(recording):
                    await session.delete(item)
                    removed += 1
            if removed:
                await session.commit()
            return removed

    try:
        deleted = asyncio.run(_cleanup())
        logger.info(f"cleanup_playlist_blank_items: removed={deleted}")
        return {"status": "success", "removed": deleted}
    except Exception as e:
        logger.opt(exception=True).error("Failed to cleanup playlist blank items: {}", e)
        return {"status": "error", "error": str(e)}


@celery_app.task(
    name="maintenance.cleanup_temp_files",
    max_retries=settings.celery.maintenance_max_retries,
    default_retry_delay=settings.celery.maintenance_retry_delay,
)
def cleanup_temp_files_task(max_age_hours: int = 6):
    """Delete stale files in ``storage/temp/`` left behind by failed pipelines.

    Pipeline stages remove their own temp files in ``finally`` blocks, but a hard
    kill (OOM, SIGKILL, worker crash) can leave temps behind. This safety-net
    sweep runs hourly via Celery Beat and removes anything older than
    ``max_age_hours`` (default 6h).
    """
    import time
    from pathlib import Path

    from file_storage.path_builder import StoragePathBuilder

    try:
        temp_dir: Path = StoragePathBuilder().temp_dir()
        if not temp_dir.exists():
            logger.debug(f"Temp dir does not exist: {temp_dir}")
            return {"status": "success", "deleted": 0, "message": "Temp dir absent"}

        cutoff = time.time() - max_age_hours * 3600
        deleted = 0
        errors: list[str] = []

        for child in temp_dir.iterdir():
            try:
                if child.is_file() and child.stat().st_mtime < cutoff:
                    child.unlink(missing_ok=True)
                    deleted += 1
            except Exception as exc:
                errors.append(f"{child.name}: {exc}")

        logger.info(f"cleanup_temp_files: deleted={deleted} errors={len(errors)} cutoff_h={max_age_hours}")
        return {
            "status": "success" if not errors else "partial_success",
            "deleted": deleted,
            "errors": errors[:10],
        }

    except Exception as e:
        logger.opt(exception=True).error("Failed to clean temp files: {}", e)
        return {"status": "error", "error": str(e)}


@celery_app.task(
    name="maintenance.reset_stale_active_recordings",
    max_retries=settings.celery.maintenance_max_retries,
    default_retry_delay=settings.celery.maintenance_retry_delay,
)
def reset_stale_active_recordings_task(stale_hours: float = 2.0):
    """
    Periodic task to reset on_air=True recordings whose pipeline has been
    running longer than `stale_hours`. Protects against worker crashes that
    leave on_air stuck without a live Celery task.

    Rolls back status to the nearest stable state and clears on_air /
    pipeline_task_id so smart_run can re-launch the pipeline cleanly.

    Runs every 30 minutes (configured in Celery Beat).
    """
    from datetime import timedelta

    from models.recording import ProcessingStageStatus, ProcessingStatus

    async def _reset():
        session_maker = get_async_session_maker()
        threshold = datetime.now(UTC) - timedelta(hours=stale_hours)

        async with session_maker() as session:
            # Also catch recordings where pipeline_started_at IS NULL — this happens when
            # a worker died before the orchestrator task had a chance to set it. Use
            # updated_at as the fallback staleness signal in that case.
            from sqlalchemy import or_

            result = await session.execute(
                select(RecordingModel)
                .where(RecordingModel.on_air.is_(True))
                .where(
                    or_(
                        RecordingModel.pipeline_started_at < threshold,
                        (RecordingModel.pipeline_started_at.is_(None)) & (RecordingModel.updated_at < threshold),
                    )
                )
                .options(
                    selectinload(RecordingModel.processing_stages),
                    selectinload(RecordingModel.outputs),
                )
            )
            stale = result.scalars().all()

            if not stale:
                return 0

            _rollback_map = {
                ProcessingStatus.DOWNLOADING: ProcessingStatus.INITIALIZED,
                ProcessingStatus.PROCESSING: ProcessingStatus.DOWNLOADED,
                ProcessingStatus.UPLOADING: ProcessingStatus.PROCESSED,
            }

            for rec in stale:
                rec.status = _rollback_map.get(rec.status, rec.status)
                for stage in rec.processing_stages:
                    if stage.status == ProcessingStageStatus.IN_PROGRESS:
                        stage.status = ProcessingStageStatus.PENDING
                        stage.started_at = None
                rec.on_air = False
                rec.pipeline_task_id = None
                logger.warning(
                    f"Stale pipeline reset | rec={rec.id} user={rec.user_id} "
                    f"started={rec.pipeline_started_at} new_status={rec.status}"
                )

            await session.commit()
            return len(stale)

    try:
        reset_count = asyncio.run(_reset())
        logger.info(f"reset_stale_active_recordings: reset={reset_count} threshold_h={stale_hours}")
        return {"status": "success", "reset": reset_count}
    except Exception as e:
        logger.opt(exception=True).error(f"Failed to reset stale active recordings: {e}")
        return {"status": "error", "error": str(e)}


@celery_app.task(
    name="maintenance.reconcile_transcription_ledger",
    max_retries=settings.celery.maintenance_max_retries,
    default_retry_delay=settings.celery.maintenance_retry_delay,
)
def reconcile_transcription_ledger_task():
    """Close AssemblyAI rows left in submitted, and copy DeepSeek usage from live files once."""
    try:

        async def reconcile():
            from api.services.resource_ledger import ResourceLedgerService, backfill_topic_tokens
            from assemblyai_module.config import AssemblyAIConfig
            from assemblyai_module.service import AssemblyAITranscriptionService

            session_maker = get_async_session_maker()
            closed = 0
            cutoff = datetime.now(UTC) - timedelta(hours=3)
            async with session_maker() as session:
                rows = await ResourceLedgerService(session).repo.submitted_transcriptions(cutoff)
                pending: list[tuple[str, int | None, str]] = []
                for row in rows:
                    job_id = row.provider_job_id
                    user_id = row.user_id
                    if not isinstance(job_id, str) or not job_id or not isinstance(user_id, str):
                        continue
                    recording_id = row.recording_id if isinstance(row.recording_id, int) else None
                    pending.append((user_id, recording_id, job_id))

            service = None
            try:
                service = AssemblyAITranscriptionService(AssemblyAIConfig.from_file("config/assemblyai_creds.json"))
            except Exception as exc:
                logger.warning(f"AssemblyAI reconcile skipped | error={exc}")

            if service is not None:
                for user_id, recording_id, job_id in pending:
                    if not job_id:
                        continue
                    try:
                        data = await service.fetch_transcript(job_id)
                    except Exception as exc:
                        logger.warning(f"AssemblyAI reconcile fetch failed | job={job_id} | error={exc}")
                        continue
                    status = data.get("status")
                    async with session_maker() as session:
                        ledger = ResourceLedgerService(session)
                        if status == "completed":
                            raw = data.get("audio_duration")
                            seconds = float(raw) if raw is not None else None
                            if seconds is None:
                                continue
                            model_used = data.get("speech_model_used")
                            await ledger.mark_transcription_completed(
                                user_id=user_id,
                                recording_id=recording_id,
                                provider_job_id=job_id,
                                audio_seconds=seconds,
                                model=model_used if isinstance(model_used, str) else None,
                            )
                            closed += 1
                        elif status == "error":
                            await ledger.mark_transcription_failed(provider_job_id=job_id)
                            closed += 1
                        await session.commit()

                async with session_maker() as session:
                    from api.services.resource_ledger import import_untracked_transcripts

                    imported = await import_untracked_transcripts(session, service)
                    await session.commit()
                    closed += imported

            async with session_maker() as session:
                await backfill_topic_tokens(session)
                await session.commit()
            return closed

        closed = asyncio.run(reconcile())
        logger.info(f"Transcription ledger reconcile closed {closed} rows")
        return {"status": "success", "closed": closed}
    except Exception as e:
        logger.opt(exception=True).error("Failed to reconcile transcription ledger: {}", e)
        return {"status": "error", "error": str(e)}


@celery_app.task(
    name="maintenance.snapshot_storage_usage",
    max_retries=settings.celery.maintenance_max_retries,
    default_retry_delay=settings.celery.maintenance_retry_delay,
)
def snapshot_storage_usage_task():
    """Hourly prefix size for users who have recordings. Quota itself still reads the live prefix."""
    try:
        from sqlalchemy import select

        from api.services.resource_ledger import ResourceLedgerService
        from database.auth_models import UserModel
        from file_storage.factory import get_storage_backend

        async def snapshot():
            session_maker = get_async_session_maker()
            hour = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
            storage = get_storage_backend()
            written = 0
            async with session_maker() as session:
                result = await session.execute(
                    select(UserModel.id, UserModel.user_slug).where(
                        UserModel.id.in_(select(RecordingModel.user_id).distinct())
                    )
                )
                users = result.all()
                ledger = ResourceLedgerService(session)
                for user_id, user_slug in users:
                    if user_slug is None:
                        continue
                    size = await storage.get_prefix_size(f"users/user_{user_slug:06d}/")
                    await ledger.record_storage_snapshot(user_id=user_id, stored_bytes=int(size), hour=hour)
                    written += 1
                await session.commit()
            return written

        written = asyncio.run(snapshot())
        logger.info(f"Storage snapshots written | users={written}")
        return {"status": "success", "users": written}
    except Exception as e:
        logger.opt(exception=True).error("Failed to snapshot storage: {}", e)
        return {"status": "error", "error": str(e)}
