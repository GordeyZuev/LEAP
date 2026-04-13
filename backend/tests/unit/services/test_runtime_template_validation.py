"""Tests for runtime template validation in config resolution."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.services.config_utils import (
    BoundTemplateNotFoundError,
    InvalidOutputPresetsError,
    RuntimeTemplateNotFoundError,
    resolve_full_config,
    validate_effective_output_config,
    validate_runtime_template_override,
)


@pytest.mark.asyncio
async def test_validate_runtime_template_override_missing_raises():
    session = AsyncMock()
    with patch("api.services.config_utils.RecordingTemplateRepository") as repo_cls:
        repo_cls.return_value.find_by_id = AsyncMock(return_value=None)
        with pytest.raises(RuntimeTemplateNotFoundError, match="Template 999 not found"):
            await validate_runtime_template_override(session, "user-1", {"runtime_template_id": 999})


@pytest.mark.asyncio
async def test_validate_runtime_template_override_none_id_skips():
    session = AsyncMock()
    with patch("api.services.config_utils.RecordingTemplateRepository") as repo_cls:
        await validate_runtime_template_override(session, "user-1", {"runtime_template_id": None})
        repo_cls.assert_not_called()


@pytest.mark.asyncio
async def test_resolve_full_config_raises_for_bad_runtime_template():
    session = AsyncMock()
    recording = MagicMock()
    recording.template_id = None
    recording.processing_preferences = None

    with (
        patch("api.services.config_utils.RecordingRepository") as rec_repo_cls,
        patch("api.services.config_utils.UserConfigRepository") as user_repo_cls,
        patch("api.services.config_utils.RecordingTemplateRepository") as tpl_repo_cls,
    ):
        rec_repo_cls.return_value.get_by_id = AsyncMock(return_value=recording)
        user_repo_cls.return_value.get_effective_config = AsyncMock(return_value={})

        tpl_inst = tpl_repo_cls.return_value
        tpl_inst.find_by_id = AsyncMock(return_value=None)

        with pytest.raises(RuntimeTemplateNotFoundError):
            await resolve_full_config(
                session,
                recording_id=1,
                user_id="user-1",
                manual_override={"runtime_template_id": 42},
            )


@pytest.mark.asyncio
async def test_resolve_full_config_bound_template_missing_raises():
    session = AsyncMock()
    recording = MagicMock()
    recording.template_id = 8
    recording.processing_preferences = None

    with (
        patch("api.services.config_utils.RecordingRepository") as rec_repo_cls,
        patch("api.services.config_utils.UserConfigRepository") as user_repo_cls,
        patch("api.services.config_utils.RecordingTemplateRepository") as tpl_repo_cls,
    ):
        rec_repo_cls.return_value.get_by_id = AsyncMock(return_value=recording)
        user_repo_cls.return_value.get_effective_config = AsyncMock(return_value={})
        tpl_repo_cls.return_value.find_by_id = AsyncMock(return_value=None)

        with pytest.raises(BoundTemplateNotFoundError, match="bound to template 8"):
            await resolve_full_config(session, 1, "user-1", None, include_output_config=False)


@pytest.mark.asyncio
async def test_validate_effective_unknown_preset_ids():
    session = AsyncMock()
    with patch("api.services.config_utils.OutputPresetRepository") as repo_cls:
        repo_cls.return_value.find_by_ids = AsyncMock(return_value=[])
        with pytest.raises(InvalidOutputPresetsError, match="Unknown"):
            await validate_effective_output_config(session, "user-1", {"preset_ids": [101]})


@pytest.mark.asyncio
async def test_validate_effective_inactive_preset():
    session = AsyncMock()
    preset = MagicMock()
    preset.id = 3
    preset.platform = "youtube"
    preset.is_active = False
    with patch("api.services.config_utils.OutputPresetRepository") as repo_cls:
        repo_cls.return_value.find_by_ids = AsyncMock(return_value=[preset])
        with pytest.raises(InvalidOutputPresetsError, match="Inactive"):
            await validate_effective_output_config(session, "user-1", {"preset_ids": [3]})


@pytest.mark.asyncio
async def test_validate_effective_auto_upload_platforms_without_presets():
    session = AsyncMock()
    with pytest.raises(InvalidOutputPresetsError, match="requires preset_ids"):
        await validate_effective_output_config(
            session,
            "user-1",
            {"auto_upload": True, "default_platforms": ["youtube"], "preset_ids": []},
        )


@pytest.mark.asyncio
async def test_validate_effective_default_platform_not_covered():
    session = AsyncMock()
    preset = MagicMock()
    preset.id = 1
    preset.platform = "vk"
    preset.is_active = True
    with patch("api.services.config_utils.OutputPresetRepository") as repo_cls:
        repo_cls.return_value.find_by_ids = AsyncMock(return_value=[preset])
        with pytest.raises(InvalidOutputPresetsError, match="youtube"):
            await validate_effective_output_config(
                session,
                "user-1",
                {
                    "auto_upload": True,
                    "preset_ids": [1],
                    "default_platforms": ["youtube"],
                },
            )
