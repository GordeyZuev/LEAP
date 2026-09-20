"""Polite retries and per-credential QPS slots for external provider APIs.

Redis key: ``ext-rl:{platform}:{subject}`` where ``subject`` is ``user_credentials.id``
for OAuth/org tokens (or ``app`` later for file-based AI keys). Fail open if Redis
is down — HTTP 429 retry is the safety net, not a hard pipeline stop.
"""

from __future__ import annotations

import asyncio
import random

import redis.asyncio as redis

from api.shared.exceptions import ExternalRateLimitError
from config.settings import get_settings
from logger import format_details, get_logger

logger = get_logger()

MTS_LINK_REQUESTS_PER_SECOND = 2
VK_VIDEO_REQUESTS_PER_SECOND = 3
RATE_LIMIT_HTTP_RETRIES = 3
_ACQUIRE_MAX_ATTEMPTS = 8
_WINDOW_SECONDS = 1


def rate_limit_key(platform: str, subject: str | int) -> str:
    """Redis key for one provider token (credential id or ``app``)."""
    return f"ext-rl:{platform}:{subject}"


def parse_retry_after(value: str | None) -> float | None:
    """Parse ``Retry-After`` as seconds. HTTP-date values are ignored."""
    if not value:
        return None
    try:
        return max(0.0, float(str(value).strip()))
    except (TypeError, ValueError):
        return None


def rate_limit_countdown(attempt: int, retry_after: float | None = None) -> float:
    """Full-jitter delay in seconds. Honors ``Retry-After`` as a floor when present."""
    if retry_after is not None and retry_after > 0:
        return retry_after + random.uniform(0, 0.3 * retry_after)
    cap = min(30.0, 2.0 * (2 ** max(attempt, 0)))
    return random.uniform(0.0, cap)


def _credential_id(subject: str | int) -> int | None:
    if isinstance(subject, int):
        return subject
    if isinstance(subject, str) and subject.isdigit():
        return int(subject)
    return None


async def acquire_external_slot(
    platform: str,
    subject: str | int,
    *,
    requests_per_second: float,
) -> None:
    """Block until this credential may send another request, or raise if still over QPS.

    Fixed 1-second window: ``INCR`` + ``EXPIRE``. Over the cap, wait remaining TTL
    plus a little jitter and try again.
    """
    if requests_per_second <= 0:
        return
    limit = max(1, int(requests_per_second))
    key = rate_limit_key(platform, subject)
    client: redis.Redis | None = None
    try:
        client = redis.from_url(
            get_settings().celery.broker_url,
            encoding="utf-8",
            decode_responses=True,
        )
        for _ in range(_ACQUIRE_MAX_ATTEMPTS):
            count = int(await client.incr(key))
            if count == 1:
                await client.expire(key, _WINDOW_SECONDS)
            else:
                ttl = int(await client.ttl(key))
                if ttl < 0:
                    await client.expire(key, _WINDOW_SECONDS)
            if count <= limit:
                return
            ttl_ms = int(await client.pttl(key))
            wait = max(ttl_ms, 50) / 1000.0 + random.uniform(0.0, 0.05)
            await asyncio.sleep(wait)
        raise ExternalRateLimitError(platform=platform, credential_id=_credential_id(subject))
    except ExternalRateLimitError:
        raise
    except Exception as exc:
        logger.warning(
            f"External rate limiter fail-open | {format_details(platform=platform, key=key, error=type(exc).__name__)}"
        )
    finally:
        if client is not None:
            await client.aclose()
