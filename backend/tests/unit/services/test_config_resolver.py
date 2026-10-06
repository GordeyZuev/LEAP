"""Unit tests for ConfigResolver and merge helpers."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from api.services.config_resolver import ConfigResolver, _processing_slice_from_user_config
from api.services.default_template import upload_config_to_output
from api.services.merger import deep_merge


@pytest.mark.unit
class TestMerger:
    def test_deep_merge_skip_none(self) -> None:
        base = {"a": 1, "b": {"c": 2}}
        override = {"b": {"c": None, "d": 3}, "e": None}
        result = deep_merge(base, override, skip_none=True)
        assert result["b"]["c"] == 2
        assert result["b"]["d"] == 3
        assert "e" not in result


@pytest.mark.unit
class TestUploadMapping:
    def test_upload_config_to_output_preset_ids(self) -> None:
        upload = {
            "auto_upload": True,
            "default_preset_ids": {"youtube": 5, "vk": 7},
            "default_platforms": ["youtube"],
        }
        out = upload_config_to_output(upload)
        assert out["auto_upload"] is True
        assert set(out["preset_ids"]) == {5, 7}
        assert out["default_platforms"] == ["youtube"]

    def test_upload_config_to_output_empty_presets(self) -> None:
        out = upload_config_to_output({"auto_upload": False, "upload_captions": True})
        assert out["preset_ids"] == []


@pytest.mark.unit
class TestProcessingSlice:
    def test_reads_transcription_not_processing_key(self) -> None:
        user = {"transcription": {"language": "en"}, "trimming": {"enable_trimming": False}}
        result = _processing_slice_from_user_config(user)
        assert result["transcription"]["language"] == "en"
        assert result["trimming"]["enable_trimming"] is False


@pytest.mark.unit
class TestConfigResolverOutput:
    @pytest.mark.asyncio
    async def test_resolve_output_uses_upload_not_output_key(self, mock_db_session) -> None:
        resolver = ConfigResolver(mock_db_session)
        resolver.user_config_repo.get_effective_config = AsyncMock(
            return_value={"upload": {"auto_upload": True, "default_preset_ids": {"youtube": 3}}}
        )
        resolver.template_repo.find_default_by_user = AsyncMock(return_value=None)

        recording = MagicMock()
        recording.template_id = None
        recording.processing_preferences = None

        output = await resolver.resolve_output_config(recording, "user_1")
        assert output.get("auto_upload") is True
        assert output.get("preset_ids") == [3]

    @pytest.mark.asyncio
    async def test_ignore_preferences_keeps_the_template_merge(self, mock_db_session) -> None:
        from api.services.config_resolver import ResolveContext

        resolver = ConfigResolver(mock_db_session)
        resolver.user_config_repo.get_effective_config = AsyncMock(return_value={})
        template = MagicMock()
        template.id = 1
        template.processing_config = {"transcription": {"language": "en", "retention_exempt": False}}
        template.output_config = {"preset_ids": [1], "publish_leap": True}
        template.metadata_config = {"title_template": "Lecture"}
        resolver.template_repo.find_default_by_user = AsyncMock(return_value=template)

        recording = MagicMock()
        recording.template_id = None
        recording.processing_preferences = {
            "processing_config": {"transcription": {"language": "de"}},
            "output_config": {"preset_ids": [9]},
            "metadata_config": {"title_template": "Override"},
        }

        effective = await resolver.resolve(ResolveContext(user_id="user_1", recording=recording))
        inherited = await resolver.resolve(
            ResolveContext(user_id="user_1", recording=recording, ignore_preferences=True)
        )

        assert effective.processing["transcription"]["language"] == "de"
        assert effective.output["preset_ids"] == [9]
        assert effective.metadata["title_template"] == "Override"
        assert inherited.processing["transcription"]["language"] == "en"
        assert inherited.processing["transcription"]["retention_exempt"] is False
        assert inherited.output["preset_ids"] == [1]
        assert inherited.metadata["title_template"] == "Lecture"
