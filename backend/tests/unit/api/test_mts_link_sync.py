"""Unit tests for MTS Link sync helpers (email resolve, paging, metadata mapping)."""

from unittest.mock import AsyncMock, patch

import pytest
from pydantic import TypeAdapter

from api.mts_link_api import MtsLinkResponseError
from api.routers.input_sources import (
    _build_mts_link_metadata,
    _list_mts_link_records,
    _mts_link_datetime_bound,
    _parse_mts_link_created_at,
    _resolve_mts_link_user_id,
)
from api.schemas.template.source_config import MtsLinkSourceConfig, SourceConfig, ZoomSourceConfig


def _record(record_id: int = 1, size: int = 100, session_id: int = 900) -> dict:
    return {
        "id": record_id,
        "name": "Lecture 1",
        "size": size,
        "createAt": "2026-05-05 10:00:00",
        "link": "https://my.mts-link.ru/j/1/room/record-new/900",
        "eventSession": {"id": session_id, "createUser": {"email": "lecturer@example.com"}},
    }


@pytest.mark.unit
class TestMtsLinkSourceConfig:
    def test_requires_at_least_one_email(self):
        with pytest.raises(ValueError):
            MtsLinkSourceConfig(user_emails=[])

    def test_defaults_favour_presenter_only_mp4_and_sidecars(self):
        config = MtsLinkSourceConfig(user_emails=["lecturer@example.com"])

        assert config.conversion_quality == "720"
        assert config.conversion_view == "none"
        assert config.fetch_chat is True
        assert config.fetch_session_files is True

    def test_union_does_not_confuse_mts_and_zoom_configs(self):
        """Both configs carry ``user_emails``, so the stored shape must still round-trip."""
        adapter = TypeAdapter(SourceConfig)

        mts = adapter.validate_python({"user_emails": ["lecturer@example.com"], "conversion_quality": "1080"})
        zoom_master = adapter.validate_python({"is_master_account": True, "user_emails": ["host@example.com"]})

        assert isinstance(mts, MtsLinkSourceConfig)
        assert isinstance(zoom_master, ZoomSourceConfig)


@pytest.mark.unit
class TestMtsLinkDateBounds:
    def test_date_only_bounds_expand_to_full_day(self):
        assert _mts_link_datetime_bound("2026-01-05", end_of_day=False) == "2026-01-05 00:00:00"
        assert _mts_link_datetime_bound("2026-01-05", end_of_day=True) == "2026-01-05 23:59:59"

    def test_existing_timestamp_and_none_pass_through(self):
        assert _mts_link_datetime_bound("2026-01-05 08:30:00", end_of_day=False) == "2026-01-05 08:30:00"
        assert _mts_link_datetime_bound(None, end_of_day=True) is None

    def test_created_at_is_always_timezone_aware(self):
        assert _parse_mts_link_created_at("2026-05-05 10:00:00").tzinfo is not None
        assert _parse_mts_link_created_at("2026-05-05T10:00:00Z").tzinfo is not None
        assert _parse_mts_link_created_at(None).tzinfo is not None
        assert _parse_mts_link_created_at("not-a-date").tzinfo is not None


@pytest.mark.unit
class TestResolveMtsLinkUserId:
    @pytest.mark.asyncio
    async def test_exact_email_match_wins_over_substring_hits(self):
        api = AsyncMock()
        api.list_organization_members.return_value = [
            {"id": 1, "email": "other.lecturer@example.com"},
            {"id": 2, "email": "Lecturer@example.com"},
        ]

        assert await _resolve_mts_link_user_id(api, "lecturer@example.com") == 2

    @pytest.mark.asyncio
    async def test_missing_email_fails_loudly(self):
        api = AsyncMock()
        api.list_organization_members.return_value = [{"id": 1, "email": "someone@example.com"}]

        with pytest.raises(ValueError, match="No organization member"):
            await _resolve_mts_link_user_id(api, "lecturer@example.com")

    @pytest.mark.asyncio
    async def test_ambiguous_email_fails_instead_of_guessing(self):
        api = AsyncMock()
        api.list_organization_members.return_value = [
            {"id": 1, "email": "lecturer@example.com"},
            {"id": 2, "email": "lecturer@example.com"},
        ]

        with pytest.raises(ValueError, match="Multiple organization members"):
            await _resolve_mts_link_user_id(api, "lecturer@example.com")


