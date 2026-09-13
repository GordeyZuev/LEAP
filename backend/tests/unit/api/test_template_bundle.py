"""Tests for template bundle export/import/replace API."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from api.schemas.template.bundle import (
    BundleReference,
    TemplateBundleExport,
    TemplateBundleExportItem,
)
from tests.fixtures.factories import create_mock_template


@pytest.mark.unit
class TestExportTemplates:
    def test_export_requires_ids(self, client, mock_user):  # noqa: ARG002
        response = client.get("/api/v1/templates/export")
        assert response.status_code == 422

    def test_export_success(self, client, mocker, mock_user):  # noqa: ARG002
        mocker.patch(
            "api.services.template_bundle_service.export_templates_bundle",
            new_callable=AsyncMock,
            return_value=TemplateBundleExport(
                exported_at=datetime.now(UTC),
                reference=BundleReference(),
                templates=[
                    TemplateBundleExportItem(
                        id=7,
                        name="Export Me",
                        description="Desc",
                        is_draft=False,
                        is_active=True,
                        is_default=False,
                    )
                ],
            ),
        )

        response = client.get("/api/v1/templates/export?ids=7")
        assert response.status_code == 200
        data = response.json()
        assert data["leap_template_bundle"] == 1
        assert len(data["templates"]) == 1
        assert data["templates"][0]["id"] == 7


@pytest.mark.unit
class TestImportTemplatesDryRun:
    def test_import_dry_run_create(self, client, mocker, mock_user):  # noqa: ARG002
        mock_repo = mocker.patch("api.services.template_bundle_service.RecordingTemplateRepository")
        mock_repo_instance = MagicMock()
        mock_repo_instance.find_by_user = AsyncMock(return_value=[])
        mock_repo_instance.count_matchable_by_user = AsyncMock(return_value=0)
        mock_repo.return_value = mock_repo_instance

        mocker.patch(
            "api.services.quota_service.QuotaService.get_effective_quotas",
            new_callable=AsyncMock,
            return_value={"max_templates": 100},
        )

        body = {
            "leap_template_bundle": 1,
            "templates": [
                {
                    "name": "Imported Draft",
                    "is_draft": True,
                    "matching_rules": {"keywords": ["test"]},
                }
            ],
        }
        response = client.post("/api/v1/templates/import?dry_run=true", json=body)
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["dry_run"] is True
        assert len(data["created"]) == 1


@pytest.mark.unit
class TestReplaceTemplate:
    def test_validate_replace_ok(self, client, mocker, mock_user):
        mock_template = create_mock_template(template_id=3, user_id=mock_user.id)
        mock_template.is_default = False

        mock_repo = mocker.patch("api.routers.templates.RecordingTemplateRepository")
        mock_repo_instance = MagicMock()
        mock_repo_instance.find_by_id = AsyncMock(return_value=mock_template)
        mock_repo.return_value = mock_repo_instance

        mocker.patch("api.routers.templates.validate_effective_output_config", new_callable=AsyncMock)

        body = {
            "name": "Renamed",
            "description": None,
            "is_draft": True,
            "is_active": True,
            "matching_rules": {"keywords": ["a"]},
            "processing_config": None,
            "metadata_config": None,
            "output_config": None,
        }
        response = client.post("/api/v1/templates/3/validate-replace", json=body)
        assert response.status_code == 200
        assert response.json()["ok"] is True

    def test_validate_replace_rejects_default_matching(self, client, mocker, mock_user):
        mock_template = create_mock_template(template_id=1, user_id=mock_user.id)
        mock_template.is_default = True

        mock_repo = mocker.patch("api.routers.templates.RecordingTemplateRepository")
        mock_repo_instance = MagicMock()
        mock_repo_instance.find_by_id = AsyncMock(return_value=mock_template)
        mock_repo.return_value = mock_repo_instance

        body = {
            "name": "Default",
            "description": None,
            "is_draft": False,
            "is_active": True,
            "matching_rules": {"keywords": ["x"]},
            "processing_config": None,
            "metadata_config": None,
            "output_config": None,
        }
        response = client.post("/api/v1/templates/1/validate-replace", json=body)
        assert response.status_code == 200
        assert response.json()["ok"] is False

    def test_validate_replace_default_null_matching(self, client, mocker, mock_user):
        mock_template = create_mock_template(template_id=1, user_id=mock_user.id)
        mock_template.is_default = True

        mock_repo = mocker.patch("api.routers.templates.RecordingTemplateRepository")
        mock_repo_instance = MagicMock()
        mock_repo_instance.find_by_id = AsyncMock(return_value=mock_template)
        mock_repo.return_value = mock_repo_instance

        mocker.patch("api.routers.templates.validate_effective_output_config", new_callable=AsyncMock)

        body = {
            "name": "Default",
            "description": "Base video processing defaults",
            "is_draft": False,
            "is_active": True,
            "matching_rules": None,
            "processing_config": {"transcription": {"enable_transcription": True}},
            "metadata_config": None,
            "output_config": None,
        }
        response = client.post("/api/v1/templates/1/validate-replace", json=body)
        assert response.status_code == 200
        assert response.json()["ok"] is True
