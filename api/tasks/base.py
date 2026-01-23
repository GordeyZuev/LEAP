"""Base task classes with built-in multi-tenancy support.

Provides common functionality for all Celery tasks:
- User ID tracking in task metadata
- Standardized result format
- Logging hooks
"""

import asyncio
from collections.abc import Awaitable
from typing import TypeVar

from celery import Task

from logger import get_logger

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
        # asyncio.run() handles everything:
        # 1. Creates new event loop
        # 2. Runs coroutine to completion
        # 3. Closes event loop and cleans up resources
        # This is perfect for Celery tasks where each task should be isolated
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
            "user_id": user_id,  # Critical for multi-tenancy
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
            "user_id": user_id,  # Critical for multi-tenancy
            "status": status,
            **data,
        }

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Log task failure with user_id."""
        user_id = kwargs.get("user_id", "unknown")
        logger.error(f"Task {task_id} for user {user_id} failed: {exc!r}")

    def on_retry(self, exc, task_id, args, kwargs, einfo):
        """Log task retry with user_id."""
        user_id = kwargs.get("user_id", "unknown")
        logger.warning(f"Task {task_id} for user {user_id} retrying: {exc}")

    def on_success(self, retval, task_id, args, kwargs):
        """Log task success with user_id."""
        user_id = args[1] if len(args) > 1 else kwargs.get("user_id", "unknown")
        logger.info(f"Task {task_id} for user {user_id} completed successfully")


class ProcessingTask(BaseTask):
    """Base class for processing tasks (download, trim, transcribe, etc.)."""

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Log processing task failure."""
        recording_id = args[0] if len(args) > 0 else kwargs.get("recording_id", "unknown")
        user_id = args[1] if len(args) > 1 else kwargs.get("user_id", "unknown")
        logger.error(f"Processing task {task_id} failed: user={user_id}, recording={recording_id}, error={exc!r}")


class UploadTask(BaseTask):
    """Base class for upload tasks."""

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Log upload task failure."""
        # Args: (recording_id, user_id, platform, ...)
        user_id = args[1] if len(args) > 1 else kwargs.get("user_id", "unknown")
        platform = args[2] if len(args) > 2 else kwargs.get("platform", "unknown")
        logger.error("Upload task {} failed: user={}, platform={}, error={}", task_id, user_id, platform, str(exc))


class SyncTask(BaseTask):
    """Base class for synchronization tasks."""

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Log sync task failure."""
        # Args: (source_id or source_ids, user_id, ...)
        user_id = args[1] if len(args) > 1 else kwargs.get("user_id", "unknown")
        source_ids = args[0] if len(args) > 0 else kwargs.get("source_ids", kwargs.get("source_id", "unknown"))
        logger.error(f"Sync task {task_id} failed: user={user_id}, sources={source_ids}, error={exc!r}")


class TemplateTask(BaseTask):
    """Base class for template-related tasks."""

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Log template task failure."""
        # Args: (template_id, user_id, ...)
        template_id = args[0] if len(args) > 0 else kwargs.get("template_id", "unknown")
        user_id = args[1] if len(args) > 1 else kwargs.get("user_id", "unknown")
        logger.error(f"Template task {task_id} failed: user={user_id}, template={template_id}, error={exc!r}")


class AutomationTask(BaseTask):
    """Base class for automation tasks."""

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Log automation task failure."""
        # Args: (job_id, user_id, ...)
        job_id = args[0] if len(args) > 0 else kwargs.get("job_id", "unknown")
        user_id = args[1] if len(args) > 1 else kwargs.get("user_id", "unknown")
        logger.error(f"Automation task {task_id} failed: user={user_id}, job={job_id}, error={exc!r}")
