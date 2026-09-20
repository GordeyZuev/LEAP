"""Rate limiting middleware (Redis-backed)."""

import ipaddress
import time
from collections.abc import Callable

from fastapi import Request, Response, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from api.dependencies import get_redis
from config.settings import get_settings
from logger import get_logger

logger = get_logger()
settings = get_settings()

_AUTH_PATHS = (
    "/api/v1/auth/login",
    "/api/v1/auth/register",
    "/api/v1/auth/forgot-password",
    "/api/v1/auth/reset-password",
    "/api/v1/auth/resend-verification",
)


def _peer_is_trusted_proxy(host: str | None) -> bool:
    if not host:
        return False
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return ip.is_private or ip.is_loopback or ip.is_link_local


def client_ip_for_rate_limit(request: Request) -> str:
    """X-Real-IP, else X-Forwarded-For, else TCP peer. Trusted if the flag is set or the peer is private."""
    peer = request.client.host if request.client else None
    trust_proxy = settings.security.trust_x_forwarded_for or _peer_is_trusted_proxy(peer)
    if trust_proxy:
        real_ip = (request.headers.get("x-real-ip") or "").strip()
        if real_ip:
            return real_ip
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",", 1)[0].strip() or "unknown"
    return peer or "unknown"


async def _hit(redis_client, key: str, limit: int, window_seconds: int) -> bool:
    """Increment ``key``; return True if the limit is exceeded."""
    count = await redis_client.incr(key)
    if count == 1:
        await redis_client.expire(key, window_seconds)
    return int(count) > limit


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Redis rate limiting: per-IP global plus a tighter cap on auth routes."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if not settings.security.rate_limit_enabled:
            return await call_next(request)

        path = request.url.path
        if path.startswith("/api/v1/health") or path == "/metrics":
            return await call_next(request)

        client_ip = client_ip_for_rate_limit(request)
        minute_bucket = int(time.time()) // 60
        hour_bucket = int(time.time()) // 3600
        is_auth = path in _AUTH_PATHS

        try:
            redis_client = await get_redis()
            over_minute = await _hit(
                redis_client,
                f"rl:ip:{client_ip}:m:{minute_bucket}",
                settings.security.rate_limit_per_minute,
                60,
            )
            over_hour = await _hit(
                redis_client,
                f"rl:ip:{client_ip}:h:{hour_bucket}",
                settings.security.rate_limit_per_hour,
                3600,
            )
            over_auth = False
            if is_auth:
                over_auth = await _hit(
                    redis_client,
                    f"rl:auth:ip:{client_ip}:m:{minute_bucket}",
                    settings.security.rate_limit_auth_per_minute,
                    60,
                )
        except Exception as exc:
            logger.warning(f"Rate limit Redis error (fail-open): {exc}")
            return await call_next(request)

        if over_auth or (over_minute and not is_auth):
            logger.warning(f"Rate limit exceeded (per minute): ip={client_ip}")
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={"detail": "Rate limit exceeded", "retry_after": 60},
                headers={"Retry-After": "60"},
            )
        if over_hour and not is_auth:
            logger.warning(f"Rate limit exceeded (per hour): ip={client_ip}")
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={"detail": "Rate limit exceeded", "retry_after": 3600},
                headers={"Retry-After": "3600"},
            )

        return await call_next(request)
