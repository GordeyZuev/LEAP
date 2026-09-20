"""Contract tests for v0.10.9.1 latency endpoints (compact list, pipeline-status, share player view)."""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import Response

from api.schemas.playlist import PublicChannelLink
from api.schemas.share import PublicRecordingResponse
from models.recording import ProcessingStatus
from tests.fixtures.factories import create_mock_recording


def _mock_stage() -> MagicMock:
    stage = MagicMock()
    stage.stage_type.value = "TRANSCRIBE"
    stage.status.value = "COMPLETED"
    stage.failed = False
    stage.failed_at = None
    stage.failed_reason = None
    stage.retry_count = 0
    stage.started_at = None
    stage.completed_at = None
    return stage


def _patch_list_deps(mocker, recordings: list) -> AsyncMock:
    mock_repo = mocker.patch("api.routers.recordings.RecordingRepository")
    mock_repo.return_value.list_filtered = AsyncMock(return_value=(recordings, len(recordings)))
    mocker.patch("api.routers.recordings._poster_urls", new=AsyncMock(return_value={}))
    return mock_repo.return_value.list_filtered


@pytest.mark.unit
class TestListRecordingsCompact:
    def test_compact_true_omits_processing_stages(self, client, mocker, mock_user) -> None:
        rec = create_mock_recording(
            record_id=1,
            user_id=mock_user.id,
            processing_stages=[_mock_stage()],
        )
        list_filtered = _patch_list_deps(mocker, [rec])

        full = client.get("/api/v1/recordings")
        compact = client.get("/api/v1/recordings?compact=true")

        assert full.status_code == 200
        assert compact.status_code == 200
        assert len(full.json()["items"][0]["processing_stages"]) == 1
        assert compact.json()["items"][0]["processing_stages"] == []
        assert list_filtered.await_args_list[0].kwargs["include_processing_stages"] is True
        assert list_filtered.await_args_list[1].kwargs["include_processing_stages"] is False


@pytest.mark.unit
class TestRecordingPipelineStatus:
    def test_pipeline_status_returns_stages_without_detailed_payload(self, client, mocker, mock_user) -> None:
        rec = create_mock_recording(
            record_id=5,
            user_id=mock_user.id,
            on_air=True,
            processing_stages=[_mock_stage()],
        )
        mocker.patch("api.routers.recordings.RecordingRepository").return_value.get_by_id = AsyncMock(return_value=rec)

        response = client.get("/api/v1/recordings/5/pipeline-status")

        assert response.status_code == 200
        body = response.json()
        assert body["id"] == 5
        assert body["on_air"] is True
        assert len(body["processing_stages"]) == 1
        assert body["processing_stages"][0]["stage_type"] == "TRANSCRIBE"
        assert "display_name" not in body
        assert "uploads" not in body

    def test_pipeline_status_404_when_not_owned(self, client, mocker) -> None:
        mocker.patch("api.routers.recordings.RecordingRepository").return_value.get_by_id = AsyncMock(return_value=None)
        response = client.get("/api/v1/recordings/99/pipeline-status")
        assert response.status_code == 404


def _player_response() -> PublicRecordingResponse:
    return PublicRecordingResponse(
        id=8,
        display_name="Lecture",
        title="Lecture",
        duration=120.0,
        start_time=datetime.now(UTC),
        status=ProcessingStatus.READY,
        available_files=["vtt"],
        has_processed_video=True,
        has_original_video=False,
        play_url="https://cdn.example/video.mp4",
        vtt_url="https://cdn.example/sub.vtt",
        media_expires_in=3600,
    )


