"""Unit tests for GET /credentials endpoints."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from tests.fixtures.factories import create_mock_credential


@pytest.mark.unit
class TestListCredentials:
    """Tests for GET /api/v1/credentials/ endpoint."""

    def test_list_credentials_success(self, client, mocker, mock_user):  # noqa: ARG002
        """Test successful retrieval of credentials list."""
        # Arrange
        mock_cred1 = MagicMock()
        mock_cred1.id = 1
        mock_cred1.platform = "youtube"
        mock_cred1.account_name = "test@example.com"
        mock_cred1.is_active = True
        mock_cred1.last_used_at = None

        mock_cred2 = MagicMock()
        mock_cred2.id = 2
        mock_cred2.platform = "vk"
        mock_cred2.account_name = "vk_user"
        mock_cred2.is_active = True
        mock_cred2.last_used_at = None

        mock_credentials = [mock_cred1, mock_cred2]

        mock_repo = mocker.patch("api.routers.credentials.UserCredentialRepository")
        mock_repo_instance = MagicMock()
        mock_repo_instance.find_by_user = AsyncMock(return_value=mock_credentials)
        mock_repo.return_value = mock_repo_instance

        # Act
        response = client.get("/api/v1/credentials/")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["platform"] == "youtube"
        assert data[1]["platform"] == "vk"

    def test_list_credentials_empty(self, client, mocker):
        """Test empty credentials list."""
        # Arrange
        mock_repo = mocker.patch("api.routers.credentials.UserCredentialRepository")
        mock_repo_instance = MagicMock()
        mock_repo_instance.find_by_user = AsyncMock(return_value=[])
        mock_repo.return_value = mock_repo_instance

        # Act
        response = client.get("/api/v1/credentials/")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 0

    def test_list_credentials_filtered_by_platform(self, client, mocker, mock_user):  # noqa: ARG002
        """Test filtering credentials by platform."""
        # Arrange
        mock_cred = MagicMock()
        mock_cred.id = 1
        mock_cred.platform = "youtube"
        mock_cred.account_name = "test@example.com"
        mock_cred.is_active = True
        mock_cred.last_used_at = None

        mock_repo = mocker.patch("api.routers.credentials.UserCredentialRepository")
        mock_repo_instance = MagicMock()
        mock_repo_instance.list_by_platform = AsyncMock(return_value=[mock_cred])
        mock_repo.return_value = mock_repo_instance

        # Act
        response = client.get("/api/v1/credentials/?platform=youtube")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["platform"] == "youtube"
        # Verify repository method was called with platform filter
        mock_repo_instance.list_by_platform.assert_called_once()

    def test_list_credentials_without_data_by_default(self, client, mocker, mock_user):  # noqa: ARG002
        """Test that credentials are not decrypted by default."""
        # Arrange
        mock_cred = MagicMock()
        mock_cred.id = 1
        mock_cred.platform = "youtube"
        mock_cred.account_name = "test@example.com"
        mock_cred.is_active = True
        mock_cred.last_used_at = None

        mock_repo = mocker.patch("api.routers.credentials.UserCredentialRepository")
        mock_repo_instance = MagicMock()
        mock_repo_instance.find_by_user = AsyncMock(return_value=[mock_cred])
        mock_repo.return_value = mock_repo_instance

        # Act
        response = client.get("/api/v1/credentials/")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        # Credentials should not be included in response
        assert "credentials" not in data[0] or data[0]["credentials"] is None

    def test_list_credentials_with_include_data(self, client, mocker):
        """Test decrypting credentials when include_data=true."""
        # Arrange
        mock_credential = MagicMock()
        mock_credential.id = 1
        mock_credential.platform = "youtube"
        mock_credential.account_name = "test@example.com"
        mock_credential.is_active = True
        mock_credential.last_used_at = datetime.now(UTC)
        mock_credential.encrypted_data = b"encrypted"

        mock_repo = mocker.patch("api.routers.credentials.UserCredentialRepository")
        mock_repo_instance = MagicMock()
        mock_repo_instance.find_by_user = AsyncMock(return_value=[mock_credential])
        mock_repo.return_value = mock_repo_instance

        # Mock encryption service
        mock_encryption = mocker.patch("api.routers.credentials.get_encryption")
        mock_encryption_instance = MagicMock()
        mock_encryption_instance.decrypt_credentials = MagicMock(return_value={"access_token": "decrypted"})
        mock_encryption.return_value = mock_encryption_instance

        # Act
        response = client.get("/api/v1/credentials/?include_data=true")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["credentials"] is not None

    def test_list_credentials_multi_tenancy(self, client, mocker, mock_user):
        """Test that credentials are filtered by user_id (multi-tenancy)."""
        # Arrange
        mock_repo = mocker.patch("api.routers.credentials.UserCredentialRepository")
        mock_repo_instance = MagicMock()
        mock_repo_instance.find_by_user = AsyncMock(return_value=[])
        mock_repo.return_value = mock_repo_instance

        # Act
        response = client.get("/api/v1/credentials/")

        # Assert
        assert response.status_code == 200
        # Verify repository was called with current user's ID
        mock_repo_instance.find_by_user.assert_called_once_with(mock_user.id)


@pytest.mark.unit
class TestGetCredentialById:
    """Tests for GET /api/v1/credentials/{id} endpoint."""

    def test_get_credential_success(self, client, mocker, mock_user):
        """Test successful retrieval of single credential."""
        # Arrange
        credential_id = 1
        mock_credential = MagicMock()
        mock_credential.id = credential_id
        mock_credential.user_id = mock_user.id
        mock_credential.platform = "youtube"
        mock_credential.account_name = "test@example.com"
        mock_credential.is_active = True
        mock_credential.last_used_at = None

        mock_repo = mocker.patch("api.routers.credentials.UserCredentialRepository")
        mock_repo_instance = MagicMock()
        mock_repo_instance.get_by_id = AsyncMock(return_value=mock_credential)
        mock_repo.return_value = mock_repo_instance

        # Act
        response = client.get(f"/api/v1/credentials/{credential_id}")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == credential_id
        assert data["platform"] == "youtube"

    def test_get_credential_not_found(self, client, mocker):
        """Test 404 when credential not found."""
        # Arrange
        credential_id = 999
        mock_repo = mocker.patch("api.routers.credentials.UserCredentialRepository")
        mock_repo_instance = MagicMock()
        mock_repo_instance.get_by_id = AsyncMock(return_value=None)
        mock_repo.return_value = mock_repo_instance

        # Act
        response = client.get(f"/api/v1/credentials/{credential_id}")

        # Assert
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_get_credential_belongs_to_different_user(self, client, mocker):
        """Test that user cannot access credential of another user (multi-tenancy)."""
        # Arrange
        credential_id = 1
        mock_credential = MagicMock()
        mock_credential.id = credential_id
        mock_credential.user_id = "other_user_id"  # Different user
        mock_credential.platform = "youtube"

        mock_repo = mocker.patch("api.routers.credentials.UserCredentialRepository")
        mock_repo_instance = MagicMock()
        mock_repo_instance.get_by_id = AsyncMock(return_value=mock_credential)
        mock_repo.return_value = mock_repo_instance

        # Act
        response = client.get(f"/api/v1/credentials/{credential_id}")

        # Assert
        assert response.status_code == 404
        # Should not reveal that credential exists but belongs to another user

    def test_get_credential_with_include_data(self, client, mocker, mock_user):
        """Test decrypting credential when include_data=true."""
        # Arrange
        credential_id = 1
        mock_credential = MagicMock()
        mock_credential.id = credential_id
        mock_credential.user_id = mock_user.id
        mock_credential.platform = "youtube"
        mock_credential.account_name = "test@example.com"
        mock_credential.is_active = True
        mock_credential.last_used_at = None
        mock_credential.encrypted_data = b"encrypted"

        mock_repo = mocker.patch("api.routers.credentials.UserCredentialRepository")
        mock_repo_instance = MagicMock()
        mock_repo_instance.get_by_id = AsyncMock(return_value=mock_credential)
        mock_repo.return_value = mock_repo_instance

        # Mock encryption service
        mock_encryption = mocker.patch("api.routers.credentials.get_encryption")
        mock_encryption_instance = MagicMock()
        mock_encryption_instance.decrypt_credentials = MagicMock(return_value={"access_token": "decrypted"})
        mock_encryption.return_value = mock_encryption_instance

        # Act
        response = client.get(f"/api/v1/credentials/{credential_id}?include_data=true")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["credentials"] is not None


@pytest.mark.unit
class TestCheckCredentialsStatus:
    """Tests for GET /api/v1/credentials/status endpoint."""

    def test_check_status_success(self, client, mocker):
        """Test successful retrieval of credentials status."""
        # Arrange
        mock_repo = mocker.patch("api.routers.credentials.UserCredentialRepository")
        mock_repo_instance = MagicMock()

        # Mock different platforms having different credentials
        async def mock_list_by_platform(user_id, platform):
            if platform in ["youtube", "zoom"]:
                return [create_mock_credential(platform=platform)]
            return []

        mock_repo_instance.list_by_platform = AsyncMock(side_effect=mock_list_by_platform)
        mock_repo.return_value = mock_repo_instance

        # Act
        response = client.get("/api/v1/credentials/status")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert "user_id" in data
        assert "available_platforms" in data
        assert "credentials_status" in data
        assert isinstance(data["credentials_status"], dict)

    def test_check_status_no_credentials(self, client, mocker):
        """Test status when user has no credentials."""
        # Arrange
        mock_repo = mocker.patch("api.routers.credentials.UserCredentialRepository")
        mock_repo_instance = MagicMock()
        mock_repo_instance.list_by_platform = AsyncMock(return_value=[])
        mock_repo.return_value = mock_repo_instance

        # Act
        response = client.get("/api/v1/credentials/status")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data["available_platforms"]) == 0
        # All platforms should show False
        for platform_status in data["credentials_status"].values():
            assert not platform_status

    def test_check_status_includes_all_platforms(self, client, mocker):
        """Test that status includes all supported platforms."""
        # Arrange
        mock_repo = mocker.patch("api.routers.credentials.UserCredentialRepository")
        mock_repo_instance = MagicMock()
        mock_repo_instance.list_by_platform = AsyncMock(return_value=[])
        mock_repo.return_value = mock_repo_instance

        # Act
        response = client.get("/api/v1/credentials/status")

        # Assert
        assert response.status_code == 200
        data = response.json()
        status_map = data["credentials_status"]

        # Check for key platforms
        expected_platforms = ["zoom", "youtube", "vk_video", "fireworks"]
        for platform in expected_platforms:
            assert platform in status_map

    def test_check_status_multi_tenancy(self, client, mocker, mock_user):
        """Test that status is checked for current user only (multi-tenancy)."""
        # Arrange
        mock_repo = mocker.patch("api.routers.credentials.UserCredentialRepository")
        mock_repo_instance = MagicMock()
        mock_repo_instance.list_by_platform = AsyncMock(return_value=[])
        mock_repo.return_value = mock_repo_instance

        # Act
        response = client.get("/api/v1/credentials/status")

        # Assert
        assert response.status_code == 200
        # Verify all platform checks were done for current user
        for call in mock_repo_instance.list_by_platform.call_args_list:
            assert call.args[0] == mock_user.id
