"""Custom API exceptions"""

from fastapi import HTTPException, status


class APIException(HTTPException):
    """Base exception for API HTTP errors."""

    def __init__(
        self,
        status_code: int,
        detail: str,
        headers: dict[str, str] | None = None,
    ):
        super().__init__(status_code=status_code, detail=detail, headers=headers)


class NotFoundError(APIException):
    """Resource not found (HTTP 404)."""

    def __init__(self, resource: str, resource_id: int | str):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{resource} with id {resource_id} not found",
        )


class APIValidationError(APIException):
    """Validation error (HTTP 422). Avoids naming clash with Pydantic's ValidationError."""

    def __init__(self, detail: str):
        super().__init__(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=detail,
        )


class ConflictError(APIException):
    """Data conflict (HTTP 409)."""

    def __init__(self, detail: str):
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail=detail,
        )


# Exceptions for Celery tasks (not HTTP-related)
class TaskError(Exception):
    """Base exception for Celery tasks."""


class CredentialError(TaskError):
    """Credential validation failed (token invalid, expired, etc.)."""

    def __init__(self, platform: str, reason: str):
        self.platform = platform
        self.reason = reason
        super().__init__(f"Credential error for {platform}: {reason}")


class ResourceNotFoundError(TaskError):
    """Resource not found (e.g. file for upload)."""

    def __init__(self, resource_type: str, resource_id: int | str):
        self.resource_type = resource_type
        self.resource_id = resource_id
        super().__init__(f"{resource_type} {resource_id} not found")
