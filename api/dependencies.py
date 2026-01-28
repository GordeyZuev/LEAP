"""FastAPI dependency injection"""

import os
import sys
from collections.abc import AsyncGenerator
from functools import lru_cache

import redis.asyncio as redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from config.settings import get_settings

settings = get_settings()


def _is_celery_worker() -> bool:
    """Check if running in Celery worker context."""
    # Check environment variable
    if os.getenv("CELERY_WORKER") == "true":
        return True

    # Check if celery worker command is in sys.argv
    if len(sys.argv) > 0:
        argv_str = " ".join(sys.argv)
        if "celery" in argv_str and "worker" in argv_str:
            return True

    return False


def get_async_engine():
    """Получение async engine для SQLAlchemy.

    Uses NullPool in Celery workers to avoid event loop issues with asyncpg.
    In Celery workers with threads pool, each task may run in a different thread
    with a different event loop, so we can't reuse connection pools.

    Note: NO @lru_cache for Celery workers - engine must be created fresh
    for each asyncio.run() call to avoid event loop issues.
    """
    if _is_celery_worker():
        # NullPool: no connection pooling, create new connection for each request
        # No caching - fresh engine for each asyncio.run() call
        return create_async_engine(settings.database.url, echo=False, poolclass=NullPool)
    # Normal pooling for FastAPI (web server) - cached
    return _get_cached_engine()


@lru_cache
def _get_cached_engine():
    """Cached engine for FastAPI web server only."""
    return create_async_engine(settings.database.url, echo=False)


def get_async_session_maker():
    """Получение session maker для async sessions."""
    engine = get_async_engine()
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Получение async database session."""
    async_session = get_async_session_maker()
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()


_redis_client = None


async def get_redis() -> redis.Redis:
    """Получение async Redis client."""
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(
            settings.celery.broker_url,
            encoding="utf-8",
            decode_responses=True,
        )
    return _redis_client
