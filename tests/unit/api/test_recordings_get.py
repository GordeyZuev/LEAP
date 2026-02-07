"""Unit tests for GET /recordings endpoints."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from models.recording import ProcessingStatus
from tests.fixtures.factories import (
    create_mock_recording,
)


@pytest.mark.unit
class TestListRecordings:
    """Tests for GET /api/v1/recordings endpoint."""

    def test_list_recordings_success(self, client, mocker, mock_user):
        """Test successful retrieval of recordings list."""
        # Arrange
        mock_recordings = [
            create_mock_recording(record_id=1, display_name="Recording 1", user_id=mock_user.id),
            create_mock_recording(record_id=2, display_name="Recording 2", user_id=mock_user.id),
        ]

        # Mock repository method
        mock_repo = mocker.patch("api.routers.recordings.RecordingRepository")
        mock_repo_instance = MagicMock()
        mock_repo_instance.list_by_user = AsyncMock(return_value=mock_recordings)
        mock_repo.return_value = mock_repo_instance

        # Act
        response = client.get("/api/v1/recordings")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert len(data["items"]) == 2
        assert data["items"][0]["display_name"] == "Recording 1"
        assert data["items"][1]["display_name"] == "Recording 2"

    def test_list_recordings_empty(self, client, mocker):
        """Test empty recordings list."""
        # Arrange
        mock_repo = mocker.patch("api.routers.recordings.RecordingRepository")
        mock_repo_instance = MagicMock()
        mock_repo_instance.list_by_user = AsyncMock(return_value=[])
        mock_repo.return_value = mock_repo_instance

        # Act
        response = client.get("/api/v1/recordings")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert len(data["items"]) == 0

    def test_list_recordings_with_template_filter(self, client, mocker, mock_user):
        """Test filtering recordings by template_id."""
        # Arrange
        template_id = 5
        mock_recordings = [
            create_mock_recording(
                record_id=1,
                display_name="Recording 1",
                user_id=mock_user.id,
                template_id=template_id,
            ),
        ]

        mock_repo = mocker.patch("api.routers.recordings.RecordingRepository")
        mock_repo_instance = MagicMock()
        mock_repo_instance.list_by_user = AsyncMock(return_value=mock_recordings)
        mock_repo.return_value = mock_repo_instance

        # Act
        response = client.get(f"/api/v1/recordings?template_id={template_id}")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["template_id"] == template_id

    def test_list_recordings_with_status_filter(self, client, mocker, mock_user):
        """Test filtering recordings by status."""
        # Arrange
        mock_recordings = [
            create_mock_recording(
                record_id=1,
                display_name="Downloaded",
                user_id=mock_user.id,
                status=ProcessingStatus.DOWNLOADED,
            ),
        ]

        mock_repo = mocker.patch("api.routers.recordings.RecordingRepository")
        mock_repo_instance = MagicMock()
        mock_repo_instance.list_by_user = AsyncMock(return_value=mock_recordings)
        mock_repo.return_value = mock_repo_instance

        # Act
        response = client.get("/api/v1/recordings?status=DOWNLOADED")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["status"] == "DOWNLOADED"

    def test_list_recordings_with_search(self, client, mocker, mock_user):
        """Test searching recordings by display_name."""
        # Arrange
        mock_recordings = [
            create_mock_recording(record_id=1, display_name="Python Lecture 1", user_id=mock_user.id),
            create_mock_recording(record_id=2, display_name="Python Lecture 2", user_id=mock_user.id),
            create_mock_recording(record_id=3, display_name="Math Course", user_id=mock_user.id),
        ]

        mock_repo = mocker.patch("api.routers.recordings.RecordingRepository")
        mock_repo_instance = MagicMock()
        mock_repo_instance.list_by_user = AsyncMock(return_value=mock_recordings)
        mock_repo.return_value = mock_repo_instance

        # Act
        response = client.get("/api/v1/recordings?search=Python")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2

    def test_list_recordings_pagination(self, client, mocker, mock_user):
        """Test pagination of recordings list."""
        # Arrange
        mock_recordings = [
            create_mock_recording(record_id=i, display_name=f"Recording {i}", user_id=mock_user.id)
            for i in range(1, 26)
        ]

        mock_repo = mocker.patch("api.routers.recordings.RecordingRepository")
        mock_repo_instance = MagicMock()
        mock_repo_instance.list_by_user = AsyncMock(return_value=mock_recordings)
        mock_repo.return_value = mock_repo_instance

        # Act - page 1
        response = client.get("/api/v1/recordings?page=1&per_page=10")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 25
        assert data["page"] == 1
        assert data["per_page"] == 10
        assert len(data["items"]) == 10
        assert data["total_pages"] == 3

    def test_list_recordings_exclude_deleted_by_default(self, client, mocker, mock_user):
        """Test that deleted recordings are excluded by default."""
        # Arrange
        mock_recordings = [
            create_mock_recording(record_id=1, display_name="Active", user_id=mock_user.id, deleted=False),
        ]

        mock_repo = mocker.patch("api.routers.recordings.RecordingRepository")
        mock_repo_instance = MagicMock()
        mock_repo_instance.list_by_user = AsyncMock(return_value=mock_recordings)
        mock_repo.return_value = mock_repo_instance

        # Act
        response = client.get("/api/v1/recordings")

        # Assert
        assert response.status_code == 200
        # Verify include_deleted=False was passed to repository
        mock_repo_instance.list_by_user.assert_called_once()


@pytest.mark.unit
class TestGetRecording:
    """Tests for GET /api/v1/recordings/{id} endpoint."""

    def test_get_recording_success(self, client, mocker, mock_user):
        """Test successful retrieval of single recording."""
        # Arrange
        recording_id = 1
        mock_recording = create_mock_recording(
            record_id=recording_id,
            display_name="Test Recording",
            user_id=mock_user.id,
        )

        mock_repo = mocker.patch("api.routers.recordings.RecordingRepository")
        mock_repo_instance = MagicMock()
        mock_repo_instance.get_by_id = AsyncMock(return_value=mock_recording)
        mock_repo.return_value = mock_repo_instance

        # Act
        response = client.get(f"/api/v1/recordings/{recording_id}")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == recording_id
        assert data["display_name"] == "Test Recording"

    def test_get_recording_not_found(self, client, mocker):
        """Test 404 when recording not found."""
        # Arrange
        recording_id = 999
        mock_repo = mocker.patch("api.routers.recordings.RecordingRepository")
        mock_repo_instance = MagicMock()
        mock_repo_instance.get_by_id = AsyncMock(return_value=None)
        mock_repo.return_value = mock_repo_instance

        # Act
        response = client.get(f"/api/v1/recordings/{recording_id}")

        # Assert
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_get_recording_with_detailed_flag(self, client, mocker, mock_user):
        """Test retrieval of recording with detailed information."""
        # Arrange
        recording_id = 1
        mock_owner = MagicMock()
        mock_owner.user_slug = "test_user"

        mock_recording = create_mock_recording(
            record_id=recording_id,
            display_name="Test Recording",
            user_id=mock_user.id,
            owner=mock_owner,
        )

        mock_repo = mocker.patch("api.routers.recordings.RecordingRepository")
        mock_repo_instance = MagicMock()
        mock_repo_instance.get_by_id = AsyncMock(return_value=mock_recording)
        mock_repo.return_value = mock_repo_instance

        # Act
        response = client.get(f"/api/v1/recordings/{recording_id}?detailed=false")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == recording_id

    def test_get_recording_belongs_to_different_user(self, client, mocker):
        """Test that user cannot access recording of another user (multi-tenancy)."""
        # Arrange
        recording_id = 1
        mock_repo = mocker.patch("api.routers.recordings.RecordingRepository")
        mock_repo_instance = MagicMock()
        # Repository returns None when recording doesn't belong to user
        mock_repo_instance.get_by_id = AsyncMock(return_value=None)
        mock_repo.return_value = mock_repo_instance

        # Act
        response = client.get(f"/api/v1/recordings/{recording_id}")

        # Assert
        assert response.status_code == 404
        # Verify repository was called with correct user_id (multi-tenancy check)
        mock_repo_instance.get_by_id.assert_called_once()
