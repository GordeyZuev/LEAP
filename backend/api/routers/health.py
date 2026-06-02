"""Health check endpoints.

* ``GET /api/v1/health/live``  — process is alive. No external calls. Docker probe.
* ``GET /api/v1/health/ready`` — DB, Redis and storage backend are reachable.
  Returns ``503`` when any dependency fails so a load balancer routes around it.
"""

from __future__ import annotations

import asyncio
import time

from fastapi import APIRouter, Response
from sqlalchemy import text

from api.dependencies import get_async_session_maker, get_redis
from api.schemas.common.health import (
    HealthCheckResult,
    LivenessResponse,
    ReadinessResponse,
)
from file_storage import get_storage_backend
from logger import get_logger

logger = get_logger(__name__)

router = APIRouter(tags=["Health"])

# S3 head_bucket = TCP + TLS + HEAD; cache so readiness scrapes don't hammer the bucket.
_STORAGE_CHECK_TTL_SECONDS = 60.0
_storage_cache_checked_at = 0.0
_storage_cache_ok = False
_storage_cache_detail = "not checked yet"


async def _check_db() -> HealthCheckResult:
    session_maker = get_async_session_maker()
    try:
        async with session_maker() as session:
            await session.execute(text("SELECT 1"))
        return HealthCheckResult(status="ok")
    except Exception as exc:
        logger.warning("Health check: DB unreachable: {}", exc)
        return HealthCheckResult(status="fail", detail=type(exc).__name__)


async def _check_redis() -> HealthCheckResult:
    try:
        client = await get_redis()
        pong = await client.ping()  # type: ignore[misc]
        if not pong:
            return HealthCheckResult(status="fail", detail="PING returned falsy")
        return HealthCheckResult(status="ok")
    except Exception as exc:
        logger.warning("Health check: Redis unreachable: {}", exc)
        return HealthCheckResult(status="fail", detail=type(exc).__name__)


async def _check_storage() -> HealthCheckResult:
    global _storage_cache_checked_at, _storage_cache_ok, _storage_cache_detail

    now = time.monotonic()
    if now - _storage_cache_checked_at < _STORAGE_CHECK_TTL_SECONDS:
        if _storage_cache_ok:
            return HealthCheckResult(status="ok", detail="cached")
        return HealthCheckResult(status="fail", detail=_storage_cache_detail)

    try:
        await get_storage_backend().health_check()
        _storage_cache_checked_at, _storage_cache_ok, _storage_cache_detail = now, True, "ok"
        return HealthCheckResult(status="ok")
    except Exception as exc:
        detail = type(exc).__name__
        logger.warning("Health check: storage unreachable: {}", exc)
        _storage_cache_checked_at, _storage_cache_ok, _storage_cache_detail = now, False, detail
        return HealthCheckResult(status="fail", detail=detail)


@router.get("/api/v1/health/live", response_model=LivenessResponse)
async def liveness() -> LivenessResponse:
    return LivenessResponse(status="ok")


@router.get(
    "/api/v1/health/ready",
    response_model=ReadinessResponse,
    responses={503: {"model": ReadinessResponse}},
)
async def readiness(response: Response) -> ReadinessResponse:
    db_result, redis_result, storage_result = await asyncio.gather(
        _check_db(),
        _check_redis(),
        _check_storage(),
    )
    checks = {"db": db_result, "redis": redis_result, "storage": storage_result}
    ready = all(c.status == "ok" for c in checks.values())
    if not ready:
        response.status_code = 503
    return ReadinessResponse(ready=ready, checks=checks)
