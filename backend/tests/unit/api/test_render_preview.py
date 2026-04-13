"""POST /templates/render-preview and /presets/render-preview."""

from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.mark.unit
class TestTemplatesRenderPreview:
    def test_recording_not_found_returns_404(self, client, mocker) -> None:
        """Unknown recording_id for current user yields 404."""
        mock_repo = mocker.patch("api.routers.templates.RecordingRepository")
        inst = MagicMock()
        inst.get_by_id = AsyncMock(return_value=None)
        mock_repo.return_value = inst

        response = client.post(
            "/api/v1/templates/render-preview",
            json={
                "recording_id": 999,
                "title_template": "{{ display_name }}",
            },
        )
        assert response.status_code == 404
        assert response.json()["detail"] == "Recording not found"

    def test_stub_context_success(self, client) -> None:
        """Preview without recording uses stub context and returns valid result."""
        response = client.post(
            "/api/v1/templates/render-preview",
            json={"title_template": "{{ display_name }}"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["valid"] is True
        assert body["rendered_title"] == "Stub Recording"

    def test_template_not_found_returns_404(self, client, mocker) -> None:
        """template_id that does not belong to user yields 404."""
        mock_repo = mocker.patch("api.routers.templates.RecordingTemplateRepository")
        inst = MagicMock()
        inst.find_by_id = AsyncMock(return_value=None)
        mock_repo.return_value = inst

        response = client.post(
            "/api/v1/templates/render-preview",
            json={"template_id": 42, "title_template": "{{ display_name }}"},
        )
        assert response.status_code == 404


@pytest.mark.unit
class TestPresetsRenderPreview:
    def test_recording_not_found_returns_404(self, client, mocker) -> None:
        """Preset preview with alien recording_id yields 404."""
        mock_repo = mocker.patch("api.routers.output_presets.RecordingRepository")
        inst = MagicMock()
        inst.get_by_id = AsyncMock(return_value=None)
        mock_repo.return_value = inst

        response = client.post(
            "/api/v1/presets/render-preview",
            json={
                "recording_id": 888,
                "title_template": "{{ display_name }}",
            },
        )
        assert response.status_code == 404
