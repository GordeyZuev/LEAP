"""Unit tests for PATCH /api/v1/users/me."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from api.schemas.auth import UserInDB


def _user_in_db(**overrides) -> UserInDB:
    base = {
        "id": "user_123",
        "user_slug": 1,
        "email": "test@example.com",
        "hashed_password": "hashed",
        "full_name": "Test User",
        "timezone": "Europe/Moscow",
        "is_active": True,
        "is_verified": True,
        "role": "user",
        "can_transcribe": True,
        "can_process_video": True,
        "can_upload": True,
        "can_create_templates": True,
        "can_delete_recordings": True,
        "can_update_uploaded_videos": True,
        "can_manage_credentials": True,
        "can_export_data": True,
        "created_at": datetime(2026, 1, 1, tzinfo=UTC),
        "updated_at": datetime(2026, 4, 12, 12, 0, 0, tzinfo=UTC),
        "last_login_at": datetime(2026, 4, 12, 10, 0, 0, tzinfo=UTC),
    }
    base.update(overrides)
    return UserInDB.model_validate(base)


@pytest.mark.unit
class TestPatchCurrentUserProfile:
    """Tests for PATCH /api/v1/users/me."""

    def test_patch_timezone_persists_in_response(self, client, mocker, mock_user):
        """Timezone in body is passed to repository and returned in response."""
        mock_instance = MagicMock()
        mock_instance.get_by_email = AsyncMock(return_value=None)
        mock_instance.update = AsyncMock(return_value=_user_in_db())

        mocker.patch("api.routers.users.UserRepository", return_value=mock_instance)

        response = client.patch("/api/v1/users/me", json={"timezone": "Europe/Moscow"})

        assert response.status_code == 200
        data = response.json()
        assert data["timezone"] == "Europe/Moscow"
        mock_instance.update.assert_awaited_once()
        call_args = mock_instance.update.await_args
        assert call_args[0][0] == mock_user.id
        assert call_args[0][1].timezone == "Europe/Moscow"

    def test_patch_invalid_timezone_returns_422(self, client, mocker):
        """Unknown IANA id is rejected before DB access."""
        mock_repo = mocker.patch("api.routers.users.UserRepository")
        response = client.patch("/api/v1/users/me", json={"timezone": "Not/AZone"})

        assert response.status_code == 422
        mock_repo.assert_not_called()

    def test_patch_empty_timezone_string_returns_422(self, client, mocker):
        mock_repo = mocker.patch("api.routers.users.UserRepository")
        response = client.patch("/api/v1/users/me", json={"timezone": "   "})

        assert response.status_code == 422
        mock_repo.assert_not_called()
