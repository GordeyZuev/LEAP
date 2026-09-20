"""Service for validating user access to Celery tasks.

Ensures task isolation between users using Redis owner binding and Celery metadata.
"""

from celery.result import AsyncResult
from fastapi import HTTPException, status

from api.celery_app import celery_app
from api.tasks.base import lookup_task_owner
from logger import get_logger

logger = get_logger()


class TaskAccessService:
    """
    Validates user access to Celery tasks (status, cancel).
    Prefers Redis task_owner binding (set at enqueue); falls back to result meta.
    """

    @staticmethod
    def _extract_user_id_from_task(task: AsyncResult) -> str | None:
        """Extract user_id from task. Checks: task.info, task.result."""
        if task.info and isinstance(task.info, dict):
            user_id = task.info.get("user_id")
            if user_id:
                return str(user_id)

        if task.state == "SUCCESS" and task.result and isinstance(task.result, dict):
            user_id = task.result.get("user_id")
            if user_id:
                return str(user_id)

        return None

    @staticmethod
    def validate_task_access(task_id: str, user_id: str) -> AsyncResult:
        """
        Validate user access to task.

        Returns:
            AsyncResult

        Raises:
            HTTPException: If access denied or task not found
        """
        task = AsyncResult(task_id, app=celery_app)

        redis_owner = lookup_task_owner(task_id)
        if redis_owner is not None:
            if redis_owner != user_id:
                logger.warning(f"User {user_id} attempted to access task {task_id} owned by {redis_owner}")
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied. This task belongs to another user.",
                )
            return task

        if task.state in ("PENDING", "STARTED", "RETRY"):
            logger.warning(f"Cannot verify ownership of task {task_id} (state={task.state}) for user {user_id}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot verify task ownership. Access denied.",
            )

        task_user_id = TaskAccessService._extract_user_id_from_task(task)

        if task_user_id is None:
            logger.warning(
                f"Cannot extract user_id from task {task_id} (state={task.state}). Access denied for user {user_id}."
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot verify task ownership. Access denied.",
            )

        if task_user_id != user_id:
            logger.warning(f"User {user_id} attempted to access task {task_id} owned by user {task_user_id}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied. This task belongs to another user.",
            )

        logger.debug(f"User {user_id} validated access to task {task_id}")
        return task
