"""Unit tests for output preset list/detail schemas."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from api.schemas.template.output_preset import OutputPresetCreate, OutputPresetListItem, OutputPresetResponse


@pytest.mark.unit
class TestOutputPresetSchemas:
    def test_list_item_accepts_null_credential_id(self) -> None:
        now = datetime(2026, 8, 22, 12, 0, tzinfo=UTC)
        item = OutputPresetListItem.model_validate(
            {
                "id": 2,
                "name": "VK preset",
                "platform": "vk",
                "credential_id": None,
                "is_active": True,
                "created_at": now,
                "updated_at": now,
            }
        )
        assert item.credential_id is None

    def test_response_accepts_null_credential_id(self) -> None:
        now = datetime(2026, 8, 22, 12, 0, tzinfo=UTC)
        item = OutputPresetResponse.model_validate(
            {
                "id": 2,
                "user_id": "u1",
                "name": "VK preset",
                "description": None,
                "platform": "vk",
                "credential_id": None,
                "preset_metadata": {},
                "is_active": True,
                "created_at": now,
                "updated_at": now,
            }
        )
        assert item.credential_id is None

    def test_create_leap_without_credential(self) -> None:
        preset = OutputPresetCreate.model_validate(
            {
                "name": "Course look",
                "platform": "leap",
                "preset_metadata": {"title_template": "{{ display_name }}"},
            }
        )
        assert preset.credential_id is None
        assert preset.platform == "leap"
        assert preset.preset_metadata.title_template == "{{ display_name }}"

    def test_create_leap_rejects_credential(self) -> None:
        with pytest.raises(ValidationError, match="must not have a credential"):
            OutputPresetCreate.model_validate(
                {
                    "name": "Course look",
                    "platform": "leap",
                    "credential_id": 3,
                    "preset_metadata": {},
                }
            )

    def test_create_youtube_requires_credential(self) -> None:
        with pytest.raises(ValidationError, match="credential_id is required"):
            OutputPresetCreate.model_validate(
                {
                    "name": "YT",
                    "platform": "youtube",
                    "preset_metadata": {},
                }
            )

    def test_leap_empty_metadata_not_youtube(self) -> None:
        now = datetime(2026, 8, 22, 12, 0, tzinfo=UTC)
        item = OutputPresetResponse.model_validate(
            {
                "id": 4,
                "user_id": "u1",
                "name": "Look",
                "description": None,
                "platform": "leap",
                "credential_id": None,
                "preset_metadata": {},
                "is_active": True,
                "created_at": now,
                "updated_at": now,
            }
        )
        assert item.preset_metadata.title_template is None
        assert not hasattr(item.preset_metadata, "privacy")
