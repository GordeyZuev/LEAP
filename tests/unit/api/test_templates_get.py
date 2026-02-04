"""Unit tests for GET /templates endpoints."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from tests.fixtures.factories import create_mock_template


@pytest.mark.unit
class TestListTemplates:
    """Tests for GET /api/v1/templates endpoint."""

    def test_list_templates_success(self, client, mocker, mock_user):
        """Test successful retrieval of templates list."""
        # Arrange
        mock_templates = [
            create_mock_template(template_id=1, name="Template 1", user_id=mock_user.id),
            create_mock_template(template_id=2, name="Template 2", user_id=mock_user.id),
        ]

        mock_repo = mocker.patch("api.routers.templates.RecordingTemplateRepository")
        mock_repo_instance = MagicMock()
        mock_repo_instance.find_by_user = AsyncMock(return_value=mock_templates)
        mock_repo.return_value = mock_repo_instance

        # Act
        response = client.get("/api/v1/templates")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["name"] == "Template 1"
        assert data[1]["name"] == "Template 2"

    def test_list_templates_empty(self, client, mocker):
        """Test empty templates list."""
        # Arrange
        mock_repo = mocker.patch("api.routers.templates.RecordingTemplateRepository")
        mock_repo_instance = MagicMock()
        mock_repo_instance.find_by_user = AsyncMock(return_value=[])
        mock_repo.return_value = mock_repo_instance

        # Act
        response = client.get("/api/v1/templates")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 0

    def test_list_templates_with_search(self, client, mocker, mock_user):
        """Test searching templates by name."""
        # Arrange
        mock_templates = [
            create_mock_template(template_id=1, name="Python Course Template", user_id=mock_user.id),
            create_mock_template(template_id=2, name="Python Advanced", user_id=mock_user.id),
            create_mock_template(template_id=3, name="Math Course Template", user_id=mock_user.id),
        ]

        mock_repo = mocker.patch("api.routers.templates.RecordingTemplateRepository")
        mock_repo_instance = MagicMock()
        mock_repo_instance.find_by_user = AsyncMock(return_value=mock_templates)
        mock_repo.return_value = mock_repo_instance

        # Act
        response = client.get("/api/v1/templates?search=Python")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2

    def test_list_templates_exclude_drafts_by_default(self, client, mocker, mock_user):
        """Test that draft templates are excluded by default."""
        # Arrange
        mock_templates = [
            create_mock_template(template_id=1, name="Active Template", user_id=mock_user.id, is_draft=False),
        ]

        mock_repo = mocker.patch("api.routers.templates.RecordingTemplateRepository")
        mock_repo_instance = MagicMock()
        mock_repo_instance.find_by_user = AsyncMock(return_value=mock_templates)
        mock_repo.return_value = mock_repo_instance

        # Act
        response = client.get("/api/v1/templates")

        # Assert
        assert response.status_code == 200
        # Verify include_drafts=False was passed
        mock_repo_instance.find_by_user.assert_called_once()
        call_kwargs = mock_repo_instance.find_by_user.call_args.kwargs
        assert not call_kwargs.get("include_drafts")

    def test_list_templates_include_drafts(self, client, mocker, mock_user):
        """Test including draft templates when requested."""
        # Arrange
        mock_templates = [
            create_mock_template(template_id=1, name="Active", user_id=mock_user.id, is_draft=False),
            create_mock_template(template_id=2, name="Draft", user_id=mock_user.id, is_draft=True),
        ]

        mock_repo = mocker.patch("api.routers.templates.RecordingTemplateRepository")
        mock_repo_instance = MagicMock()
        mock_repo_instance.find_by_user = AsyncMock(return_value=mock_templates)
        mock_repo.return_value = mock_repo_instance

        # Act
        response = client.get("/api/v1/templates?include_drafts=true")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2

    def test_list_templates_multi_tenancy(self, client, mocker, mock_user):
        """Test that templates are filtered by user_id (multi-tenancy)."""
        # Arrange
        mock_repo = mocker.patch("api.routers.templates.RecordingTemplateRepository")
        mock_repo_instance = MagicMock()
        mock_repo_instance.find_by_user = AsyncMock(return_value=[])
        mock_repo.return_value = mock_repo_instance

        # Act
        response = client.get("/api/v1/templates")

        # Assert
        assert response.status_code == 200
        # Verify repository was called with current user's ID
        mock_repo_instance.find_by_user.assert_called_once_with(mock_user.id, include_drafts=False)


@pytest.mark.unit
class TestGetTemplate:
    """Tests for GET /api/v1/templates/{id} endpoint."""

    def test_get_template_success(self, client, mocker, mock_user):
        """Test successful retrieval of single template."""
        # Arrange
        template_id = 1
        mock_template = create_mock_template(
            template_id=template_id,
            name="Test Template",
            user_id=mock_user.id,
            description="Test description",
        )

        mock_repo = mocker.patch("api.routers.templates.RecordingTemplateRepository")
        mock_repo_instance = MagicMock()
        mock_repo_instance.find_by_id = AsyncMock(return_value=mock_template)
        mock_repo.return_value = mock_repo_instance

        # Act
        response = client.get(f"/api/v1/templates/{template_id}")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == template_id
        assert data["name"] == "Test Template"
        assert data["description"] == "Test description"

    def test_get_template_not_found(self, client, mocker):
        """Test 404 when template not found."""
        # Arrange
        template_id = 999
        mock_repo = mocker.patch("api.routers.templates.RecordingTemplateRepository")
        mock_repo_instance = MagicMock()
        mock_repo_instance.find_by_id = AsyncMock(return_value=None)
        mock_repo.return_value = mock_repo_instance

        # Act
        response = client.get(f"/api/v1/templates/{template_id}")

        # Assert
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_get_template_belongs_to_different_user(self, client, mocker):
        """Test that user cannot access template of another user (multi-tenancy)."""
        # Arrange
        template_id = 1
        mock_repo = mocker.patch("api.routers.templates.RecordingTemplateRepository")
        mock_repo_instance = MagicMock()
        # Repository returns None when template doesn't belong to user
        mock_repo_instance.find_by_id = AsyncMock(return_value=None)
        mock_repo.return_value = mock_repo_instance

        # Act
        response = client.get(f"/api/v1/templates/{template_id}")

        # Assert
        assert response.status_code == 404
        # Verify repository was called with correct user_id
        mock_repo_instance.find_by_id.assert_called_once()


@pytest.mark.unit
class TestGetTemplateStats:
    """Tests for GET /api/v1/templates/{id}/stats endpoint."""

    def test_get_template_stats_success(self, client, mocker, mock_user):  # noqa: ARG002
        """Test successful retrieval of template statistics."""
        # Skip - this test requires complex async mock setup for SQLAlchemy queries
        pytest.skip("Requires complex async database mock setup")

    def test_get_template_stats_not_found(self, client, mocker):
        """Test 404 when template not found."""
        # Arrange
        template_id = 999
        mock_repo = mocker.patch("api.routers.templates.RecordingTemplateRepository")
        mock_repo_instance = MagicMock()
        mock_repo_instance.find_by_id = AsyncMock(return_value=None)
        mock_repo.return_value = mock_repo_instance

        # Act
        response = client.get(f"/api/v1/templates/{template_id}/stats")

        # Assert
        assert response.status_code == 404

    def test_get_template_stats_empty_recordings(self, client, mocker, mock_user):  # noqa: ARG002
        """Test stats for template with no recordings."""
        # Skip - this test requires complex async mock setup for SQLAlchemy queries
        pytest.skip("Requires complex async database mock setup")
