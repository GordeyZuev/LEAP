"""Unit tests for per-credential external rate limiting."""

from unittest.mock import AsyncMock

import pytest

from api.helpers.external_retry import (
    acquire_external_slot,
    parse_retry_after,
    rate_limit_countdown,
    rate_limit_key,
)
from api.shared.exceptions import ExternalRateLimitError


class FakeRedis:
    def __init__(self):
        self.counts: dict[str, int] = {}
        self.expires: dict[str, int] = {}

    async def incr(self, key: str) -> int:
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]

    async def expire(self, key: str, seconds: int) -> None:
        self.expires[key] = seconds

    async def ttl(self, key: str) -> int:
        return self.expires.get(key, -1)

    async def pttl(self, key: str) -> int:
        ttl = self.expires.get(key, -1)
        return ttl * 1000 if ttl >= 0 else -1

    async def aclose(self) -> None:
        return None

    def reset_counts(self) -> None:
        self.counts.clear()
        self.expires.clear()


@pytest.mark.unit
class TestRateLimitHelpers:
    def test_key_is_platform_and_credential(self):
        assert rate_limit_key("mts_link", 42) == "ext-rl:mts_link:42"
        assert rate_limit_key("vk_video", 17) == "ext-rl:vk_video:17"
        assert rate_limit_key("deepseek", "app") == "ext-rl:deepseek:app"

    def test_parse_retry_after_seconds(self):
        assert parse_retry_after("2") == 2.0
        assert parse_retry_after(" 1.5 ") == 1.5
        assert parse_retry_after("Wed, 21 Oct 2015 07:28:00 GMT") is None
        assert parse_retry_after(None) is None

    def test_countdown_honors_retry_after_floor(self, mocker):
        mocker.patch("api.helpers.external_retry.random.uniform", return_value=0.3)
        delay = rate_limit_countdown(0, retry_after=2.0)
        assert delay == pytest.approx(2.3)

    def test_countdown_full_jitter_stays_within_cap(self, mocker):
        mocker.patch("api.helpers.external_retry.random.uniform", side_effect=lambda *args: args[1])
        assert rate_limit_countdown(0) == 2.0
        assert rate_limit_countdown(3) == 16.0
        assert rate_limit_countdown(10) == 30.0


@pytest.mark.unit
class TestAcquireExternalSlot:
    @pytest.mark.asyncio
    async def test_same_credential_waits_when_over_rps(self, mocker):
        client = FakeRedis()
        mocker.patch("api.helpers.external_retry.redis.from_url", return_value=client)

        async def expire_window(_seconds: float) -> None:
            client.reset_counts()

        sleep = mocker.patch("api.helpers.external_retry.asyncio.sleep", side_effect=expire_window)
        await acquire_external_slot("mts_link", 42, requests_per_second=1)
        await acquire_external_slot("mts_link", 42, requests_per_second=1)
        sleep.assert_awaited()

    @pytest.mark.asyncio
    async def test_different_credentials_are_independent(self, mocker):
        client = FakeRedis()
        mocker.patch("api.helpers.external_retry.redis.from_url", return_value=client)
        sleep = mocker.patch("api.helpers.external_retry.asyncio.sleep", new_callable=AsyncMock)
        await acquire_external_slot("mts_link", 42, requests_per_second=1)
        await acquire_external_slot("mts_link", 99, requests_per_second=1)
        sleep.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_redis_error_fails_open(self, mocker):
        mocker.patch("api.helpers.external_retry.redis.from_url", side_effect=ConnectionError("down"))
        await acquire_external_slot("mts_link", 42, requests_per_second=2)

    @pytest.mark.asyncio
    async def test_exhausted_window_raises(self, mocker):
        client = FakeRedis()
        mocker.patch("api.helpers.external_retry.redis.from_url", return_value=client)
        mocker.patch("api.helpers.external_retry.asyncio.sleep", new_callable=AsyncMock)
        await acquire_external_slot("mts_link", 42, requests_per_second=1)
        with pytest.raises(ExternalRateLimitError) as exc:
            await acquire_external_slot("mts_link", 42, requests_per_second=1)
        assert exc.value.platform == "mts_link"
        assert exc.value.credential_id == 42
