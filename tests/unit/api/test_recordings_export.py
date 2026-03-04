"""Unit tests for POST /api/v1/recordings/export endpoint."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from models.recording import ProcessingStatus, TargetStatus, TargetType
from tests.fixtures.factories import (
    create_mock_output_target,
    create_mock_recording,
    create_mock_template,
)


@pytest.mark.unit
class TestExportRecordings:
    """Tests for POST /api/v1/recordings/export endpoint."""

    def test_export_json_with_recording_ids(self, client, mocker, mock_user):
        """Export to JSON using explicit recording_ids, short verbosity."""
        mock_template = create_mock_template(template_id=5, name="ML Course")
        mock_recording = create_mock_recording(
            record_id=1,
            display_name="Lecture 1",
            user_id=mock_user.id,
            status=ProcessingStatus.READY,
            template=mock_template,
            template_id=5,
            main_topics=["ML", "Neural Networks"],
        )

        mock_repo = mocker.patch("api.routers.recordings.RecordingRepository")
        mock_repo_instance = MagicMock()
        mock_repo_instance.get_by_ids = AsyncMock(return_value={1: mock_recording})
        mock_repo.return_value = mock_repo_instance

        response = client.post(
            "/api/v1/recordings/export",
            json={
                "recording_ids": [1],
                "format": "json",
                "verbosity": "short",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert len(data["items"]) == 1
        item = data["items"][0]
        assert item["id"] == 1
        assert item["display_name"] == "Lecture 1"
        assert item["status"] == "READY"
        assert item["main_topics"] == ["ML", "Neural Networks"]
        mock_repo_instance.get_by_ids.assert_called_once_with([1], mock_user.id, include_deleted=False)

    def test_export_csv_with_platform_urls(self, client, mocker, mock_user):
        """Export to CSV includes platform URLs when outputs present."""
        youtube_output = create_mock_output_target(
            target_type=TargetType.YOUTUBE,
            status=TargetStatus.UPLOADED,
            target_meta={"video_url": "https://youtube.com/watch?v=abc"},
        )
        mock_recording = create_mock_recording(
            record_id=2,
            display_name="Lecture 2",
            user_id=mock_user.id,
            outputs=[youtube_output],
        )

        mock_repo = mocker.patch("api.routers.recordings.RecordingRepository")
        mock_repo_instance = MagicMock()
        mock_repo_instance.get_by_ids = AsyncMock(return_value={2: mock_recording})
        mock_repo.return_value = mock_repo_instance

        response = client.post(
            "/api/v1/recordings/export",
            json={
                "recording_ids": [2],
                "format": "csv",
                "verbosity": "short",
            },
        )

        assert response.status_code == 200
        assert response.headers["content-type"] == "text/csv; charset=utf-8"
        assert "attachment" in response.headers["content-disposition"]
        assert ".csv" in response.headers["content-disposition"]
        content = response.content.decode("utf-8")
        assert "id" in content
        assert "youtube_url" in content
        assert "Lecture 2" in content
        assert "https://youtube.com/watch?v=abc" in content

    def test_export_validation_requires_ids_or_filters(self, client):
        """Export fails when neither recording_ids nor filters provided."""
        response = client.post(
            "/api/v1/recordings/export",
            json={"format": "json"},
        )
        assert response.status_code == 422

    def test_export_validation_rejects_both_ids_and_filters(self, client):
        """Export fails when both recording_ids and filters provided."""
        response = client.post(
            "/api/v1/recordings/export",
            json={
                "recording_ids": [1],
                "filters": {"template_id": 5},
                "format": "json",
            },
        )
        assert response.status_code == 422

    def test_export_with_filters_uses_get_filtered_ids(self, client, mocker, mock_user):
        """Export with filters calls get_filtered_ids and respects user_id."""
        mock_recording = create_mock_recording(
            record_id=3,
            display_name="Filtered Recording",
            user_id=mock_user.id,
        )

        mock_repo = mocker.patch("api.routers.recordings.RecordingRepository")
        mock_repo_instance = MagicMock()
        mock_repo_instance.get_filtered_ids = AsyncMock(return_value=[3])
        mock_repo_instance.get_by_ids = AsyncMock(return_value={3: mock_recording})
        mock_repo.return_value = mock_repo_instance

        response = client.post(
            "/api/v1/recordings/export",
            json={
                "filters": {"template_id": 5, "status": ["READY"]},
                "limit": 100,
                "format": "json",
                "verbosity": "short",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        mock_repo_instance.get_filtered_ids.assert_called_once()
        mock_repo_instance.get_by_ids.assert_called_once_with([3], mock_user.id, include_deleted=False)

    def test_export_xlsx_returns_binary(self, client, mocker, mock_user):
        """Export to XLSX returns downloadable file."""
        mock_recording = create_mock_recording(
            record_id=4,
            display_name="Lecture 4",
            user_id=mock_user.id,
        )

        mock_repo = mocker.patch("api.routers.recordings.RecordingRepository")
        mock_repo_instance = MagicMock()
        mock_repo_instance.get_by_ids = AsyncMock(return_value={4: mock_recording})
        mock_repo.return_value = mock_repo_instance

        response = client.post(
            "/api/v1/recordings/export",
            json={
                "recording_ids": [4],
                "format": "xlsx",
                "verbosity": "long",
            },
        )

        assert response.status_code == 200
        assert "spreadsheet" in response.headers["content-type"]
        assert "attachment" in response.headers["content-disposition"]
        assert ".xlsx" in response.headers["content-disposition"]
        # openpyxl creates valid XLSX (PK header)
        assert response.content[:4] == b"PK\x03\x04"
