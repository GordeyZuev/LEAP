"""Request logging middleware"""

import time

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from logger import get_logger

logger = get_logger()


class LoggingMiddleware(BaseHTTPMiddleware):
    """Middleware for logging HTTP requests."""

    async def dispatch(self, request: Request, call_next):
        """Processing of request with logging."""
        start_time = time.time()

        # Log request
        logger.debug(
            f"Request: {request.method} {request.url.path} | "
            f"client={request.client.host if request.client else 'unknown'}"
        )

        # Execute request
        response = await call_next(request)

        # Log response
        process_time = time.time() - start_time
        logger.debug(
            f"Response: {request.method} {request.url.path} | status={response.status_code} | time={process_time:.3f}s"
        )

        return response
