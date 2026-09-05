"""Unit tests for TemplateOutputConfig normalization."""

import pytest

from api.schemas.template.output_config import TemplateOutputConfig, normalize_output_config
from api.schemas.template.template import RecordingTemplateResponse


@pytest.mark.unit
class TestNormalizeOutputConfig:
    def test_missing_preset_ids(self) -> None:
        raw = {"auto_upload": False, "upload_captions": True, "default_platforms": []}
        normalized = normalize_output_config(raw)
        assert normalized["preset_ids"] == []
        assert normalized["playlist_ids"] == []

    def test_template_output_config_accepts_legacy_shape(self) -> None:
        cfg = TemplateOutputConfig.model_validate(
            {"auto_upload": False, "upload_captions": True, "default_platforms": []}
        )
        assert cfg.preset_ids == []

    def test_auto_upload_requires_preset_ids(self) -> None:
        with pytest.raises(ValueError, match="auto_upload"):
            TemplateOutputConfig.model_validate({"auto_upload": True, "preset_ids": []})

    def test_response_model_normalizes_output_config(self) -> None:
        """ORM-style payload without preset_ids must validate (GET /templates/{id})."""
        payload = {
            "id": 1,
            "user_id": "u1",
            "name": "Default",
            "description": None,
            "matching_rules": None,
            "processing_config": None,
            "metadata_config": None,
            "output_config": {"auto_upload": False, "upload_captions": True, "default_platforms": []},
            "is_draft": False,
            "is_active": True,
            "is_default": True,
            "used_count": 0,
            "last_used_at": None,
            "created_at": "2026-08-22T12:00:00+00:00",
            "updated_at": "2026-08-22T12:00:00+00:00",
        }
        model = RecordingTemplateResponse.model_validate(payload)
        assert model.output_config is not None
        assert model.output_config.preset_ids == []
        assert model.output_config.playlist_ids == []

    def test_playlist_ids_unique_and_capped(self) -> None:
        cfg = TemplateOutputConfig.model_validate({"playlist_ids": [1, 2, 3]})
        assert cfg.playlist_ids == [1, 2, 3]
        with pytest.raises(ValueError, match="unique"):
            TemplateOutputConfig.model_validate({"playlist_ids": [1, 1]})
        with pytest.raises(ValueError, match="Maximum 10"):
            TemplateOutputConfig.model_validate({"playlist_ids": list(range(1, 12))})
