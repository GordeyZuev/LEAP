"""Contract tests for v0.10.9.1 latency endpoints (compact list, pipeline-status, share player view)."""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

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


def _patch_list_deps(mocker, recordings: list) -> None:
    mock_repo = mocker.patch("api.routers.recordings.RecordingRepository")
    mock_repo.return_value.list_filtered = AsyncMock(return_value=(recordings, len(recordings)))
    mocker.patch("api.routers.recordings._poster_urls", new=AsyncMock(return_value={}))


@pytest.mark.unit
class TestListRecordingsCompact:
    def test_compact_true_omits_processing_stages(self, client, mocker, mock_user) -> None:
        rec = create_mock_recording(
            record_id=1,
            user_id=mock_user.id,
            processing_stages=[_mock_stage()],
        )
        _patch_list_deps(mocker, [rec])

        full = client.get("/api/v1/recordings")
        compact = client.get("/api/v1/recordings?compact=true")

        assert full.status_code == 200
        assert compact.status_code == 200
        assert len(full.json()["items"][0]["processing_stages"]) == 1
        assert compact.json()["items"][0]["processing_stages"] == []


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

    def test_playlist_item_passes_player_view(self, client, mocker) -> None:
        rec = create_mock_recording(record_id=8, processed_video_path="k.mp4")
        item = MagicMock()
        item.id = 11
        item.recording = rec
        pl = MagicMock()
        pl.items = [item]
        mocker.patch("api.routers.share._get_enabled_playlist", new=AsyncMock(return_value=pl))
        build = mocker.patch(
            "api.routers.share._build_public_recording_response",
            new=AsyncMock(return_value=_player_response()),
        )

        response = client.get(f"/api/v1/share/p/{uuid.uuid4()}/items/11?view=player")

        assert response.status_code == 200
        assert response.json()["play_url"]
        build.assert_awaited_once()
        assert build.await_args.kwargs["view"] == "player"

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
        mocker.patch("transcription_module.manager.get_transcription_manager", return_value=tx)
        mocker.patch("api.helpers.source_extras.list_source_extras", new=AsyncMock(return_value=None))

        response = client.get(f"/api/v1/share/{uuid.uuid4()}?view=player")

        assert response.status_code == 200
        body = response.json()
        assert body["play_url"] == "https://cdn.example/video.mp4"
        assert body["vtt_url"] == "https://cdn.example/sub.vtt"
        assert storage.presigned_url.await_count >= 2
