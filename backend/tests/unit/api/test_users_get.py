"""Unit tests for GET /users/me endpoints."""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from api.schemas.auth.subscription import QuotaStatusResponse


@pytest.mark.unit
class TestGetCurrentUser:
    """Tests for GET /api/v1/users/me endpoint."""

    def test_get_current_user_success(self, client, mock_user):
        """Test successful retrieval of current user profile."""
        # Act
        response = client.get("/api/v1/users/me")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == mock_user.id
        assert data["email"] == mock_user.email
        assert data["full_name"] == mock_user.full_name
        assert data["role"] == mock_user.role
        assert data["is_active"] == mock_user.is_active
        assert data["is_verified"] == mock_user.is_verified

    def test_get_current_user_includes_required_fields(self, client):
        """Test that response includes all required user fields."""
        # Act
        response = client.get("/api/v1/users/me")

        # Assert
        assert response.status_code == 200
        data = response.json()
        required_fields = [
            "id",
            "email",
            "full_name",
            "timezone",
            "role",
            "is_active",
            "is_verified",
            "created_at",
        ]
        for field in required_fields:
            assert field in data


@pytest.mark.unit
class TestGetCurrentUserQuota:
    """Tests for GET /api/v1/users/me/quota endpoint."""

    def test_get_quota_success(self, client, mocker, mock_user):  # noqa: ARG002
        """Test successful retrieval of quota status."""
        mock_response = QuotaStatusResponse(
            subscription=None,
            current_usage=None,
            recordings={"used": 5, "limit": 10, "available": 5},
            storage={"used_gb": 2.5, "limit_gb": 5.0, "available_gb": 2.5},
            concurrent_tasks={"used": 1, "limit": 5, "available": 4},
            automation_jobs={"used": 0, "limit": 3, "available": 3},
            is_overage_enabled=False,
            overage_cost_this_month=Decimal("0"),
            overage_limit=None,
        )
        mock_quota_cls = mocker.patch("api.routers.users.QuotaService")
        mock_instance = MagicMock()
        mock_instance.get_quota_status = AsyncMock(return_value=mock_response)
        mock_quota_cls.return_value = mock_instance

        response = client.get("/api/v1/users/me/quota")

        assert response.status_code == 200
        data = response.json()
        assert data["recordings"]["used"] == 5
        assert data["recordings"]["limit"] == 10
        assert data["storage"]["used_gb"] == 2.5

    def test_get_quota_user_not_found(self, client, mocker):
        """Test 404 when user quota not found."""
        # Arrange
        mock_quota_service = mocker.patch("api.routers.users.QuotaService")
        mock_service_instance = MagicMock()
        mock_service_instance.get_quota_status = AsyncMock(side_effect=ValueError("User not found"))
        mock_quota_service.return_value = mock_service_instance

        # Act
        response = client.get("/api/v1/users/me/quota")

        # Assert
        assert response.status_code == 404

    def test_get_quota_with_overage(self, client, mocker, mock_user):  # noqa: ARG002
        """Test quota status with overage usage."""
        mock_response = QuotaStatusResponse(
            subscription=None,
            current_usage=None,
            recordings={"used": 15, "limit": 10, "available": None},
            storage={"used_gb": 6.0, "limit_gb": 5.0, "available_gb": None},
            concurrent_tasks={"used": 3, "limit": 5, "available": 2},
            automation_jobs={"used": 0, "limit": 3, "available": 3},
            is_overage_enabled=True,
            overage_cost_this_month=Decimal("2.50"),
            overage_limit=Decimal("50"),
        )
        mock_quota_cls = mocker.patch("api.routers.users.QuotaService")
        mock_instance = MagicMock()
        mock_instance.get_quota_status = AsyncMock(return_value=mock_response)
        mock_quota_cls.return_value = mock_instance

        response = client.get("/api/v1/users/me/quota")

        assert response.status_code == 200
        data = response.json()
        assert data["recordings"]["available"] is None
        assert data["is_overage_enabled"] is True
        assert float(data["overage_cost_this_month"]) == 2.5