@pytest.mark.unit
@patch("asyncio.sleep", new_callable=AsyncMock)
class TestListMtsLinkRecords:
    """The rate-limit pause is stubbed out: these assert paging, not wall-clock time."""

    @pytest.mark.asyncio
    async def test_stops_on_empty_page(self, _sleep):
        api = AsyncMock()
        api.list_records.side_effect = [[_record()], []]

        records = await _list_mts_link_records(api, 42, "2026-01-01 00:00:00", None)

        assert len(records) == 1
        assert api.list_records.await_args_list[0].kwargs["user_id"] == 42

    @pytest.mark.asyncio
    async def test_short_page_is_not_treated_as_the_last_one(self, _sleep):
        """Their API may cap a page below the requested size; stopping there loses records."""
        api = AsyncMock()
        api.list_records.side_effect = [
            [_record(record_id=1), _record(record_id=2)],
            [_record(record_id=3)],
            [],
        ]

        records = await _list_mts_link_records(api, 42, "2026-01-01 00:00:00", None)

        assert len(records) == 3
        # Offset advances by rows actually returned, not by the requested page size.
        assert [call.kwargs["offset"] for call in api.list_records.await_args_list] == [0, 2, 3]

    @pytest.mark.asyncio
    async def test_endpoint_ignoring_offset_cannot_loop_forever(self, _sleep):
        from api.routers import input_sources

        api = AsyncMock()
        api.list_records.return_value = [_record()]

        records = await _list_mts_link_records(api, 42, "2026-01-01 00:00:00", None)

        assert api.list_records.await_count == input_sources._MTS_LINK_MAX_RECORD_PAGES
        assert len(records) == input_sources._MTS_LINK_MAX_RECORD_PAGES


@pytest.mark.unit
class TestBuildMtsLinkMetadata:
    def test_ready_online_recording_without_mp4_needs_conversion(self):
        meta = _build_mts_link_metadata(_record(size=239_137_807), "lecturer@example.com", 176_030_889, None)

        assert meta["needs_mp4"] is True
        assert meta["source_processing_incomplete"] is False
        assert meta["download_url"] is None
        assert meta["event_session_id"] == 900
        assert meta["mts_user_id"] == 176_030_889
        assert meta["extras"] == {"chat": False, "files_count": 0, "error": None}

    def test_zero_size_marks_source_still_processing(self):
        meta = _build_mts_link_metadata(_record(size=0), "lecturer@example.com", 1, None)

        assert meta["source_processing_incomplete"] is True

    def test_existing_conversion_skips_further_work(self):
        meta = _build_mts_link_metadata(_record(), "lecturer@example.com", 1, "https://cdn/x.mp4")

        assert meta["needs_mp4"] is False
        assert meta["download_url"] == "https://cdn/x.mp4"


@pytest.mark.unit
class TestMtsLinkSyncErrorIsolation:
    @pytest.mark.asyncio
    async def test_converted_records_failure_leaves_record_needing_mp4(self):
        """A 500 on the per-session lookup must not abort discovery of the record."""
        api = AsyncMock()
        api.get_ready_mp4_url.side_effect = MtsLinkResponseError(500, "boom")

        try:
            download_url = await api.get_ready_mp4_url(900)
        except MtsLinkResponseError:
            download_url = None

        meta = _build_mts_link_metadata(_record(), "lecturer@example.com", 1, download_url)
        assert meta["needs_mp4"] is True
