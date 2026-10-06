"""Saved sort rules for playlist items and channel members."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from api.helpers.catalog_sort import natural_key, video_name_key, video_sort_key
from tests.fixtures.factories import create_mock_recording


def _playlist_service():
    from api.services.playlist_service import PlaylistService

    return PlaylistService(AsyncMock(), "user_123")


def _channel_service():
    # channel_repo builds loader options at import time, so import after the app has mapped every model.
    from api.main import app  # noqa: F401
    from api.services.channel_service import ChannelService

    return ChannelService(AsyncMock(), "user_123")


def _rec(record_id: int, title: str, day: int, minutes: int):
    rec = create_mock_recording(
        record_id=record_id,
        display_name=title,
        start_time=datetime(2026, 9, day, tzinfo=UTC),
        duration=minutes * 60,
    )
    rec.final_duration = None
    return rec


def _item(item_id: int, position: int, rec):
    item = MagicMock()
    item.id = item_id
    item.position = position
    item.recording = rec
    return item


@pytest.mark.unit
class TestSortKeys:
    def test_names_sort_naturally_without_case_or_zoom_timestamp(self) -> None:
        titles = ["lecture 10", "2026-09-01_10-00 Lecture 2", "Lecture 1"]
        assert sorted(titles, key=video_name_key) == ["Lecture 1", "2026-09-01_10-00 Lecture 2", "lecture 10"]

    def test_bare_timestamp_title_is_kept(self) -> None:
        assert video_name_key("2026-09-01 10:00") == natural_key("2026-09-01 10:00")

    def test_missing_start_time_is_oldest(self) -> None:
        dated = video_sort_key("newest", title="a", start_time=datetime(2026, 1, 1, tzinfo=UTC))
        undated = video_sort_key("newest", title="a", start_time=None)
        assert dated < undated
        assert video_sort_key("oldest", title="a", start_time=None) < -dated


@pytest.mark.unit
class TestPlaylistSavedSort:
    @pytest.mark.asyncio
    async def test_saved_rule_rewrites_dense_positions(self, mocker) -> None:
        mocker.patch("api.services.playlist_service.publication_looks_for_recordings", new=AsyncMock(return_value={}))
        old, new, mid = _rec(1, "A", 1, 30), _rec(2, "B", 20, 10), _rec(3, "C", 10, 50)
        items = [_item(10, 0, old), _item(11, 4, new), _item(12, 9, mid)]
        playlist = MagicMock(items=items, item_sort="newest")
        await _playlist_service().apply_item_sort(playlist)
        assert [(i.id, i.position) for i in sorted(items, key=lambda i: i.position)] == [(11, 0), (12, 1), (10, 2)]

    @pytest.mark.asyncio
    async def test_name_uses_publication_title(self, mocker) -> None:
        looks = {1: MagicMock(title="Lecture 2"), 2: MagicMock(title="")}
        mocker.patch(
            "api.services.playlist_service.publication_looks_for_recordings", new=AsyncMock(return_value=looks)
        )
        items = [_item(10, 0, _rec(1, "zzz", 1, 1)), _item(11, 1, _rec(2, "Lecture 10", 2, 1))]
        playlist = MagicMock(items=items, item_sort="name")
        await _playlist_service().apply_item_sort(playlist)
        assert [i.position for i in items] == [0, 1]

    @pytest.mark.asyncio
    async def test_custom_order_is_left_alone(self, mocker) -> None:
        looks = mocker.patch("api.services.playlist_service.publication_looks_for_recordings", new=AsyncMock())
        items = [_item(10, 5, _rec(1, "B", 1, 1)), _item(11, 2, _rec(2, "A", 2, 1))]
        await _playlist_service().apply_item_sort(MagicMock(items=items, item_sort=None))
        assert [i.position for i in items] == [5, 2]
        looks.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_drag_clears_saved_rule(self) -> None:
        items = [_item(10, 0, _rec(1, "A", 1, 1)), _item(11, 1, _rec(2, "B", 2, 1))]
        playlist = MagicMock(items=items, item_sort="name")
        await _playlist_service().reorder(playlist, [11, 10])
        assert playlist.item_sort is None
        assert [i.position for i in items] == [1, 0]

    @pytest.mark.asyncio
    async def test_picking_a_rule_saves_and_applies_it(self, mocker) -> None:
        looks = mocker.patch("api.services.playlist_service.publication_looks_for_recordings", new=AsyncMock())
        items = [_item(10, 0, _rec(1, "A", 1, 10)), _item(11, 1, _rec(2, "B", 2, 90))]
        playlist = MagicMock(items=items, item_sort=None)
        await _playlist_service().set_item_sort(playlist, "newest")
        assert playlist.item_sort == "newest"
        assert [i.position for i in items] == [1, 0]
        looks.assert_not_awaited()


@pytest.mark.unit
class TestChannelSavedSort:
    @pytest.mark.asyncio
    async def test_saved_video_rule_rewrites_positions(self, mocker) -> None:
        svc = _channel_service()
        mocker.patch("api.services.channel_service.publication_looks_for_recordings", new=AsyncMock(return_value={}))
        rows = [_item(1, 0, _rec(1, "A", 20, 1)), _item(2, 3, _rec(2, "B", 1, 1))]
        svc.repo.list_videos = AsyncMock(return_value=rows)
        await svc.apply_video_sort(MagicMock(id=1, video_sort="oldest"))
        assert [r.position for r in rows] == [1, 0]

    @pytest.mark.asyncio
    async def test_saved_playlist_rule_sorts_names_naturally(self) -> None:
        svc = _channel_service()
        rows = [MagicMock(position=0), MagicMock(position=1)]
        rows[0].playlist.name, rows[1].playlist.name = "Module 10", "module 2"
        svc.repo.list_channel_playlists = AsyncMock(return_value=rows)
        await svc.apply_playlist_sort(MagicMock(id=1, playlist_sort="name"))
        assert [r.position for r in rows] == [1, 0]

    @pytest.mark.asyncio
    async def test_drag_clears_saved_rules(self) -> None:
        svc = _channel_service()
        channel = MagicMock(id=1, video_sort="name", playlist_sort="name")
        svc.repo.list_videos = AsyncMock(return_value=[MagicMock(recording_id=5, position=0)])
        svc.repo.list_channel_playlists = AsyncMock(return_value=[MagicMock(playlist_id=7, position=0)])
        await svc.reorder_videos(channel, [5])
        await svc.reorder_playlists(channel, [7])
        assert channel.video_sort is None
        assert channel.playlist_sort is None
