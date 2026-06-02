"""Global error handling.

All handlers return a unified error format: {"error": str, "detail": str | list}.
"""

from fastapi import HTTPException, Request, status
from fastapi.exceptions import RequestValidationError, ResponseValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from api.shared.exceptions import APIException
from config.settings import get_settings
from logger import get_logger, short_user_id

logger = get_logger()


def _bound(request: Request):
    """Logger bound to user_id / request_id from request.state."""
    user_id = getattr(request.state, "user_id", None)
    return logger.bind(
        user_id=short_user_id(user_id) if user_id else None,
        request_id=getattr(request.state, "request_id", None),
    )


def _expose_internal_error_detail() -> bool:
    """Match ``APP_DEBUG`` / ``Settings.app.debug`` (not a separate ``DEBUG`` env)."""
    return get_settings().app.debug


# Maps HTTP status codes to human-readable error categories
_STATUS_ERROR_MAP: dict[int, str] = {
    400: "Bad request",
    401: "Unauthorized",
    403: "Forbidden",
    404: "Not found",
    409: "Conflict",
    413: "Payload too large",
}


async def http_exception_handler(_request: Request, exc: HTTPException) -> JSONResponse:
    """HTTPException handler with unified error format."""
    error_category = _STATUS_ERROR_MAP.get(exc.status_code, f"Error {exc.status_code}")
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": error_category,
            "detail": exc.detail,
        },
        headers=exc.headers,
    )


async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Global exception handler."""
    try:
        exc_str = str(exc)
    except Exception:
        exc_str = repr(exc)

    _bound(request).error("Unhandled exception: {}", exc_str, exc_info=exc)

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "Internal server error",
            "detail": exc_str if _expose_internal_error_detail() else "An error occurred",
        },
    )


async def api_exception_handler(_request: Request, exc: APIException) -> JSONResponse:
    """API exception handler."""
    error_category = _STATUS_ERROR_MAP.get(exc.status_code, f"Error {exc.status_code}")
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": error_category,
            "detail": exc.detail,
        },
    )


async def validation_exception_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
    """Validation exception handler."""
    errors = []
    for error in exc.errors():
        error_dict = {
            "type": error.get("type"),
            "loc": error.get("loc"),
            "msg": error.get("msg"),
            "input": error.get("input"),
        }
        if error.get("ctx"):
            error_dict["ctx"] = {k: str(v) for k, v in error["ctx"].items()}
        errors.append(error_dict)

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": "Validation error",
            "detail": errors,
        },
    )


async def response_validation_exception_handler(request: Request, exc: ResponseValidationError) -> JSONResponse:
    """Response validation exception handler."""
    _bound(request).error("Response validation error: {}", exc, exc_info=exc)

    errors = []
    for error in exc.errors():
        error_dict = {
            "type": error.get("type"),
            "loc": error.get("loc"),
            "msg": error.get("msg"),
        }
        if "input" in error:
            error_dict["input_summary"] = (
                f"{type(error['input']).__name__}" if not _expose_internal_error_detail() else error["input"]
            )
        if error.get("ctx"):
            error_dict["ctx"] = {k: str(v) for k, v in error["ctx"].items()}
        errors.append(error_dict)

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "Internal server error",
            "detail": "Response validation failed" if not _expose_internal_error_detail() else errors,
        },
    )


async def sqlalchemy_exception_handler(request: Request, exc: SQLAlchemyError) -> JSONResponse:
    """SQLAlchemy exception handler."""
    _bound(request).error("Database error: {}", exc, exc_info=exc)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "Database error",
            "detail": "An error occurred while accessing the database",
        },
    )
