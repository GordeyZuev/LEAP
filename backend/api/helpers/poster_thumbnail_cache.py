"""Short-lived, tenant-scoped lookup cache for configured recording covers."""

import asyncio
import hashlib
from collections.abc import Awaitable, Callable
from pathlib import Path

from redis.exceptions import RedisError

from api.dependencies import get_redis
from logger import get_logger

logger = get_logger(__name__)

_PREFIX = "leap:poster-thumbnail:v1"
_LOOKUP_TTL_SECONDS = 300
_MISSING = "-"


def _generation_key(user_slug: int) -> str:
    return f"{_PREFIX}:{user_slug}:generation"


def _lookup_key(user_slug: int, generation: str, name: str) -> str:
    normalized = Path(name).name
    name_hash = hashlib.sha256(normalized.encode()).hexdigest()
    return f"{_PREFIX}:{user_slug}:{generation}:{name_hash}"


async def resolve_poster_thumbnails(
    user_slug: int,
    names: list[str],
    resolve: Callable[[str], Awaitable[str | None]],
) -> tuple[dict[str, str | None], str | None]:
    """Resolve missing names in S3; reuse recent results across API workers."""
    if not names:
        return {}, None

    client = None
    generation: str | None = None
    cached: list[str | None] = [None] * len(names)
    try:
        client = await get_redis()
        generation = await client.get(_generation_key(user_slug)) or "0"
        cached = await client.mget([_lookup_key(user_slug, generation, name) for name in names])
    except (RedisError, RuntimeError) as exc:
        logger.debug("Poster thumbnail cache read failed: {}", type(exc).__name__)
        client = None
        generation = None

    missing_indices = [i for i, value in enumerate(cached) if value is None]
    resolved = await asyncio.gather(*(resolve(names[i]) for i in missing_indices))
    results = {name: (None if cached[i] == _MISSING else cached[i]) for i, name in enumerate(names)}
    for i, value in zip(missing_indices, resolved, strict=True):
        results[names[i]] = value

    if client is not None and generation is not None and missing_indices:
        try:
            async with client.pipeline(transaction=False) as pipe:
                for i, value in zip(missing_indices, resolved, strict=True):
                    pipe.setex(
                        _lookup_key(user_slug, generation, names[i]),
                        _LOOKUP_TTL_SECONDS,
                        value if value is not None else _MISSING,
                    )
                await pipe.execute()
        except (RedisError, RuntimeError) as exc:
            logger.debug("Poster thumbnail cache write failed: {}", type(exc).__name__)

    return results, generation


async def invalidate_poster_thumbnails(user_slug: int) -> None:
    """Bump the generation after a cover write/delete, including across workers."""
    try:
        client = await get_redis()
        await client.incr(_generation_key(user_slug))
    except (RedisError, RuntimeError) as exc:
        logger.debug("Poster thumbnail cache invalidation failed: {}", type(exc).__name__)
