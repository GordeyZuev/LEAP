"""MTS Link pipeline entry: /run prepare, /download blocked."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from models.recording import ProcessingStatus, SourceType
from tests.fixtures.factories import create_mock_recording


def _mts_recording(**kwargs):
    recording = create_mock_recording(
        status=ProcessingStatus.INITIALIZED,
        is_mapped=True,
        **kwargs,
    )
    source = MagicMock()
    source.source_type = SourceType.MTS_LINK
    source.meta = {"mts_record_id": 1, "event_session_id": 2, "needs_mp4": True}
    recording.source = source
    return recording


@pytest.mark.unit
class TestMtsLinkDownloadBlocked:
    def test_download_mts_link_returns_400(self, client, mocker, mock_user):
        recording = _mts_recording(record_id=1, user_id=mock_user.id)

        mock_repo = mocker.patch("api.routers.recordings.RecordingRepository")
        mock_repo_instance = MagicMock()
        mock_repo_instance.get_by_id = AsyncMock(return_value=recording)
        mock_repo.return_value = mock_repo_instance

        response = client.post("/api/v1/recordings/1/download")

        assert response.status_code == 400
        assert "POST /run" in response.json()["detail"]


@pytest.mark.unit
class TestMtsLinkBulkDownloadBlocked:
    def test_bulk_download_skips_mts_link(self, client, mocker, mock_user):
        recording = _mts_recording(record_id=1, user_id=mock_user.id)

        mock_repo = mocker.patch("api.routers.recordings.RecordingRepository")
        mock_repo_instance = MagicMock()
        mock_repo_instance.get_by_ids = AsyncMock(return_value={1: recording})
        mock_repo.return_value = mock_repo_instance

        mocker.patch(
            "api.routers.recordings._resolve_recording_ids",
            AsyncMock(return_value=[1]),
        )
        mock_delay = mocker.patch("api.tasks.processing.download_recording_task")

        response = client.post("/api/v1/recordings/bulk/download", json={"recording_ids": [1]})

        assert response.status_code == 200
        task = response.json()["tasks"][0]
        assert task["status"] == "skipped"
        assert "POST /run" in task["error"]
        mock_delay.delay.assert_not_called()
