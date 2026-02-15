"""Service for validating user access to Celery tasks.

Ensures task isolation between users using Celery metadata.
"""

from celery.result import AsyncResult
from fastapi import HTTPException, status

from api.celery_app import celery_app
from logger import get_logger

logger = get_logger()


class TaskAccessService:
    """
    Validates user access to Celery tasks (status, cancel).
    Uses user_id from task result/metadata.
    """

    @staticmethod
    def _extract_user_id_from_task(task: AsyncResult) -> str | None:
        """
        Extract user_id from task. Checks: task.info, task.result.
        """
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

        # PENDING tasks: allow (task creator verified via API)
        if task.state == "PENDING":
            logger.debug(f"Task {task_id} is PENDING, skipping user_id check")
            return task

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
