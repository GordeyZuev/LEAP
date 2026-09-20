"""Unit tests for share link observability helpers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from api.services.share_observability import (
    ShareObservabilityService,
    _channel_id_from_from_param,
    enqueue_share_event_batch,
    fill_daily_series,
    visitor_key_for_request,
)


class _FakeClient:
    host = "127.0.0.1"


class _FakeRequest:
    def __init__(self, ip: str = "203.0.113.1", user_agent: str = "TestAgent/1.0") -> None:
        self.headers = {"user-agent": user_agent, "x-forwarded-for": ip}
        self.client = _FakeClient()


def test_visitor_key_is_stable_for_same_day() -> None:
    request = _FakeRequest()
    first = visitor_key_for_request(42, request)
    second = visitor_key_for_request(42, request)
    assert first == second
    assert len(first) == 64


def test_visitor_key_differs_by_recording_id() -> None:
    request = _FakeRequest()
    assert visitor_key_for_request(1, request) != visitor_key_for_request(2, request)


def test_visitor_key_ignores_forwarded_ip_from_untrusted_peer(mocker) -> None:
    mocker.patch("api.middleware.rate_limit.settings.security.trust_x_forwarded_for", False)
    first = _FakeRequest(ip="192.0.2.1")
    second = _FakeRequest(ip="192.0.2.2")
    first.client = MagicMock(host="8.8.8.8")
    second.client = MagicMock(host="8.8.8.8")

    assert visitor_key_for_request("recording:1", first) == visitor_key_for_request("recording:1", second)


def test_fill_daily_series_zero_fills_gaps() -> None:
    today = datetime.now(UTC).date()
    yesterday = today - timedelta(days=1)
    aggregates = [(datetime.combine(yesterday, datetime.min.time(), tzinfo=UTC), 2, 1)]

    series = fill_daily_series(aggregates, days=2)

    assert len(series) == 2
    assert series[0] == (yesterday, 2, 1)
    assert series[1][0] == today
    assert series[1][1:] == (0, 0)


@pytest.mark.asyncio
async def test_share_event_publish_fails_fast_before_db_fallback(mocker) -> None:
    task = mocker.patch("api.tasks.share_events.persist_share_event_batch")
    payload = {"access_events": []}

    await enqueue_share_event_batch(payload)

    assert "queued_at" in payload
    task.apply_async.assert_called_once_with(kwargs={"payload": payload}, retry=False)


@pytest.mark.asyncio
async def test_from_param_rejects_unrelated_channel(mocker) -> None:
    channel = MagicMock(id=7, user_id="another_owner", share_enabled=True)
    mocker.patch("api.repositories.channel_repo.ChannelRepository.get_by_slug", new=AsyncMock(return_value=channel))
    request = MagicMock()
    request.query_params = {"from": "26"}
    session = AsyncMock()

    result = await _channel_id_from_from_param(session, request, owner_user_id="user_123", playlist_id=3)

    assert result is None
    session.scalar.assert_not_awaited()


@pytest.mark.asyncio
async def test_from_param_requires_actual_playlist_membership(mocker) -> None:
    channel = MagicMock(id=7, user_id="user_123", share_enabled=True)
    mocker.patch("api.repositories.channel_repo.ChannelRepository.get_by_slug", new=AsyncMock(return_value=channel))
    request = MagicMock()
    request.query_params = {"from": "26"}
    session = AsyncMock()
    session.scalar = AsyncMock(side_effect=[None, 42])

    assert await _channel_id_from_from_param(session, request, owner_user_id="user_123", playlist_id=3) is None
    assert await _channel_id_from_from_param(session, request, owner_user_id="user_123", playlist_id=3) == 7


@pytest.mark.asyncio
async def test_from_param_requires_actual_recording_membership(client, mocker) -> None:
    channel = MagicMock(id=7, user_id="user_123", share_enabled=True)
    mocker.patch("api.repositories.channel_repo.ChannelRepository.get_by_slug", new=AsyncMock(return_value=channel))
    request = MagicMock()
    request.query_params = {"from": "course-26"}
    session = AsyncMock()
    session.scalar = AsyncMock(side_effect=[None, None])

    result = await _channel_id_from_from_param(session, request, owner_user_id="user_123", recording_id=8)

    assert result is None
    assert session.scalar.await_count == 2


@pytest.mark.asyncio
async def test_record_page_view_skips_without_owner() -> None:
    recording = MagicMock()
    recording.id = 1
    recording.user_id = None

    service = ShareObservabilityService()
    counted = await service.record_page_view(recording, _FakeRequest())
    assert counted is False


@pytest.mark.asyncio
async def test_sync_fallback_duplicate_does_not_increment_counter(mocker) -> None:
    session = AsyncMock()
    session.scalar = AsyncMock(return_value=None)
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    mocker.patch("api.services.share_observability.get_async_session_maker", return_value=lambda: session)
    mocker.patch("api.services.share_observability._channel_id_from_from_param", new=AsyncMock(return_value=None))
    recording = MagicMock(id=12, user_id="owner")

    persisted = await ShareObservabilityService()._persist_event(
        recording, event_type="page_view", visitor_key="visitor", increment_views=True, event_id="duplicate"
    )

    assert persisted is True
    session.scalar.assert_awaited_once()
    session.execute.assert_not_awaited()
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_catalog_analytics_includes_downloads_by_type(mocker) -> None:
    from datetime import date

    from api.services.share_observability import build_catalog_analytics

    repo = MagicMock()
    repo.daily_aggregates_for_recordings = AsyncMock(return_value=[])
    repo.daily_opens = AsyncMock(return_value=[])
    repo.totals_for_recordings = AsyncMock(return_value=(1, 3))
    repo.total_opens = AsyncMock(return_value=0)
    repo.downloads_by_type_for_recordings = AsyncMock(return_value={"video": 3})
    mocker.patch("api.services.share_observability.ShareEventRepository", return_value=repo)
    engagement = MagicMock()
    engagement.build_summary = AsyncMock(return_value=None)
    mocker.patch("api.services.share_engagement.ShareEngagementService", return_value=engagement)

    start = date(2026, 9, 1)
    end = date(2026, 9, 2)
    result = await build_catalog_analytics(
        MagicMock(),
        recording_ids=[1, 2],
        from_date=start,
        to_date=end,
        from_dt=datetime(2026, 9, 1, tzinfo=UTC),
        to_dt=datetime(2026, 9, 2, 23, 59, tzinfo=UTC),
        owner_user_id="u1",
        channel_id=9,
    )
    assert result.downloads_by_type == {"video": 3}
    repo.downloads_by_type_for_recordings.assert_awaited_once()