@pytest.mark.unit
class TestSharePlayerView:
    def test_public_recording_passes_player_view(self, client, mocker) -> None:
        rec = create_mock_recording(record_id=8, processed_video_path="k.mp4")
        mocker.patch("api.routers.share._get_recording_by_share_token", new=AsyncMock(return_value=rec))
        build = mocker.patch(
            "api.routers.share._build_public_recording_response",
            new=AsyncMock(return_value=_player_response()),
        )

        response = client.get(f"/api/v1/share/{uuid.uuid4()}?view=player")

        assert response.status_code == 200
        body = response.json()
        assert body["play_url"] == "https://cdn.example/video.mp4"
        assert body["vtt_url"] == "https://cdn.example/sub.vtt"
        build.assert_awaited_once()
        assert build.await_args.kwargs["view"] == "player"

    def test_public_recording_passes_only_context_channel(self, client, mocker) -> None:
        rec = create_mock_recording(record_id=8, processed_video_path="k.mp4")
        mocker.patch("api.routers.share._get_recording_by_share_token", new=AsyncMock(return_value=rec))
        channel = PublicChannelLink(slug="course-26", name="Course 26")
        resolve = mocker.patch("api.routers.share._public_channel_for_request", new=AsyncMock(return_value=channel))
        build = mocker.patch(
            "api.routers.share._build_public_recording_response",
            new=AsyncMock(return_value=_player_response()),
        )

        response = client.get(f"/api/v1/share/{uuid.uuid4()}?view=player&from=course-26")

        assert response.status_code == 200
        assert resolve.await_args.args[1].query_params["from"] == "course-26"
        assert build.await_args.kwargs["navigation_channel"] == channel

    def test_playlist_item_passes_player_view(self, client, mocker) -> None:
        rec = create_mock_recording(record_id=8, processed_video_path="k.mp4")
        item = MagicMock()
        item.id = 11
        item.recording = rec
        pl = MagicMock()
        pl.items = [item]
        mocker.patch(
            "api.routers.share.PlaylistRepository.get_public_item_by_share_token",
            new=AsyncMock(return_value=(pl, item, rec)),
        )
        build = mocker.patch(
            "api.routers.share._build_public_recording_response",
            new=AsyncMock(return_value=_player_response()),
        )

        response = client.get(f"/api/v1/share/p/{uuid.uuid4()}/items/11?view=player")

        assert response.status_code == 200
        assert response.json()["play_url"]
        build.assert_awaited_once()
        assert build.await_args.kwargs["view"] == "player"
        assert build.await_args.kwargs["include_original"] is True

    def test_playlist_landing_beacon_uses_scalar_surface_lookup(self, client, mocker) -> None:
        lookup = mocker.patch(
            "api.routers.share.PlaylistRepository.get_public_surface_by_share_token",
            new=AsyncMock(return_value=(7, "owner")),
        )
        full_lookup = mocker.patch("api.routers.share._get_enabled_playlist", new=AsyncMock())
        track = mocker.patch("api.routers.share._observability.record_surface_view", new=AsyncMock())

        response = client.post(f"/api/v1/share/p/{uuid.uuid4()}/beacon")

        assert response.status_code == 204
        lookup.assert_awaited_once()
        full_lookup.assert_not_awaited()
        assert track.await_args.kwargs["owner_user_id"] == "owner"
        assert track.await_args.kwargs["playlist_id"] == 7

    def test_playlist_landing_engagement_uses_scalar_surface_lookup(self, client, mocker) -> None:
        lookup = mocker.patch(
            "api.routers.share.PlaylistRepository.get_public_surface_by_share_token",
            new=AsyncMock(return_value=(7, "owner")),
        )
        full_lookup = mocker.patch("api.routers.share._get_enabled_playlist", new=AsyncMock())
        mocker.patch("api.routers.share._channel_id_for_request", new=AsyncMock(return_value=None))
        respond = mocker.patch(
            "api.routers.share._respond_engagement", new=AsyncMock(return_value=Response(status_code=204))
        )

        response = client.post(f"/api/v1/share/p/{uuid.uuid4()}/engagement", json={})

        assert response.status_code == 204
        lookup.assert_awaited_once()
        full_lookup.assert_not_awaited()
        context = respond.await_args.args[1]
        assert context.owner_user_id == "owner"
        assert context.playlist_id == 7

    def test_revoked_playlist_landing_events_return_204_without_tracking(self, client, mocker) -> None:
        mocker.patch(
            "api.routers.share.PlaylistRepository.get_public_surface_by_share_token",
            new=AsyncMock(return_value=None),
        )
        track = mocker.patch("api.routers.share._observability.record_surface_view", new=AsyncMock())
        respond = mocker.patch("api.routers.share._respond_engagement", new=AsyncMock())
        token = uuid.uuid4()

        assert client.post(f"/api/v1/share/p/{token}/beacon").status_code == 204
        assert client.post(f"/api/v1/share/p/{token}/engagement", json={}).status_code == 204
        track.assert_not_awaited()
        respond.assert_not_awaited()

    def test_player_view_includes_presigned_media_without_separate_media_route(self, client, mocker) -> None:
        """Player payload must carry play_url so clients skip GET .../media on the hot path."""
        rec = create_mock_recording(record_id=8, processed_video_path="users/u/8/video.mp4")
        rec.owner = MagicMock(user_slug=1)
        rec.deleted = False
        rec.delete_state = "active"
        rec.topic_timestamps = [{"topic": "Intro", "start": 0}]
        rec.main_topics = ["Intro"]

        mocker.patch("api.routers.share._get_recording_by_share_token", new=AsyncMock(return_value=rec))

        storage = MagicMock()

        @asynccontextmanager
        async def _shared():
            yield

        storage.shared_operations = _shared
        storage.exists = AsyncMock(return_value=False)

        async def _presign(path: str, **_kwargs: object) -> str:
            if "video" in path:
                return "https://cdn.example/video.mp4"
            return "https://cdn.example/sub.vtt"

        storage.presigned_url = AsyncMock(side_effect=_presign)
        mocker.patch("file_storage.factory.get_storage_backend", return_value=storage)
        mocker.patch(
            "api.helpers.leap_publication.publication_looks_for_recordings",
            new=AsyncMock(return_value={8: MagicMock(title="T", description_template=None, thumbnail_name=None)}),
        )
        tx = MagicMock()
        tx.has_extracted = AsyncMock(return_value=False)
        tx.get_active_extracted = AsyncMock(return_value=None)
        mocker.patch("transcription_module.manager.get_transcription_manager", return_value=tx)
        mocker.patch("api.helpers.source_extras.list_source_extras", new=AsyncMock(return_value=None))

        response = client.get(f"/api/v1/share/{uuid.uuid4()}?view=player")

        assert response.status_code == 200
        body = response.json()
        assert body["play_url"] == "https://cdn.example/video.mp4"
        assert body["vtt_url"] == "https://cdn.example/sub.vtt"
        assert body["channels"] == []
        assert "playlists" not in body
        assert storage.presigned_url.await_count >= 2
        tx.has_extracted.assert_not_awaited()
        tx.get_active_extracted.assert_awaited_once()

    def test_player_view_loads_summary_and_questions_from_extracted(self, client, mocker) -> None:
        rec = create_mock_recording(record_id=8, processed_video_path="users/u/8/video.mp4")
        rec.owner = MagicMock(user_slug=1)
        rec.deleted = False
        rec.delete_state = "active"
        rec.topic_timestamps = [{"topic": "Intro", "start": 0}]
        rec.main_topics = ["Intro"]
        rec.allow_files_download = False
        rec.allow_video_download = True

        mocker.patch("api.routers.share._get_recording_by_share_token", new=AsyncMock(return_value=rec))
        storage = MagicMock()

        @asynccontextmanager
        async def _shared():
            yield

        storage.shared_operations = _shared
        storage.exists = AsyncMock(return_value=False)
        storage.presigned_url = AsyncMock(return_value="https://cdn.example/video.mp4")
        mocker.patch("file_storage.factory.get_storage_backend", return_value=storage)
        mocker.patch(
            "api.helpers.leap_publication.publication_looks_for_recordings",
            new=AsyncMock(return_value={8: MagicMock(title="T", description_template=None, thumbnail_name=None)}),
        )
        tx = MagicMock()
        tx.has_extracted = AsyncMock(return_value=True)
        tx.get_active_extracted = AsyncMock(
            return_value={"summary": "A lecture summary.", "questions": ["What is a tree?"]}
        )
        mocker.patch("transcription_module.manager.get_transcription_manager", return_value=tx)

        response = client.get(f"/api/v1/share/{uuid.uuid4()}?view=player")

        assert response.status_code == 200
        body = response.json()
        assert body["summary"] == "A lecture summary."
        assert body["questions"] == ["What is a tree?"]
        tx.has_extracted.assert_not_awaited()
        tx.get_active_extracted.assert_awaited_once()


