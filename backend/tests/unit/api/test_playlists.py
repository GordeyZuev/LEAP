"""Unit tests for playlist service rules and owner/public API."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from api.schemas.playlist import PlaylistCreate, PlaylistUpdate
from api.services.playlist_service import (
    SHARE_NOT_FOUND,
    PlaylistService,
    assert_public_download,
    is_playable,
    item_unavailable_reason,
)
from tests.fixtures.factories import create_mock_recording


@pytest.mark.unit
class TestPlaylistDescriptionSchema:
    def test_keeps_line_breaks_and_indent(self) -> None:
        body = "Intro\n  indented\nthird"
        created = PlaylistCreate(name="Course", description=body)
        assert created.description == body
        updated = PlaylistUpdate(description=body)
        assert updated.description == body

    def test_blank_becomes_none(self) -> None:
        assert PlaylistCreate(name="Course", description="   \n  ").description is None


@pytest.mark.unit
class TestPlayableHelpers:
    def test_not_ready_when_no_processed_path(self) -> None:
        rec = create_mock_recording(processed_video_path=None, delete_state="active")
        rec.blank_record = False
        rec.deleted = False
        assert item_unavailable_reason(rec) == "not_ready"
        assert is_playable(rec) is False

    def test_playable_when_processed_exists(self) -> None:
        rec = create_mock_recording(processed_video_path="users/x/video.mp4", delete_state="active")
        rec.blank_record = False
        rec.deleted = False
        assert item_unavailable_reason(rec) is None
        assert is_playable(rec) is True

    def test_deleted_reason(self) -> None:
        rec = create_mock_recording(deleted=True, processed_video_path="x", delete_state="soft_deleted")
        assert item_unavailable_reason(rec) == "deleted"

    def test_blank_reason(self) -> None:
        rec = create_mock_recording(blank_record=True, processed_video_path="x", delete_state="active")
        rec.deleted = False
        assert item_unavailable_reason(rec) == "blank"


@pytest.mark.unit
class TestDownloadAcl:
    def test_inline_always_allowed(self) -> None:
        assert_public_download(allow_video=False, allow_files=False, kind="files", inline=True)

    def test_video_download_forbidden(self) -> None:
        with pytest.raises(HTTPException) as exc:
            assert_public_download(allow_video=False, allow_files=True, kind="video")
        assert exc.value.status_code == 403

    def test_files_download_forbidden(self) -> None:
        with pytest.raises(HTTPException) as exc:
            assert_public_download(allow_video=True, allow_files=False, kind="files")
        assert exc.value.status_code == 403


def _playlist(*, name="Course", user_id="user_123", items=None, token=None, enabled=False):
    now = datetime.now(UTC)
    pl = MagicMock()
    pl.id = 1
    pl.user_id = user_id
    pl.name = name
    pl.description = None
    pl.items = items if items is not None else []
    pl.share_token = token
    pl.share_enabled = enabled
    pl.share_created_at = now if token else None
    pl.created_at = now
    pl.updated_at = now
    return pl


@pytest.mark.unit
class TestPlaylistService:
    @pytest.mark.asyncio
    async def test_add_items_foreign_recording_404(self) -> None:
        session = AsyncMock()
        empty = MagicMock()
        empty.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(return_value=empty)
        svc = PlaylistService(session, "user_123")
        with pytest.raises(HTTPException) as exc:
            await svc.add_items(_playlist(), [99])
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_add_items_duplicate_is_noop(self) -> None:
        session = AsyncMock()
        existing = MagicMock()
        existing.recording_id = 7
        playlist = _playlist(items=[existing])
        svc = PlaylistService(session, "user_123")
        created = await svc.add_items(playlist, [7])
        assert created == []
        session.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_reorder_stale_set_409(self) -> None:
        session = AsyncMock()
        a = MagicMock()
        a.id = 1
        b = MagicMock()
        b.id = 2
        svc = PlaylistService(session, "user_123")
        with pytest.raises(HTTPException) as exc:
            await svc.reorder(_playlist(items=[a, b]), [1])
        assert exc.value.status_code == 409

    @pytest.mark.asyncio
    async def test_create_duplicate_name_409(self) -> None:
        session = AsyncMock()
        session.flush = AsyncMock(side_effect=IntegrityError("INSERT", {}, Exception("unique")))
        session.rollback = AsyncMock()
        svc = PlaylistService(session, "user_123")
        svc.repo = MagicMock()
        svc.repo.count_by_user = AsyncMock(return_value=0)
        with patch("api.services.playlist_service.PlaylistModel", return_value=MagicMock()):
            with pytest.raises(HTTPException) as exc:
                await svc.create("Algorp", None)
        assert exc.value.status_code == 409
        assert exc.value.detail == "A playlist with this name already exists."
        session.rollback.assert_awaited()

    @pytest.mark.asyncio
    async def test_enable_disable_keeps_token(self) -> None:
        session = AsyncMock()
        session.flush = AsyncMock()
        playlist = _playlist()
        svc = PlaylistService(session, "user_123")
        await svc.enable_share(playlist)
        token = playlist.share_token
        assert token is not None
        assert playlist.share_enabled is True
        await svc.disable_share(playlist)
        assert playlist.share_enabled is False
        assert playlist.share_token == token
        await svc.enable_share(playlist)
        assert playlist.share_token == token
        assert playlist.share_enabled is True

    @pytest.mark.asyncio
    async def test_rotate_changes_token(self) -> None:
        session = AsyncMock()
        session.flush = AsyncMock()
        old = uuid.uuid4()
        playlist = _playlist(token=old, enabled=True)
        svc = PlaylistService(session, "user_123")
        await svc.rotate_share(playlist)
        assert playlist.share_token != old
        assert playlist.share_enabled is True

    @pytest.mark.asyncio
    async def test_add_from_template_skips_default(self) -> None:
        session = AsyncMock()
        template = MagicMock()
        template.is_default = True
        template.output_config = {"playlist_ids": [1]}
        result = MagicMock()
        result.scalar_one_or_none.return_value = template
        session.execute = AsyncMock(return_value=result)
        rec = create_mock_recording(template_id=5)
        svc = PlaylistService(session, "user_123")
        with patch.object(svc, "_add_recording_to_playlist_ids", new=AsyncMock()) as add:
            await svc.add_from_template(rec)
            add.assert_not_called()


@pytest.mark.unit
class TestPlaylistOwnerApi:
    def test_create_playlist(self, client, mocker) -> None:
        created = _playlist(name="Algorp")
        created.id = 3
        mocker.patch("api.routers.playlists.PlaylistService.create", new=AsyncMock(return_value=created))
        response = client.post("/api/v1/playlists", json={"name": "Algorp"})
        assert response.status_code == 201
        assert response.json()["name"] == "Algorp"

    def test_list_playlists(self, client, mocker) -> None:
        pl = _playlist(name="Algorp")
        pl.id = 3
        mocker.patch(
            "api.services.playlist_service.PlaylistRepository.list_by_user",
            new=AsyncMock(return_value=[pl]),
        )
        response = client.get("/api/v1/playlists")
        assert response.status_code == 200
        assert response.json()["total"] == 1
        assert response.json()["items"][0]["name"] == "Algorp"


def _storage_ok(mocker) -> None:
    storage = MagicMock()
    storage.exists = AsyncMock(return_value=True)
    storage.presigned_url = AsyncMock(return_value="https://cdn.example/video.mp4")
    mocker.patch("file_storage.factory.get_storage_backend", return_value=storage)


@pytest.mark.unit
class TestShareDownloadFlags:
    def test_recording_media_play_200_when_download_off(self, client, mocker) -> None:
        rec = create_mock_recording(record_id=8, processed_video_path="k.mp4", allow_video_download=False)
        rec.local_video_path = None
        mocker.patch("api.routers.share._get_recording_by_share_token", new=AsyncMock(return_value=rec))
        _storage_ok(mocker)
        response = client.get(f"/api/v1/share/{uuid.uuid4()}/media?type=processed")
        assert response.status_code == 200

    def test_recording_media_download_403(self, client, mocker) -> None:
        rec = create_mock_recording(record_id=8, processed_video_path="k.mp4", allow_video_download=False)
        rec.local_video_path = None
        mocker.patch("api.routers.share._get_recording_by_share_token", new=AsyncMock(return_value=rec))
        response = client.get(f"/api/v1/share/{uuid.uuid4()}/media?type=processed&download=true")
        assert response.status_code == 403

    def test_playlist_media_download_403(self, client, mocker) -> None:
        rec = create_mock_recording(record_id=8, processed_video_path="k.mp4", allow_video_download=False)
        rec.deleted = False
        rec.delete_state = "active"
        item = MagicMock()
        item.id = 11
        item.recording = rec
        pl = _playlist(enabled=True, token=uuid.uuid4(), items=[item])
        mocker.patch("api.routers.share._get_enabled_playlist", new=AsyncMock(return_value=pl))
        response = client.get(f"/api/v1/share/p/{pl.share_token}/items/11/media?type=processed&download=true")
        assert response.status_code == 403

    def test_unknown_and_disabled_playlist_same_404(self, client, mocker) -> None:
        mocker.patch("api.routers.share.PlaylistRepository.get_by_share_token", new=AsyncMock(return_value=None))
        unknown = client.get(f"/api/v1/share/p/{uuid.uuid4()}")
        assert unknown.status_code == 404
        assert unknown.json()["detail"] == SHARE_NOT_FOUND

        disabled = _playlist(enabled=False, token=uuid.uuid4())
        mocker.patch("api.routers.share.PlaylistRepository.get_by_share_token", new=AsyncMock(return_value=disabled))
        off = client.get(f"/api/v1/share/p/{disabled.share_token}")
        assert off.status_code == 404
        assert off.json()["detail"] == SHARE_NOT_FOUND

    def test_empty_playlist_200(self, client, mocker) -> None:
        pl = _playlist(name="Empty", enabled=True, token=uuid.uuid4(), items=[])
        mocker.patch("api.routers.share._get_enabled_playlist", new=AsyncMock(return_value=pl))
        response = client.get(f"/api/v1/share/p/{pl.share_token}")
        assert response.status_code == 200
        body = response.json()
        assert body["items"] == []
        assert body["name"] == "Empty"

    def test_playlist_poster_uses_first_item(self, client, mocker) -> None:
        rec = create_mock_recording(record_id=9)
        item = MagicMock()
        item.position = 0
        item.recording = rec
        pl = _playlist(enabled=True, token=uuid.uuid4(), items=[item])
        mocker.patch("api.routers.share._get_enabled_playlist", new=AsyncMock(return_value=pl))
        mocker.patch(
            "api.routers.share.poster_url_map",
            new=AsyncMock(return_value={rec.id: "https://cdn.example/course.jpg"}),
        )
        response = client.get(f"/api/v1/share/p/{pl.share_token}/poster", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "https://cdn.example/course.jpg"

    def test_playlist_item_beacon_counts_view(self, client, mocker) -> None:
        rec = create_mock_recording(record_id=8, processed_video_path="k.mp4", delete_state="active")
        rec.deleted = False
        rec.blank_record = False
        item = MagicMock()
        item.id = 11
        item.recording = rec
        pl = _playlist(enabled=True, token=uuid.uuid4(), items=[item])
        mocker.patch("api.routers.share._get_enabled_playlist", new=AsyncMock(return_value=pl))
        track = mocker.patch("api.routers.share._track_page_view_safe", new=AsyncMock())
        response = client.post(f"/api/v1/share/p/{pl.share_token}/items/11/beacon")
        assert response.status_code == 204
        track.assert_awaited_once()

    def test_playlist_item_beacon_unknown_still_204(self, client, mocker) -> None:
        mocker.patch(
            "api.routers.share._get_enabled_playlist",
            new=AsyncMock(side_effect=HTTPException(status_code=404, detail=SHARE_NOT_FOUND)),
        )
        track = mocker.patch("api.routers.share._track_page_view_safe", new=AsyncMock())
        response = client.post(f"/api/v1/share/p/{uuid.uuid4()}/items/11/beacon")
        assert response.status_code == 204
        track.assert_not_called()

    def test_playlist_item_beacon_skips_deleted_recording(self, client, mocker) -> None:
        rec = create_mock_recording(record_id=8, deleted=True)
        rec.deleted = True
        item = MagicMock()
        item.id = 11
        item.recording = rec
        pl = _playlist(enabled=True, token=uuid.uuid4(), items=[item])
        mocker.patch("api.routers.share._get_enabled_playlist", new=AsyncMock(return_value=pl))
        track = mocker.patch("api.routers.share._track_page_view_safe", new=AsyncMock())
        response = client.post(f"/api/v1/share/p/{pl.share_token}/items/11/beacon")
        assert response.status_code == 204
        track.assert_not_called()

    def test_playlist_item_beacon_skips_not_ready(self, client, mocker) -> None:
        rec = create_mock_recording(record_id=8, processed_video_path=None, delete_state="active")
        rec.deleted = False
        rec.blank_record = False
        item = MagicMock()
        item.id = 11
        item.recording = rec
        pl = _playlist(enabled=True, token=uuid.uuid4(), items=[item])
        mocker.patch("api.routers.share._get_enabled_playlist", new=AsyncMock(return_value=pl))
        track = mocker.patch("api.routers.share._track_page_view_safe", new=AsyncMock())
        response = client.post(f"/api/v1/share/p/{pl.share_token}/items/11/beacon")
        assert response.status_code == 204
        track.assert_not_called()
