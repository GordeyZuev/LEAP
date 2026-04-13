"""Base task classes with built-in multi-tenancy support.

Provides common functionality for all Celery tasks:
- User ID tracking in task metadata
- Standardized result format
- Logging hooks with contextualize() for structured output
"""

import asyncio
from collections.abc import Awaitable
from typing import TypeVar

from celery import Task

from logger import format_details, get_logger, short_task_id, short_user_id

logger = get_logger()

T = TypeVar("T")


class BaseTask(Task):
    """
    Base class for all application tasks.

    Provides common functionality:
    - Progress tracking with user_id for access control
    - Standardized result format
    - Logging hooks
    - Event loop management for async tasks

    Usage:
        @celery_app.task(bind=True, base=ProcessingTask)
        def my_task(self, recording_id: int, user_id: str):
            self.update_progress(user_id, 50, "Processing...")
            result = self.run_async(async_function(recording_id))
            return self.build_result(user_id, result=result)
    """

    def run_async(self, coro: Awaitable[T]) -> T:
        """
        Run async coroutine in Celery worker with proper event loop management.

        Uses asyncio.run() which creates a completely fresh event loop for each task.
        This is the recommended approach for running async code in sync context.

        Benefits:
        - Creates new event loop + sets it as current + closes it automatically
        - Cleans up async generators and other resources
        - Safe for asyncpg connection pools (each run gets fresh loop)
        - No issues with "event loop already running" or "future attached to different loop"

        Args:
            coro: Async coroutine to run

        Returns:
            Result of coroutine execution
        """
        return asyncio.run(coro)

    def update_progress(
        self,
        user_id: str,
        progress: int,
        status: str,
        step: str | None = None,
        **extra_meta,
    ) -> None:
        """
        Update task progress with user_id for multi-tenancy validation.

        Args:
            user_id: ID of user who owns this task
            progress: Progress percentage (0-100)
            status: Human-readable status message
            step: Optional step name (download, trim, upload, etc.)
            **extra_meta: Additional metadata fields
        """
        meta = {
            "user_id": user_id,
            "progress": progress,
            "status": status,
            **extra_meta,
        }

        if step:
            meta["step"] = step

        self.update_state(state="PROCESSING", meta=meta)

    def build_result(self, user_id: str, status: str = "completed", **data) -> dict:
        """
        Build standardized task result with user_id.

        Args:
            user_id: ID of user who owns this task
            status: Task status (completed, failed, etc.)
            **data: Additional result data

        Returns:
            Dictionary with task result
        """
        return {
            "task_id": self.request.id,
            "user_id": user_id,
            "status": status,
            **data,
        }

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Log task failure with user_id."""
        user_id = kwargs.get("user_id", "unknown")
        with logger.contextualize(task_id=short_task_id(task_id), user_id=short_user_id(user_id)):
            logger.error(f"Task failed: {exc!r}")

    def on_retry(self, exc, task_id, args, kwargs, einfo):
        """Log task retry with user_id."""
        user_id = kwargs.get("user_id", "unknown")
        with logger.contextualize(task_id=short_task_id(task_id), user_id=short_user_id(user_id)):
            logger.warning(f"Task retrying: {exc}")

    def on_success(self, retval, task_id, args, kwargs):
        """Log task success with user_id."""
        user_id = args[1] if len(args) > 1 else kwargs.get("user_id", "unknown")
        with logger.contextualize(task_id=short_task_id(task_id), user_id=short_user_id(user_id)):
            logger.success("Task completed")


class ProcessingTask(BaseTask):
    """Base class for processing tasks (download, trim, transcribe, etc.)."""

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Handle processing task failure with status rollback."""
        recording_id = args[0] if len(args) > 0 else kwargs.get("recording_id", "unknown")
        user_id = args[1] if len(args) > 1 else kwargs.get("user_id", "unknown")

        with logger.contextualize(
            task_id=short_task_id(task_id),
            recording_id=recording_id,
            user_id=short_user_id(user_id),
        ):
            # Skip failure handling for orchestrator task
            task_name = self.name.split(".")[-1] if self.name else "unknown"
            if task_name == "run_recording":
                logger.error(f"Pipeline orchestration failed: {exc!r}")
                return

            # Determine task type and stage
            from models.recording import ProcessingStageType

            stage_map = {
                "download_recording": ("download", None),
                "trim_video": ("trim", ProcessingStageType.TRIM),
                "transcribe_recording": ("transcribe", ProcessingStageType.TRANSCRIBE),
                "extract_topics": ("topics", ProcessingStageType.EXTRACT_TOPICS),
                "generate_subtitles": ("subtitles", ProcessingStageType.GENERATE_SUBTITLES),
            }

            failed_at_stage, stage_type = stage_map.get(task_name, (None, None))

            if failed_at_stage:
                asyncio.run(self._handle_failure_async(recording_id, user_id, failed_at_stage, stage_type, exc))
                logger.error(f"Processing failed at {failed_at_stage}: {exc!r}")
            else:
                logger.error(f"Processing failed: {exc!r}")

    async def _handle_failure_async(
        self, recording_id: int, user_id: str, failed_at_stage: str, stage_type, exc: Exception
    ):
        """Async failure handling with status rollback and stage updates."""
        from api.dependencies import get_async_session_maker
        from api.helpers import failure_handler
        from api.repositories.recording_repos import RecordingRepository
        from api.services.config_utils import resolve_full_config

        session_maker = get_async_session_maker()

        async with session_maker() as session:
            repo = RecordingRepository(session)
            recording = await repo.get_by_id(recording_id, user_id)

            if not recording:
                logger.warning(f"Recording {recording_id} not found during failure handling")
                return

            error_msg = str(exc)

            if failed_at_stage == "download":
                await failure_handler.handle_download_failure(recording, error_msg)
            elif failed_at_stage == "trim":
                await failure_handler.handle_trim_failure(recording, error_msg)
            elif failed_at_stage in ["transcribe", "topics", "subtitles"]:
                full_config, _ = await resolve_full_config(session, recording_id, user_id, manual_override=None)
                transcription_config = full_config.get("transcription", {})
                allow_errors = transcription_config.get("allow_errors", False)
                await failure_handler.handle_transcribe_failure(recording, stage_type, error_msg, allow_errors)

            await repo.update(recording)
            await session.commit()


