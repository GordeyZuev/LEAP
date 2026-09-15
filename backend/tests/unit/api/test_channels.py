"""Channel owner/public API and M:N rules."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from tests.fixtures.factories import create_mock_recording


def _channel(*, slug="proga", share=False):
    now = datetime.now(UTC)
    ch = MagicMock()
    ch.id = 1
    ch.user_id = "user_123"
    ch.name = "Program"
    ch.slug = slug
    ch.description = None
    ch.share_enabled = share
    ch.banner_key = None
    ch.created_at = now
    ch.updated_at = now
    return ch


@pytest.mark.unit
class TestChannelOwnerApi:
    def test_list_channels_uses_counts_not_membership(self, client, mocker) -> None:
        ch = _channel()
        mocker.patch(
            "api.services.channel_service.ChannelRepository.list_page",
            new=AsyncMock(return_value=([ch], 1)),
        )
        counts = mocker.patch(
            "api.services.channel_service.ChannelRepository.membership_counts",
            new=AsyncMock(return_value={1: (2, 3)}),
        )
        mocker.patch("api.routers.channels.presign_storage_keys", new=AsyncMock(return_value={}))
        response = client.get("/api/v1/channels")
        assert response.status_code == 200
        item = response.json()["items"][0]
        assert item["video_count"] == 2
        assert item["playlist_count"] == 3
        assert item["slug"] == "proga"
        counts.assert_awaited_once()

    def test_public_filters_disabled(self, client, mocker) -> None:
        from fastapi import HTTPException, status

        mocker.patch(
            "api.services.channel_service.ChannelService.require_public",
            new=AsyncMock(side_effect=HTTPException(status.HTTP_404_NOT_FOUND, detail="not found")),
        )
        response = client.get("/api/v1/c/proga")
        assert response.status_code == 404

    def test_public_looks_called_once(self, client, mocker) -> None:
        ch = _channel(share=True)
        rec_a = create_mock_recording(record_id=11, user_id="user_123", main_topics=["SQL overview"])
        rec_b = create_mock_recording(record_id=12, user_id="user_123")
        rec_a.share_token = uuid4()
        rec_b.share_token = uuid4()
        rec_a.share_enabled = True
        rec_b.share_enabled = True
        svc = MagicMock()
        svc.require_public = AsyncMock(return_value=ch)
        svc.repo.public_videos = AsyncMock(return_value=[(MagicMock(), rec_a), (MagicMock(), rec_b)])
        svc.repo.public_playlists = AsyncMock(return_value=[])
        mocker.patch("api.routers.channels.ChannelService", return_value=svc)
        looks = mocker.patch(
            "api.routers.channels.publication_looks_for_recordings",
            new=AsyncMock(return_value={11: MagicMock(title="Published YouTube title")}),
        )
        mocker.patch("api.routers.channels.poster_preview_map", new=AsyncMock(return_value={}))
        response = client.get("/api/v1/c/proga")
        assert response.status_code == 200
        assert looks.await_count == 1
        videos = response.json()["videos"]
        assert len(videos) == 2
        assert videos[0]["title"] == rec_a.display_name
        assert videos[0]["start_time"]
        assert videos[0]["blurb"] == "SQL overview"
        assert videos[1]["blurb"] is None

    def test_public_playlist_blurb(self, client, mocker) -> None:
        ch = _channel(share=True)
        pl = MagicMock()
        pl.id = 3
        pl.name = "Course"
        pl.description = "About {{ video_count }} lectures"
        pl.share_token = uuid4()
        pl.cover_key = None
        svc = MagicMock()
        svc.require_public = AsyncMock(return_value=ch)
        svc.repo.public_videos = AsyncMock(return_value=[])
        svc.repo.public_playlists = AsyncMock(return_value=[(MagicMock(), pl)])
        mocker.patch("api.routers.channels.ChannelService", return_value=svc)
        mocker.patch("api.routers.channels.publication_looks_for_recordings", new=AsyncMock(return_value={}))
        mocker.patch("api.routers.channels.poster_preview_map", new=AsyncMock(return_value={}))
        mocker.patch("api.routers.channels.presign_storage_keys", new=AsyncMock(return_value={}))
        mocker.patch(
            "api.routers.channels.PlaylistRepository.aggregate_stats",
            new=AsyncMock(return_value={3: (4, 100.0)}),
        )
        mocker.patch(
            "api.routers.channels.PlaylistRepository.first_playable_recordings",
            new=AsyncMock(return_value={}),
        )
        response = client.get("/api/v1/c/proga")
        assert response.status_code == 200
        item = response.json()["playlists"][0]
        assert item["blurb"] == "About 4 lectures"
