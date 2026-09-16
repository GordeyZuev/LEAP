"""MTS Link lecture start_time resolution."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from api.helpers.mts_link_datetime import (
    load_event_session,
    parse_mts_link_datetime,
    resolve_mts_link_start_time,
    session_starts_at_iso,
)
from api.mts_link_api import MtsLinkResponseError


@pytest.mark.unit
class TestParseMtsLinkDatetime:
    def test_naive_is_moscow_not_utc(self):
        parsed = parse_mts_link_datetime("2026-05-05 10:00:00")
        assert parsed is not None
        assert parsed.tzinfo is not None
        assert parsed.astimezone(UTC) == datetime(2026, 5, 5, 7, 0, tzinfo=UTC)

    def test_zulu_and_offset_colon(self):
        zulu = parse_mts_link_datetime("2026-05-05T10:00:00Z")
        assert zulu == datetime(2026, 5, 5, 10, 0, tzinfo=UTC)
        offset = parse_mts_link_datetime("2019-07-29T17:59:41+03:00")
        assert offset is not None
        assert offset.replace(tzinfo=None) == datetime(2019, 7, 29, 17, 59, 41)
        assert offset.utcoffset() is not None
        assert offset.utcoffset().total_seconds() == 10800

    def test_offset_without_colon(self):
        parsed = parse_mts_link_datetime("2018-09-27T19:54:41+0300")
        assert parsed is not None
        assert parsed.utcoffset().total_seconds() == 10800

    def test_missing_or_garbage_is_none(self):
        assert parse_mts_link_datetime(None) is None
        assert parse_mts_link_datetime("not-a-date") is None
        assert parse_mts_link_datetime("") is None


@pytest.mark.unit
class TestResolveMtsLinkStartTime:
    def test_starts_at_wins(self):
        record = {"createAt": "2026-05-05 10:00:00"}
        session = {"startsAt": "2019-07-29T17:59:41+03:00", "utcStartsAt": 1564412381}
        dt, source = resolve_mts_link_start_time(record, session)
        assert source == "startsAt"
        assert dt.year == 2019

    def test_utc_starts_at_when_starts_at_missing(self):
        dt, source = resolve_mts_link_start_time({}, {"utcStartsAt": 1564412381})
        assert source == "utcStartsAt"
        assert dt == datetime.fromtimestamp(1564412381, tz=UTC)

    def test_estimated_then_create_at(self):
        dt, source = resolve_mts_link_start_time(
            {"createAt": "2026-05-05 10:00:00"},
            {"estimatedAt": "2018-09-27T19:54:00+0300"},
        )
        assert source == "estimatedAt"
        assert dt.year == 2018

        dt, source = resolve_mts_link_start_time({"createAt": "2026-05-05 10:00:00"}, {})
        assert source == "createAt"
        assert dt.astimezone(UTC) == datetime(2026, 5, 5, 7, 0, tzinfo=UTC)

    def test_now_only_when_allowed(self):
        dt, source = resolve_mts_link_start_time({}, {}, allow_now=True)
        assert source == "now"
        assert dt.tzinfo is not None

        dt, source = resolve_mts_link_start_time({}, {}, allow_now=False)
        assert source == "skip"
        assert dt is None

    def test_session_starts_at_iso(self):
        session = {"startsAt": "2019-07-29T17:59:41+03:00"}
        iso = session_starts_at_iso(session)
        assert iso is not None
        assert "2019-07-29" in iso

        utc_iso = session_starts_at_iso({"utcStartsAt": 1564412381})
        assert utc_iso is not None
        assert utc_iso.startswith("2019-07-29")

        assert session_starts_at_iso(None) is None
        assert session_starts_at_iso({}) is None


@pytest.mark.unit
class TestLoadEventSession:
    @pytest.mark.asyncio
    async def test_one_get_for_shared_session(self):
        api = AsyncMock()
        api.get_event_session.return_value = {"id": 900, "startsAt": "2019-07-29T17:59:41+03:00"}
        cache: dict = {}
        first = await load_event_session(api, 900, cache)
        second = await load_event_session(api, 900, cache)
        assert first is second
        assert api.get_event_session.await_count == 1

    @pytest.mark.asyncio
    async def test_error_caches_none(self):
        api = AsyncMock()
        api.get_event_session.side_effect = MtsLinkResponseError(404, "missing")
        cache: dict = {}
        assert await load_event_session(api, 900, cache) is None
        assert await load_event_session(api, 900, cache) is None
        assert api.get_event_session.await_count == 1

    @pytest.mark.asyncio
    async def test_unwraps_data_envelope(self):
        api = AsyncMock()
        api.get_event_session.return_value = {"data": {"id": 900, "startsAt": "2019-07-29T17:59:41+03:00"}}
        session = await load_event_session(api, 900, {})
        assert session is not None
        assert session["id"] == 900
        assert session["startsAt"].startswith("2019")