class UploadTask(BaseTask):
    """Base class for upload tasks."""

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Handle upload failure: mark output as FAILED, recalculate status."""
        recording_id = args[0] if len(args) > 0 else kwargs.get("recording_id", "unknown")
        user_id = args[1] if len(args) > 1 else kwargs.get("user_id", "unknown")
        platform = args[2] if len(args) > 2 else kwargs.get("platform", "unknown")

        with logger.contextualize(
            task_id=short_task_id(task_id),
            recording_id=recording_id,
            user_id=short_user_id(user_id),
            platform=platform,
        ):
            asyncio.run(self._handle_upload_failure_async(recording_id, user_id, platform, exc))
            logger.error(f"Upload failed: {exc}")

    async def _handle_upload_failure_async(self, recording_id: int, user_id: str, platform: str, exc: Exception):
        """Mark output target as FAILED and recalculate recording status."""
        from api.dependencies import get_async_session_maker
        from api.helpers import failure_handler
        from api.repositories.recording_repos import RecordingRepository

        session_maker = get_async_session_maker()

        async with session_maker() as session:
            repo = RecordingRepository(session)
            recording = await repo.get_by_id(recording_id, user_id)

            if not recording:
                logger.warning(f"Recording {recording_id} not found during upload failure handling")
                return

            error_msg = str(exc)
            await failure_handler.handle_upload_failure(recording, platform, error_msg)

            await repo.update(recording)
            await session.commit()


class SyncTask(BaseTask):
    """Base class for synchronization tasks."""

    def on_success(self, retval, task_id, args, kwargs):
        """Log sync result; warn if task returned status=error (e.g. credential decryption failed)."""
        user_id = args[1] if len(args) > 1 else kwargs.get("user_id", "unknown")
        with logger.contextualize(task_id=short_task_id(task_id), user_id=short_user_id(user_id)):
            if isinstance(retval, dict) and retval.get("status") == "error":
                logger.warning(
                    f"Sync completed with error | {format_details(source=retval.get('source_id'), error=retval.get('error'))}"
                )
            else:
                logger.success("Task completed")

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Log sync task failure."""
        user_id = args[1] if len(args) > 1 else kwargs.get("user_id", "unknown")
        source_ids = args[0] if len(args) > 0 else kwargs.get("source_ids", kwargs.get("source_id", "unknown"))
        with logger.contextualize(task_id=short_task_id(task_id), user_id=short_user_id(user_id)):
            logger.error(f"Sync failed | sources={source_ids} | error={exc!r}")


class TemplateTask(BaseTask):
    """Base class for template-related tasks."""

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Log template task failure."""
        template_id = args[0] if len(args) > 0 else kwargs.get("template_id", "unknown")
        user_id = args[1] if len(args) > 1 else kwargs.get("user_id", "unknown")
        with logger.contextualize(task_id=short_task_id(task_id), user_id=short_user_id(user_id)):
            logger.error(f"Template task failed | template={template_id} | error={exc!r}")


class AutomationTask(BaseTask):
    """Base class for automation tasks."""

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Log automation task failure."""
        job_id = args[0] if len(args) > 0 else kwargs.get("job_id", "unknown")
        user_id = args[1] if len(args) > 1 else kwargs.get("user_id", "unknown")
        with logger.contextualize(task_id=short_task_id(task_id), user_id=short_user_id(user_id)):
            logger.error(f"Automation failed | job={job_id} | error={exc!r}")