@pytest.mark.unit
class TestSharePlaylistCatalogView:
    def test_catalog_view_skips_poster_presign(self, client, mocker) -> None:
        rec = create_mock_recording(record_id=3, user_id="u1")
        item = MagicMock()
        item.id = 1
        item.position = 0
        item.recording = rec
        item.created_at = datetime.now(UTC)
        pl = MagicMock()
        pl.name = "Course"
        pl.description = None
        pl.items = [item]
        pl.user_id = "u1"
        mocker.patch("api.routers.share._get_enabled_playlist", new=AsyncMock(return_value=pl))
        mocker.patch(
            "api.helpers.leap_publication.publication_looks_for_recordings",
            new=AsyncMock(return_value={3: MagicMock(title="T", description_template=None, thumbnail_name=None)}),
        )
        poster_map = mocker.patch("api.services.playlist_service.poster_preview_map", new=AsyncMock())

        response = client.get(f"/api/v1/share/p/{uuid.uuid4()}?view=catalog")

        assert response.status_code == 200
        body = response.json()
        assert body["items"][0]["poster_url"] is None
        poster_map.assert_not_awaited()

    def test_catalog_hides_corrupt_cross_tenant_item(self, client, mocker) -> None:
        foreign = create_mock_recording(record_id=4, user_id="another_user")
        foreign.display_name = "Private title"
        item = MagicMock(id=7, position=0, group_id=None, recording=foreign, created_at=datetime.now(UTC))
        playlist = MagicMock()
        playlist.name = "Course"
        playlist.description = "{{ items }}"
        playlist.items = [item]
        playlist.groups = []
        playlist.user_id = "owner"
        mocker.patch("api.routers.share._get_enabled_playlist", new=AsyncMock(return_value=playlist))
        response = client.get(f"/api/v1/share/p/{uuid.uuid4()}?view=catalog")

        assert response.status_code == 200
        body = response.json()
        assert "Private title" not in body["description"]
        assert body["items"][0]["title"] == "Unknown"
        assert body["items"][0]["playable"] is False
        posters = client.get(f"/api/v1/share/p/{uuid.uuid4()}/posters?item_ids=7")
        assert posters.status_code == 200
        assert posters.json() == {}

    def test_share_artifact_files_cache_skips_exists(self, client, mocker) -> None:
        rec = create_mock_recording(record_id=8, processed_video_path="users/u/8/video.mp4")
        rec.owner = MagicMock(user_slug=1)
        rec.deleted = False
        rec.delete_state = "active"
        rec.topic_timestamps = [{"topic": "Intro", "start": 0}]
        rec.main_topics = ["Intro"]
        rec.share_artifact_files = ["vtt", "srt"]
        rec.allow_files_download = False

        mocker.patch("api.routers.share._get_recording_by_share_token", new=AsyncMock(return_value=rec))
        storage = MagicMock()

        @asynccontextmanager
        async def _shared():
            yield

        storage.shared_operations = _shared
        storage.exists = AsyncMock(return_value=True)
        storage.presigned_url = AsyncMock(return_value="https://cdn.example/video.mp4")
        mocker.patch("file_storage.factory.get_storage_backend", return_value=storage)
        mocker.patch(
            "api.helpers.leap_publication.publication_looks_for_recordings",
            new=AsyncMock(return_value={8: MagicMock(title="T", description_template=None, thumbnail_name=None)}),
        )
        tx = MagicMock()
        tx.has_extracted = AsyncMock(return_value=False)
        tx.get_active_extracted = AsyncMock(return_value=None)
        mocker.patch("transcription_module.manager.get_transcription_manager", return_value=tx)

        response = client.get(f"/api/v1/share/{uuid.uuid4()}?view=player")

        assert response.status_code == 200
        assert response.json()["available_files"] == ["vtt", "srt"]
        storage.exists.assert_not_awaited()

    def test_player_view_includes_original_play_url_when_source_exists(self, client, mocker) -> None:
        rec = create_mock_recording(
            record_id=8,
            processed_video_path="users/u/8/video.mp4",
            local_video_path="users/u/8/source.mp4",
        )
        rec.owner = MagicMock(user_slug=1)
        rec.deleted = False
        rec.delete_state = "active"
        rec.topic_timestamps = [{"topic": "Intro", "start": 0}]
        rec.allow_files_download = False

        mocker.patch("api.routers.share._get_recording_by_share_token", new=AsyncMock(return_value=rec))
        storage = MagicMock()

        @asynccontextmanager
        async def _shared():
            yield

        storage.shared_operations = _shared
        storage.presigned_url = AsyncMock(side_effect=lambda path, **_kw: f"https://cdn.example/{path.split('/')[-1]}")
        mocker.patch("file_storage.factory.get_storage_backend", return_value=storage)
        mocker.patch(
            "api.helpers.leap_publication.publication_looks_for_recordings",
            new=AsyncMock(return_value={8: MagicMock(title="T", description_template=None, thumbnail_name=None)}),
        )
        mocker.patch(
            "api.helpers.share_artifacts.resolve_share_available_files",
            new=AsyncMock(return_value=[]),
        )

        response = client.get(f"/api/v1/share/{uuid.uuid4()}?view=player")

        assert response.status_code == 200
        body = response.json()
        assert body["has_original_video"] is True
        assert body["original_play_url"] is not None
        assert "source.mp4" in body["original_play_url"]

    def test_player_view_hides_original_when_source_key_matches_processed(self, client, mocker) -> None:
        rec = create_mock_recording(
            record_id=8,
            processed_video_path="users/u/8/video.mp4",
            local_video_path="users/u/8/video.mp4",
        )
        rec.owner = MagicMock(user_slug=1)
        rec.deleted = False
        rec.delete_state = "active"
        rec.topic_timestamps = [{"topic": "Intro", "start": 0}]
        rec.allow_files_download = False

        mocker.patch("api.routers.share._get_recording_by_share_token", new=AsyncMock(return_value=rec))
        storage = MagicMock()

        @asynccontextmanager
        async def _shared():
            yield

        storage.shared_operations = _shared
        storage.presigned_url = AsyncMock(side_effect=lambda path, **_kw: f"https://cdn.example/{path.split('/')[-1]}")
        mocker.patch("file_storage.factory.get_storage_backend", return_value=storage)
        mocker.patch(
            "api.helpers.leap_publication.publication_looks_for_recordings",
            new=AsyncMock(return_value={8: MagicMock(title="T", description_template=None, thumbnail_name=None)}),
        )
        mocker.patch(
            "api.helpers.share_artifacts.resolve_share_available_files",
            new=AsyncMock(return_value=[]),
        )

        response = client.get(f"/api/v1/share/{uuid.uuid4()}?view=player")

        assert response.status_code == 200
        body = response.json()
        assert body["has_original_video"] is False
        assert body["original_play_url"] is None
        assert storage.presigned_url.await_count == 2
