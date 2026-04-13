"""Rate limiting middleware"""

import time
from collections import defaultdict
from collections.abc import Callable

from fastapi import Request, Response, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from config.settings import get_settings
from logger import get_logger

logger = get_logger()
settings = get_settings()


class RateLimitMiddleware(BaseHTTPMiddleware):
    """In-memory rate limiting middleware"""

    def __init__(self, app):
        super().__init__(app)
        self.minute_requests = defaultdict(list)
        self.hour_requests = defaultdict(list)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if not settings.security.rate_limit_enabled:
            return await call_next(request)

        if request.url.path == "/health":
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        current_time = time.time()
        minute_ago = current_time - 60
        hour_ago = current_time - 3600

        self.minute_requests[client_ip] = [t for t in self.minute_requests[client_ip] if t > minute_ago]
        self.hour_requests[client_ip] = [t for t in self.hour_requests[client_ip] if t > hour_ago]

        minute_count = len(self.minute_requests[client_ip])
        hour_count = len(self.hour_requests[client_ip])

        per_minute = settings.security.rate_limit_per_minute
        per_hour = settings.security.rate_limit_per_hour

        if minute_count >= per_minute:
            logger.warning(f"Rate limit exceeded (per minute): ip={client_ip} | requests={minute_count}/{per_minute}")
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={"detail": f"Rate limit exceeded: {per_minute} requests per minute", "retry_after": 60},
                headers={"Retry-After": "60"},
            )

        if hour_count >= per_hour:
            logger.warning(f"Rate limit exceeded (per hour): ip={client_ip} | requests={hour_count}/{per_hour}")
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={"detail": f"Rate limit exceeded: {per_hour} requests per hour", "retry_after": 3600},
                headers={"Retry-After": "3600"},
            )

        self.minute_requests[client_ip].append(current_time)
        self.hour_requests[client_ip].append(current_time)

        response = await call_next(request)
        response.headers["X-RateLimit-Limit-Minute"] = str(per_minute)
        response.headers["X-RateLimit-Remaining-Minute"] = str(max(0, per_minute - minute_count - 1))
        response.headers["X-RateLimit-Limit-Hour"] = str(per_hour)
        response.headers["X-RateLimit-Remaining-Hour"] = str(max(0, per_hour - hour_count - 1))

        return response
