"""Unit tests for share engagement payload normalization and batch parsing."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import Request

from api.services.share_engagement import (
    ALLOWED_EVENT_NAMES,
    MAX_BODY_BYTES,
    EngagementContext,
    ShareEngagementService,
    normalize_event,
    parse_engagement_batch,
)
from database.share_models import ShareEngagementEventName


@pytest.mark.unit
class TestNormalizeEvent:
    def test_chapter_seek_valid(self):
        out = normalize_event(
            ShareEngagementEventName.CHAPTER_SEEK,
            {"source": "marker", "time_sec": 10, "label": "Intro"},
        )
        assert out == (ShareEngagementEventName.CHAPTER_SEEK, {"source": "marker", "time_sec": 10, "label": "Intro"})

    def test_chapter_seek_rejects_bad_source(self):
        assert normalize_event(ShareEngagementEventName.CHAPTER_SEEK, {"source": "scrub", "time_sec": 1}) is None

    def test_chapter_seek_strips_long_label(self):
        long_label = "x" * 200
        out = normalize_event(
            ShareEngagementEventName.CHAPTER_SEEK,
            {"source": "marker", "time_sec": 1, "label": long_label},
        )
        assert out is not None
        assert len(out[1]["label"]) == 120

    def test_playlist_navigate_valid(self):
        out = normalize_event(
            ShareEngagementEventName.PLAYLIST_NAVIGATE,
            {"from": "autoplay", "to_item_id": 42},
        )
        assert out is not None
        assert out[1]["to_item_id"] == 42

    def test_playback_complete_empty(self):
        assert normalize_event(ShareEngagementEventName.PLAYBACK_COMPLETE, {}) == (
            ShareEngagementEventName.PLAYBACK_COMPLETE,
            {},
        )

    def test_watch_exit_clamps(self):
        out = normalize_event(
            ShareEngagementEventName.WATCH_EXIT,
            {"position_sec": 500, "duration_sec": 100},
        )
        assert out == (ShareEngagementEventName.WATCH_EXIT, {"position_sec": 100, "duration_sec": 100})

    def test_unknown_name(self):
        assert normalize_event("unknown", {}) is None

    def test_sql_injection_like_label_stored_as_text(self):
        out = normalize_event(
            ShareEngagementEventName.CHAPTER_SEEK,
            {"source": "marker", "time_sec": 0, "label": "'; DROP TABLE users;--"},
        )
        assert out is not None
        assert "DROP TABLE" in out[1]["label"]


@pytest.mark.unit
class TestParseEngagementBatch:
    def test_empty_body(self):
        body = parse_engagement_batch(b"")
        assert body is not None
        assert body.events == []

    def test_over_limit_returns_none(self):
        assert parse_engagement_batch(b"x" * (MAX_BODY_BYTES + 1)) is None

    def test_invalid_json_returns_none(self):
        assert parse_engagement_batch(b"{not-json") is None

    def test_unknown_event_name_returns_none(self):
        raw = b'{"session_id":"s","events":[{"name":"evil","payload":{}}]}'
        assert parse_engagement_batch(raw) is None


@pytest.mark.unit
class TestShareEngagementService:
    @pytest.mark.asyncio
    async def test_build_summary_skips_views_only(self):
        svc = ShareEngagementService()
        session = AsyncMock()
        with patch("api.services.share_engagement.ShareEngagementRepository") as repo_cls:
            repo = repo_cls.return_value
            repo.count_page_views_in_range = AsyncMock(return_value=10)
            repo.count_event = AsyncMock(return_value=0)
            repo.chapter_seeks_top = AsyncMock(return_value=[])
            repo.watch_exit_median_ratio = AsyncMock(return_value=None)
            repo.playlist_navigate_by_from = AsyncMock(return_value={"url": 0})

            from datetime import UTC, datetime

            out = await svc.build_summary(
                session,
                from_dt=datetime(2026, 1, 1, tzinfo=UTC),
                to_dt=datetime(2026, 1, 2, tzinfo=UTC),
                recording_id=1,
                owner_user_id="user_a",
            )
            assert out is None
            repo.count_event.assert_awaited_once()
            call_kwargs = repo.count_event.await_args.kwargs
            assert call_kwargs.get("owner_user_id") == "user_a"
            repo.count_page_views_in_range.assert_awaited_once_with(
                recording_ids=[1],
                from_dt=datetime(2026, 1, 1, tzinfo=UTC),
                to_dt=datetime(2026, 1, 2, tzinfo=UTC),
            )

    @pytest.mark.asyncio
    async def test_record_batch_drops_wrong_playlist_item_nav(self):
        svc = ShareEngagementService()
        session = AsyncMock()
        request = MagicMock(spec=Request)
        request.headers = {}
        request.client = MagicMock(host="127.0.0.1")

        context = EngagementContext(
            owner_user_id="owner_1",
            recording_id=5,
            playlist_id=9,
            expected_nav_item_id=100,
        )
        with patch("api.services.share_engagement.visitor_key_for_request", return_value="vk"):
            with patch("api.services.share_engagement.ShareEngagementRepository") as repo_cls:
                repo = repo_cls.return_value
                repo.insert_many = AsyncMock()

                await svc.record_batch(
                    session,
                    context=context,
                    request=request,
                    session_id="sess",
                    events=[
                        {
                            "name": ShareEngagementEventName.PLAYLIST_NAVIGATE,
                            "payload": {"from": "sidebar", "to_item_id": 999},
                        }
                    ],
                )
                repo.insert_many.assert_not_awaited()

    def test_allowed_event_names_match_model_constants(self):
        assert ShareEngagementEventName.CHAPTER_SEEK in ALLOWED_EVENT_NAMES
        assert len(ALLOWED_EVENT_NAMES) == 4
