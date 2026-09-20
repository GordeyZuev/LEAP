"""Configured cover lookup reuses S3 checks and invalidates across workers."""

from unittest.mock import AsyncMock, patch

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from api.helpers.poster_thumbnail_cache import invalidate_poster_thumbnails, resolve_poster_thumbnails


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.pending: list[tuple[str, str]] = []

    async def get(self, key: str) -> str | None:
        return self.values.get(key)

    async def mget(self, keys: list[str]) -> list[str | None]:
        return [self.values.get(key) for key in keys]

    async def incr(self, key: str) -> int:
        value = int(self.values.get(key, "0")) + 1
        self.values[key] = str(value)
        return value

    def pipeline(self, *, transaction: bool):
        assert transaction is False
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    def setex(self, key: str, _ttl: int, value: str) -> None:
        self.pending.append((key, value))

    async def execute(self) -> None:
        self.values.update(self.pending)
        self.pending.clear()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cached_thumbnail_resolution_and_write_invalidation() -> None:
    redis = FakeRedis()
    present = {"cover.png"}
    resolve = AsyncMock(side_effect=lambda name: f"users/000042/thumbnails/{name}" if name in present else None)

    with patch("api.helpers.poster_thumbnail_cache.get_redis", new=AsyncMock(return_value=redis)):
        first, generation = await resolve_poster_thumbnails(42, ["cover.png", "missing.png"], resolve)
        second, same_generation = await resolve_poster_thumbnails(42, ["cover.png", "missing.png"], resolve)
        present.add("missing.png")
        await invalidate_poster_thumbnails(42)
        third, new_generation = await resolve_poster_thumbnails(42, ["cover.png", "missing.png"], resolve)

    assert (
        first
        == second
        == {
            "cover.png": "users/000042/thumbnails/cover.png",
            "missing.png": None,
        }
    )
    assert third["missing.png"] == "users/000042/thumbnails/missing.png"
    assert (generation, same_generation, new_generation) == ("0", "0", "1")
    assert resolve.await_count == 4


@pytest.mark.unit
@pytest.mark.asyncio
async def test_redis_failure_keeps_s3_lookup_available() -> None:
    redis = AsyncMock()
    redis.get.side_effect = RedisConnectionError("unavailable")
    resolve = AsyncMock(return_value="users/000042/thumbnails/cover.png")

    with patch("api.helpers.poster_thumbnail_cache.get_redis", new=AsyncMock(return_value=redis)):
        result, generation = await resolve_poster_thumbnails(42, ["cover.png"], resolve)

    assert result == {"cover.png": "users/000042/thumbnails/cover.png"}
    assert generation is None
    resolve.assert_awaited_once_with("cover.png")
