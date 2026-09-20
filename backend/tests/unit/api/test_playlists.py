"""Unit tests for playlist service rules and owner/public API."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from api.core.context import ServiceContext
from api.repositories.playlist_repo import PlaylistRepository
from api.routers.playlists import _cover_asset_key, set_playlist_item_group
from api.schemas.playlist import PlaylistCreate, PlaylistItemGroupUpdate, PlaylistUpdate, PublicChannelLink
from api.services.playlist_service import (
    SHARE_NOT_FOUND,
    PlaylistService,
    assert_public_download,
    is_playable,
    item_unavailable_reason,
)
from tests.fixtures.factories import create_mock_recording


@pytest.mark.unit
@pytest.mark.asyncio
async def test_public_playlist_aggregate_queries_require_recording_owner(client) -> None:
    from sqlalchemy.dialects import postgresql

    session = AsyncMock()
    result = MagicMock()
    result.all.return_value = []
    session.execute.return_value = result
    repo = PlaylistRepository(session)

    await repo.aggregate_stats([1])
    stats_sql = str(session.execute.await_args.args[0].compile(dialect=postgresql.dialect()))
    await repo.first_playable_recordings([1])
    poster_sql = str(session.execute.await_args.args[0].compile(dialect=postgresql.dialect()))
    await repo.item_titles_by_playlist([1])
    title_sql = str(session.execute.await_args.args[0].compile(dialect=postgresql.dialect()))

    assert all("recordings.user_id = playlists.user_id" in sql for sql in (stats_sql, poster_sql, title_sql))


@pytest.mark.unit
@pytest.mark.asyncio
async def test_public_playlist_surface_lookup_requires_enabled_token(client) -> None:
    from sqlalchemy.dialects import postgresql

    session = AsyncMock()
    result = MagicMock()
    result.one_or_none.return_value = (7, "owner")
    session.execute.return_value = result

    assert await PlaylistRepository(session).get_public_surface_by_share_token(uuid.uuid4()) == (7, "owner")
    sql = str(session.execute.await_args.args[0].compile(dialect=postgresql.dialect()))
    assert "playlists.share_token" in sql
    assert "playlists.share_enabled IS true" in sql
    assert "playlist_items" not in sql


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
    pl.groups = []
    pl.share_token = token
    pl.share_enabled = enabled
    pl.share_created_at = now if token else None
    pl.created_at = now
    pl.updated_at = now
    pl.cover_key = None
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
    async def test_add_from_playlist_ids_delegates(self) -> None:
        session = AsyncMock()
        rec = create_mock_recording()
        svc = PlaylistService(session, "user_123")
        with patch.object(svc, "_add_recording_to_playlist_ids", new=AsyncMock()) as add:
            await svc.add_from_playlist_ids(rec, [1, 2])
            add.assert_awaited_once_with(rec, [1, 2])


@pytest.mark.unit
class TestPlaylistOwnerApi:
    def test_cover_identity_changes_when_same_key_is_replaced(self) -> None:
        playlist = _playlist()
        playlist.cover_key = "users/user_000001/playlists/1/cover.jpg"
        first = _cover_asset_key(playlist)
        playlist.updated_at = datetime.fromtimestamp(playlist.updated_at.timestamp() + 1, UTC)
        assert _cover_asset_key(playlist) != first

    def test_create_playlist(self, client, mocker) -> None:
        created = _playlist(name="Algorp")
        created.id = 3
        mocker.patch("api.routers.playlists.PlaylistService.create", new=AsyncMock(return_value=created))
        response = client.post("/api/v1/playlists", json={"name": "Algorp"})
        assert response.status_code == 201
        assert response.json()["name"] == "Algorp"

    def test_list_playlists(self, client, mocker) -> None:
        token = uuid.uuid4()
        pl = _playlist(name="Algorp", token=token, enabled=True)
        pl.id = 3
        mocker.patch(
            "api.services.playlist_service.PlaylistRepository.list_page",
            new=AsyncMock(return_value=([pl], 1)),
        )
        mocker.patch(
            "api.services.playlist_service.PlaylistRepository.aggregate_stats",
            new=AsyncMock(return_value={3: (0, 0.0)}),
        )
        mocker.patch(
            "api.services.playlist_service.PlaylistRepository.first_playable_recordings",
            new=AsyncMock(return_value={}),
        )
        mocker.patch("api.routers.playlists.presign_storage_keys", new=AsyncMock(return_value={}))
        mocker.patch("api.routers.playlists.publication_looks_for_recordings", new=AsyncMock(return_value={}))
        mocker.patch("api.routers.playlists.poster_preview_map", new=AsyncMock(return_value={}))
        response = client.get("/api/v1/playlists")
        assert response.status_code == 200
        assert response.json()["total"] == 1
        item = response.json()["items"][0]
        assert item["name"] == "Algorp"
        assert item["share_enabled"] is True
        assert item["share_token"] == str(token)

    def test_list_playlists_skips_auto_cover_query_for_custom_covers(self, client, mocker) -> None:
        covered = _playlist(name="Covered")
        covered.id = 3
        covered.cover_key = "users/user_000001/covers/3.jpg"
        uncovered = _playlist(name="Auto cover")
        uncovered.id = 4

        mocker.patch(
            "api.services.playlist_service.PlaylistRepository.list_page",
            new=AsyncMock(return_value=([covered, uncovered], 2)),
        )
        mocker.patch(
            "api.services.playlist_service.PlaylistRepository.aggregate_stats",
            new=AsyncMock(return_value={}),
        )
        first_playable = mocker.patch(
            "api.services.playlist_service.PlaylistRepository.first_playable_recordings",
            new=AsyncMock(return_value={}),
        )
        mocker.patch(
            "api.routers.playlists.presign_storage_keys", new=AsyncMock(return_value={covered.cover_key: "signed"})
        )
        mocker.patch("api.routers.playlists.presigned_image_refresh_at_ms", return_value=123_000)

        response = client.get("/api/v1/playlists")

        assert response.status_code == 200
        first_playable.assert_awaited_once_with([4])
        assert response.json()["items"][0]["poster_refresh_at_ms"] == 123_000
        assert response.json()["items"][1]["poster_refresh_at_ms"] is None

    @pytest.mark.asyncio
    async def test_cannot_assign_item_to_group_from_another_playlist(self, mocker) -> None:
        session = AsyncMock()
        session.scalar = AsyncMock(return_value=None)
        item = MagicMock(group_id=None)
        mocker.patch("api.routers.playlists.PlaylistService.get_owned", new=AsyncMock(return_value=_playlist()))
        mocker.patch("api.repositories.playlist_repo.PlaylistRepository.get_item", new=AsyncMock(return_value=item))

        with pytest.raises(HTTPException) as exc:
            await set_playlist_item_group(
                1, 11, PlaylistItemGroupUpdate(group_id=99), ServiceContext(session=session, user_id="user_123")
            )

        assert exc.value.status_code == 404
        assert item.group_id is None
        session.commit.assert_not_awaited()


def _storage_ok(mocker) -> None:
    storage = MagicMock()
    storage.exists = AsyncMock(return_value=True)
    storage.presigned_url = AsyncMock(return_value="https://cdn.example/video.mp4")
    mocker.patch("file_storage.factory.get_storage_backend", return_value=storage)


@pytest.mark.unit
class TestShareDownloadFlags:
    @pytest.mark.asyncio
    async def test_direct_share_lookup_rejects_deleting_or_orphan_recordings(self) -> None:
        from sqlalchemy.dialects import postgresql

        from api.routers.share import _get_recording_by_share_token

        session = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=result)

        with pytest.raises(HTTPException) as exc:
            await _get_recording_by_share_token(uuid.uuid4(), session)

        sql = str(session.execute.await_args.args[0].compile(dialect=postgresql.dialect()))
        assert exc.value.status_code == 404
        assert "recordings.delete_state =" in sql
        assert "recordings.user_id IS NOT NULL" in sql

    def test_share_file_inline_streams_body(self, client, mocker) -> None:
        rec = create_mock_recording(record_id=8, processed_video_path="k.mp4")
        rec.owner = MagicMock(user_slug=1)
        mocker.patch("api.routers.share._get_recording_by_share_token", new=AsyncMock(return_value=rec))
        storage = MagicMock()
        storage.exists = AsyncMock(return_value=True)
        storage.load = AsyncMock(return_value=b"WEBVTT\n")
        mocker.patch("file_storage.factory.get_storage_backend", return_value=storage)
        response = client.get(f"/api/v1/share/{uuid.uuid4()}/files/vtt?inline=true", follow_redirects=False)
        assert response.status_code == 200
        assert response.content == b"WEBVTT\n"
        assert "text/vtt" in response.headers["content-type"]
        storage.presigned_url.assert_not_called()
        storage.load.assert_awaited_once()

    def test_inline_transcript_cannot_bypass_disabled_files(self, client, mocker) -> None:
        rec = create_mock_recording(record_id=8, processed_video_path="k.mp4", allow_files_download=False)
        rec.owner = MagicMock(user_slug=1)
        mocker.patch("api.routers.share._get_recording_by_share_token", new=AsyncMock(return_value=rec))
        storage = MagicMock()
        storage.exists = AsyncMock(return_value=True)
        storage.load = AsyncMock(return_value=b"private transcript")
        mocker.patch("file_storage.factory.get_storage_backend", return_value=storage)

        token = uuid.uuid4()
        denied = client.get(f"/api/v1/share/{token}/files/transcript_txt?inline=true")
        allowed_subtitle = client.get(f"/api/v1/share/{token}/files/vtt?inline=true")

        assert denied.status_code == 403
        assert allowed_subtitle.status_code == 200
        storage.load.assert_awaited_once()

    def test_s3_share_file_redirects_without_loading_bytes(self, client, mocker) -> None:
        from contextlib import asynccontextmanager

        from file_storage.backends.s3 import S3StorageBackend

        rec = create_mock_recording(record_id=8, processed_video_path="k.mp4")
        rec.owner = MagicMock(user_slug=1)
        mocker.patch("api.routers.share._get_recording_by_share_token", new=AsyncMock(return_value=rec))
        storage = object.__new__(S3StorageBackend)
        storage.presigned_url = AsyncMock(return_value="https://cdn.example/subtitles.vtt")
        storage.exists = AsyncMock()
        storage.load = AsyncMock()

        @asynccontextmanager
        async def shared_operations():
            yield

        storage.shared_operations = shared_operations
        mocker.patch("file_storage.factory.get_storage_backend", return_value=storage)

        response = client.get(f"/api/v1/share/{uuid.uuid4()}/files/vtt?inline=true", follow_redirects=False)

        assert response.status_code == 302
        assert response.headers["location"] == "https://cdn.example/subtitles.vtt"
        storage.presigned_url.assert_awaited_once()
        storage.exists.assert_not_awaited()
        storage.load.assert_not_awaited()

    def test_recording_media_play_200_when_download_off(self, client, mocker) -> None:
        rec = create_mock_recording(record_id=8, processed_video_path="k.mp4", allow_video_download=False)
        rec.local_video_path = None
        mocker.patch("api.routers.share._get_recording_by_share_token", new=AsyncMock(return_value=rec))
        _storage_ok(mocker)
        response = client.get(f"/api/v1/share/{uuid.uuid4()}/media?type=processed")
        assert response.status_code == 200

    def test_video_download_is_tracked_after_successful_presign(self, client, mocker) -> None:
        from contextlib import asynccontextmanager

        rec = create_mock_recording(record_id=8, processed_video_path="k.mp4", allow_video_download=True)
        rec.local_video_path = None
        mocker.patch("api.routers.share._get_recording_by_share_token", new=AsyncMock(return_value=rec))
        events: list[str] = []
        storage = MagicMock()

        @asynccontextmanager
        async def shared_operations():
            yield

        async def presign(*_args, **_kwargs):
            events.append("presign")
            return "https://cdn.example/video.mp4"

        async def track(*_args, **_kwargs):
            events.append("track")

        storage.shared_operations = shared_operations
        storage.presigned_url = AsyncMock(side_effect=presign)
        mocker.patch("file_storage.factory.get_storage_backend", return_value=storage)
        mocker.patch("api.routers.share._track_download_safe", new=AsyncMock(side_effect=track))

        response = client.get(f"/api/v1/share/{uuid.uuid4()}/media?type=processed&download=true")

        assert response.status_code == 200
        assert events == ["presign", "track"]

        events.clear()
        mocker.patch(
            "api.routers.share._public_playlist_item_or_404",
            new=AsyncMock(return_value=(MagicMock(), MagicMock(), rec)),
        )
        playlist_response = client.get(f"/api/v1/share/p/{uuid.uuid4()}/items/11/media?download=true")
        assert playlist_response.status_code == 200
        assert events == ["presign", "track"]

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
        mocker.patch(
            "api.routers.share.PlaylistRepository.get_public_item_by_share_token",
            new=AsyncMock(return_value=(pl, item, rec)),
        )
        response = client.get(f"/api/v1/share/p/{pl.share_token}/items/11/media?type=processed&download=true")
        assert response.status_code == 403

    def test_unavailable_playlist_item_does_not_expose_media(self, client, mocker) -> None:
        rec = create_mock_recording(record_id=8, processed_video_path="k.mp4", deleted=True)
        rec.delete_state = "soft_deleted"
        item = MagicMock(id=11, recording=rec)
        pl = _playlist(enabled=True, token=uuid.uuid4(), items=[item])
        mocker.patch(
            "api.routers.share.PlaylistRepository.get_public_item_by_share_token",
            new=AsyncMock(return_value=(pl, item, rec)),
        )
        response = client.get(f"/api/v1/share/p/{pl.share_token}/items/11?view=player")
        media = client.get(f"/api/v1/share/p/{pl.share_token}/items/11/media")
        files = client.get(f"/api/v1/share/p/{pl.share_token}/items/11/files/vtt?inline=true")
        assert response.status_code == media.status_code == files.status_code == 404

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

    def test_public_playlist_exposes_group_folder_and_membership(self, client, mocker) -> None:
        rec = create_mock_recording(record_id=8, processed_video_path="video.mp4")
        item = MagicMock(id=11, position=0, group_id=5, recording=rec)
        group = MagicMock()
        group.id = 5
        group.name = "Group 1"
        group.position = 0
        pl = _playlist(enabled=True, token=uuid.uuid4(), items=[item])
        pl.groups = [group]
        mocker.patch("api.routers.share._get_enabled_playlist", new=AsyncMock(return_value=pl))
        mocker.patch("api.routers.share.publication_looks_for_recordings", new=AsyncMock(return_value={}))

        response = client.get(f"/api/v1/share/p/{pl.share_token}?view=catalog")

        assert response.status_code == 200
        assert response.json()["channels"] == []
        assert response.json()["groups"] == [{"id": 5, "name": "Group 1", "position": 0, "item_count": 1}]
        assert response.json()["items"][0]["group_id"] == 5

    def test_public_playlist_exposes_only_requested_channel(self, client, mocker) -> None:
        pl = _playlist(enabled=True, token=uuid.uuid4(), items=[])
        mocker.patch("api.routers.share._get_enabled_playlist", new=AsyncMock(return_value=pl))
        channel = PublicChannelLink(slug="course-26", name="Course 26")
        resolve = mocker.patch("api.routers.share._public_channel_for_request", new=AsyncMock(return_value=channel))

        response = client.get(f"/api/v1/share/p/{pl.share_token}?view=catalog&from=course-26")

        assert response.status_code == 200
        assert response.json()["channels"] == [{"slug": "course-26", "name": "Course 26"}]
        assert resolve.await_args.args[1].query_params["from"] == "course-26"

    def test_public_posters_only_resolve_requested_items(self, client, mocker) -> None:
        first = create_mock_recording(record_id=8)
        second = create_mock_recording(record_id=9)
        pl = _playlist(
            enabled=True,
            token=uuid.uuid4(),
            items=[
                MagicMock(id=11, recording_id=8, recording=first),
                MagicMock(id=12, recording_id=9, recording=second),
            ],
        )
        mocker.patch("api.routers.share._get_enabled_playlist", new=AsyncMock(return_value=pl))
        mocker.patch("api.routers.share.publication_looks_for_recordings", new=AsyncMock(return_value={}))
        previews = mocker.patch(
            "api.services.playlist_service.poster_preview_map",
            new=AsyncMock(return_value={8: MagicMock(url="https://cdn.example/8.jpg", asset_key="8.jpg")}),
        )

        response = client.get(f"/api/v1/share/p/{pl.share_token}/posters?item_ids=11")

        assert response.status_code == 200
        assert response.json() == {"11": {"url": "https://cdn.example/8.jpg", "asset_key": "8.jpg"}}
        assert [rec.id for rec in previews.await_args.args[2]] == [8]

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
        mocker.patch(
            "api.routers.share.PlaylistRepository.get_public_item_by_share_token",
            new=AsyncMock(return_value=(pl, item, rec)),
        )
        track = mocker.patch("api.routers.share._track_page_view_safe", new=AsyncMock())
        response = client.post(f"/api/v1/share/p/{pl.share_token}/items/11/beacon")
        assert response.status_code == 204
        track.assert_awaited_once()

    def test_playlist_item_beacon_unknown_still_204(self, client, mocker) -> None:
        mocker.patch(
            "api.routers.share.PlaylistRepository.get_public_item_by_share_token", new=AsyncMock(return_value=None)
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
        mocker.patch(
            "api.routers.share.PlaylistRepository.get_public_item_by_share_token",
            new=AsyncMock(return_value=(pl, item, rec)),
        )
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
        mocker.patch(
            "api.routers.share.PlaylistRepository.get_public_item_by_share_token",
            new=AsyncMock(return_value=(pl, item, rec)),
        )
        track = mocker.patch("api.routers.share._track_page_view_safe", new=AsyncMock())
        response = client.post(f"/api/v1/share/p/{pl.share_token}/items/11/beacon")
        assert response.status_code == 204
        track.assert_not_called()
