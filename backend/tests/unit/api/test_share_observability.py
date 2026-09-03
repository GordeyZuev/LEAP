"""Unit tests for share link observability helpers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest

from api.services.share_observability import fill_daily_series, visitor_key_for_request


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
async def test_record_page_view_skips_without_owner() -> None:
    from api.services.share_observability import ShareObservabilityService

    recording = MagicMock()
    recording.id = 1
    recording.user_id = None

    service = ShareObservabilityService()
    counted = await service.record_page_view(recording, _FakeRequest())
    assert counted is False
