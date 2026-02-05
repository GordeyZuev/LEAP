"""Error schemas"""

from pydantic import BaseModel

from .config import BASE_MODEL_CONFIG


class ErrorDetail(BaseModel):
    """Error details."""

    model_config = BASE_MODEL_CONFIG

    message: str
    field: str | None = None
    code: str | None = None


class ErrorResponse(BaseModel):
    """Standard error response."""

    model_config = BASE_MODEL_CONFIG

    error: str
    detail: str | list[ErrorDetail] | None = None


class ValidationErrorResponse(BaseModel):
    """Response with validation errors."""

    model_config = BASE_MODEL_CONFIG

    error: str = "Validation error"
    detail: list[ErrorDetail]


class HTTPError(BaseModel):
    """HTTP error response (for FastAPI docs)."""

    model_config = BASE_MODEL_CONFIG

    detail: str
