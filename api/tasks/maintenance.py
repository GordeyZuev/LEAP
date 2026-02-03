"""Celery tasks for system maintenance."""

import asyncio
from datetime import datetime, timezone

from sqlalchemy import select
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
        logger.error("Failed to cleanup expired tokens: {}", str(e), exc_info=True)
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

            # Find active recordings where expire_at passed
            async with session_maker() as session:
                query = (
                    select(RecordingModel)
                    .where(
                        RecordingModel.deleted == False,  # noqa: E712
                        RecordingModel.expire_at.isnot(None),
                        RecordingModel.expire_at < datetime.now(timezone.utc),
                    )
                    .options(selectinload(RecordingModel.owner))
                )
                result = await session.execute(query)
                recordings = result.scalars().all()

            logger.info(f"Found {len(recordings)} recordings to auto-expire")

            # Process each in separate transaction
            for recording in recordings:
                try:
                    async with session_maker() as tx_session:
                        recording_repo = RecordingRepository(tx_session)
                        user_config_repo = UserConfigRepository(tx_session)

                        # Refetch recording
                        rec = await tx_session.get(RecordingModel, recording.id)
                        if not rec:
                            continue

                        # Get user config (merged with defaults)
                        user_config = await user_config_repo.get_effective_config(rec.user_id)

                        # Auto-expire
                        await recording_repo.auto_expire(rec, user_config)
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
        logger.error("Failed to auto-expire recordings: {}", str(e), exc_info=True)
        return {"status": "error", "error": str(e)}


@celery_app.task(
    name="maintenance.cleanup_recording_files",
    max_retries=settings.celery.maintenance_max_retries,
    default_retry_delay=settings.celery.maintenance_retry_delay,
)
def cleanup_recording_files_task():
    """
    Level 1: Clean up files for soft deleted recordings.

    Deletes videos/audio, keeps master.json and topics.json.
    Runs daily at 4:00 UTC (configured in Celery Beat).
    """
    try:
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload

        from api.repositories.recording_repos import RecordingRepository
        from database.models import RecordingModel

        logger.info("Starting cleanup of recording files...")

        async def cleanup():
            session_maker = get_async_session_maker()

            cleaned_count = 0
            errors = []

            # Get all soft deleted recordings with owner
            async with session_maker() as session:
                query = (
                    select(RecordingModel)
                    .where(RecordingModel.delete_state == "soft")
                    .options(selectinload(RecordingModel.owner))
                )
                result = await session.execute(query)
                recordings = result.scalars().all()

            logger.info(f"Found {len(recordings)} soft deleted recordings")

            # Check scheduled cleanup time
            for recording in recordings:
                try:
                    # CRITICAL: Check soft_deleted_at is not None
                    if not recording.soft_deleted_at:
                        logger.warning(
                            f"Recording {recording.id} has delete_state='soft' but soft_deleted_at is None, skipping"
                        )
                        continue

                    # Check if cleanup time has passed
                    if recording.soft_deleted_at >= datetime.now(timezone.utc):
                        logger.debug(
                            f"Skipping recording {recording.id}: cleanup scheduled for {recording.soft_deleted_at}"
                        )
                        continue

                    async with session_maker() as tx_session:
                        recording_repo = RecordingRepository(tx_session)
                        rec = await tx_session.get(RecordingModel, recording.id)
                        if not rec:
                            continue

                        # CRITICAL: Re-check state after refetch (race condition protection)
                        if rec.delete_state != "soft":
                            logger.debug(f"Skipping recording {rec.id}: state changed to {rec.delete_state}")
                            continue

                        logger.debug(f"Cleaning files for recording {rec.id} (soft_deleted_at={rec.soft_deleted_at})")

                        # Cleanup files (has internal state check)
                        freed_bytes = await recording_repo.cleanup_recording_files(rec)
                        if freed_bytes > 0:
                            await tx_session.commit()
                            cleaned_count += 1
                            logger.info(f"Cleaned files for recording {rec.id}, freed {freed_bytes} bytes")
                        else:
                            logger.debug(f"No files cleaned for recording {rec.id}")

                except Exception as e:
                    error_msg = f"Failed to cleanup files for recording {recording.id}: {e}"
                    logger.error(error_msg)
                    errors.append(error_msg)

            return cleaned_count, errors

        # Execute async function
        # Use asyncio.run() for proper event loop isolation
        cleaned_count, errors = asyncio.run(cleanup())

        if errors:
            logger.warning(f"Files cleanup completed with {len(errors)} errors")

        logger.info(f"Files cleanup completed: {cleaned_count} recordings cleaned")

        return {
            "status": "success" if not errors else "partial_success",
            "files_cleaned": cleaned_count,
            "errors_count": len(errors),
            "errors": errors[:10] if errors else [],
            "message": f"Cleaned files for {cleaned_count} recordings",
        }

    except Exception as e:
        logger.error("Failed to cleanup recording files: {}", str(e), exc_info=True)
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
                query = select(RecordingModel).where(
                    RecordingModel.hard_delete_at.isnot(None),
                    RecordingModel.hard_delete_at < datetime.now(timezone.utc),
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
        logger.error("Failed to hard delete recordings: {}", str(e), exc_info=True)
        return {"status": "error", "error": str(e)}
