"""Unit tests for output preset list/detail schemas."""

from datetime import UTC, datetime

import pytest

from api.schemas.template.output_preset import OutputPresetListItem, OutputPresetResponse


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
