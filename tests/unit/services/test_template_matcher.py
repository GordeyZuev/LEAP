"""Unit tests for TemplateMatcher service."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from tests.fixtures.factories import create_mock_recording, create_mock_template


@pytest.mark.unit
class TestTemplateMatcher:
    """Tests for template matching logic."""

    @pytest.mark.asyncio
    async def test_find_matching_template_by_display_name(self, mock_db_session):
        """Test finding template by display name pattern."""
        # Arrange
        from api.services.template_matcher import TemplateMatcher

        user_id = "user_123"
        matcher = TemplateMatcher(mock_db_session)

        # Mock recording
        recording = create_mock_recording(display_name="Python Advanced Course", user_id=user_id)

        # Mock templates
        mock_template = create_mock_template(
            template_id=1,
            name="Python Courses",
            user_id=user_id,
            matching_rules={"display_name_pattern": ".*Python.*"},
        )
        matcher.repo.find_active_by_user = AsyncMock(return_value=[mock_template])

        # Mock matching logic
        matcher._matches_template = MagicMock(return_value=True)

        # Act
        result = await matcher.find_matching_template(recording, user_id)

        # Assert
        assert result is not None
        assert result.id == mock_template.id

    @pytest.mark.asyncio
    async def test_find_matching_template_no_match(self, mock_db_session):
        """Test returns None when no template matches."""
        # Arrange
        from api.services.template_matcher import TemplateMatcher

        user_id = "user_123"
        matcher = TemplateMatcher(mock_db_session)

        recording = create_mock_recording(display_name="Math Course", user_id=user_id)

        mock_template = create_mock_template(
            template_id=1,
            name="Python Courses",
            user_id=user_id,
            matching_rules={"display_name_pattern": ".*Python.*"},
        )
        matcher.repo.find_active_by_user = AsyncMock(return_value=[mock_template])
        matcher._matches_template = MagicMock(return_value=False)

        # Act
        result = await matcher.find_matching_template(recording, user_id)

        # Assert
        assert result is None

    @pytest.mark.asyncio
    async def test_find_matching_template_multiple_templates(self, mock_db_session):
        """Test returns first matching template when multiple match."""
        # Arrange
        from api.services.template_matcher import TemplateMatcher

        user_id = "user_123"
        matcher = TemplateMatcher(mock_db_session)

        recording = create_mock_recording(display_name="Python Advanced Course", user_id=user_id)

        # Two templates that could match
        mock_template1 = create_mock_template(
            template_id=1, name="Python Courses", user_id=user_id, matching_rules={"pattern": ".*Python.*"}
        )
        mock_template2 = create_mock_template(
            template_id=2, name="Advanced Courses", user_id=user_id, matching_rules={"pattern": ".*Advanced.*"}
        )

        matcher.repo.find_active_by_user = AsyncMock(return_value=[mock_template1, mock_template2])

        # First template matches
        def side_effect(recording, template):
            return template.id == 1

        matcher._matches_template = MagicMock(side_effect=side_effect)

        # Act
        result = await matcher.find_matching_template(recording, user_id)

        # Assert
        assert result is not None
        assert result.id == 1  # First matching template

    @pytest.mark.asyncio
    async def test_find_matching_template_draft_excluded(self, mock_db_session):
        """Test that draft templates are excluded from matching."""
        # Arrange
        from api.services.template_matcher import TemplateMatcher

        user_id = "user_123"
        matcher = TemplateMatcher(mock_db_session)

        recording = create_mock_recording(display_name="Python Course", user_id=user_id)

        # Mock only returns active templates (not drafts)
        mock_template = create_mock_template(template_id=1, user_id=user_id, is_draft=False, is_active=True)
        matcher.repo.find_active_by_user = AsyncMock(return_value=[mock_template])
        matcher._matches_template = MagicMock(return_value=True)

        # Act
        result = await matcher.find_matching_template(recording, user_id)

        # Assert
        assert result is not None
        matcher.repo.find_active_by_user.assert_called_once_with(user_id)


@pytest.mark.unit
class TestApplyTemplate:
    """Tests for applying template to recording."""

    @pytest.mark.asyncio
    async def test_apply_template_merges_processing_config(self, mock_db_session):
        """Test applying template merges processing config."""
        # Arrange
        from api.services.template_matcher import TemplateMatcher

        matcher = TemplateMatcher(mock_db_session)

        recording = create_mock_recording(record_id=1, user_id="user_123")
        recording.processing_preferences = {"trimming": {"enabled": False}}

        template = create_mock_template(
            template_id=1,
            user_id="user_123",
            processing_config={"trimming": {"enabled": True, "threshold": -40}},
        )

        matcher.repo.increment_usage = AsyncMock()

        # Act
        result = await matcher.apply_template(recording, template)

        # Assert
        assert result.processing_preferences["trimming"]["enabled"] is True
        assert result.processing_preferences["trimming"]["threshold"] == -40
        matcher.repo.increment_usage.assert_called_once_with(template)

    @pytest.mark.asyncio
    async def test_apply_template_adds_output_config(self, mock_db_session):
        """Test applying template adds output config."""
        # Arrange
        from api.services.template_matcher import TemplateMatcher

        matcher = TemplateMatcher(mock_db_session)

        recording = create_mock_recording(record_id=1, user_id="user_123")
        recording.processing_preferences = {}

        template = create_mock_template(
            template_id=1,
            user_id="user_123",
            output_config={"auto_upload": True, "preset_ids": [1, 2]},
        )

        matcher.repo.increment_usage = AsyncMock()

        # Act
        result = await matcher.apply_template(recording, template)

        # Assert
        assert "output_config" in result.processing_preferences
        assert result.processing_preferences["output_config"]["auto_upload"] is True
        assert result.processing_preferences["output_config"]["preset_ids"] == [1, 2]

    @pytest.mark.asyncio
    async def test_apply_template_increments_usage_counter(self, mock_db_session):
        """Test applying template increments usage counter."""
        # Arrange
        from api.services.template_matcher import TemplateMatcher

        matcher = TemplateMatcher(mock_db_session)

        recording = create_mock_recording(record_id=1, user_id="user_123")
        template = create_mock_template(template_id=1, user_id="user_123")

        matcher.repo.increment_usage = AsyncMock()

        # Act
        await matcher.apply_template(recording, template)

        # Assert
        matcher.repo.increment_usage.assert_called_once_with(template)

    @pytest.mark.asyncio
    async def test_apply_template_deep_merge_config(self, mock_db_session):
        """Test deep merge of nested config structures."""
        # Arrange
        from api.services.template_matcher import TemplateMatcher

        matcher = TemplateMatcher(mock_db_session)

        recording = create_mock_recording(record_id=1, user_id="user_123")
        recording.processing_preferences = {
            "trimming": {"enabled": True, "threshold": -30},
            "transcription": {"language": "en"},
        }

        template = create_mock_template(
            template_id=1,
            user_id="user_123",
            processing_config={
                "trimming": {"threshold": -40},  # Override threshold only
                "segmentation": {"enabled": True},  # Add new config
            },
        )

        matcher.repo.increment_usage = AsyncMock()

        # Act
        result = await matcher.apply_template(recording, template)

        # Assert
        # Trimming: enabled stays True, threshold updated to -40
        assert result.processing_preferences["trimming"]["enabled"] is True
        assert result.processing_preferences["trimming"]["threshold"] == -40
        # Transcription: untouched
        assert result.processing_preferences["transcription"]["language"] == "en"
        # Segmentation: added
        assert result.processing_preferences["segmentation"]["enabled"] is True


@pytest.mark.unit
class TestConfigMerge:
    """Tests for config merging logic."""

    def test_merge_configs_simple(self, mock_db_session):
        """Test simple config merge."""
        # Arrange
        from api.services.template_matcher import TemplateMatcher

        matcher = TemplateMatcher(mock_db_session)
        base = {"a": 1, "b": 2}
        override = {"b": 3, "c": 4}

        # Act
        result = matcher._merge_configs(base, override)

        # Assert
        assert result == {"a": 1, "b": 3, "c": 4}

    def test_merge_configs_nested(self, mock_db_session):
        """Test nested config merge."""
        # Arrange
        from api.services.template_matcher import TemplateMatcher

        matcher = TemplateMatcher(mock_db_session)
        base = {"trimming": {"enabled": True, "threshold": -30}, "other": "value"}
        override = {"trimming": {"threshold": -40, "mode": "auto"}}

        # Act
        result = matcher._merge_configs(base, override)

        # Assert
        assert result["trimming"]["enabled"] is True  # Preserved
        assert result["trimming"]["threshold"] == -40  # Overridden
        assert result["trimming"]["mode"] == "auto"  # Added
        assert result["other"] == "value"  # Preserved

    def test_merge_configs_override_with_non_dict(self, mock_db_session):
        """Test overriding dict with non-dict value."""
        # Arrange
        from api.services.template_matcher import TemplateMatcher

        matcher = TemplateMatcher(mock_db_session)
        base = {"config": {"nested": "value"}}
        override = {"config": "simple_value"}

        # Act
        result = matcher._merge_configs(base, override)

        # Assert
        assert result["config"] == "simple_value"  # Replaced completely

    def test_merge_configs_empty_base(self, mock_db_session):
        """Test merge with empty base."""
        # Arrange
        from api.services.template_matcher import TemplateMatcher

        matcher = TemplateMatcher(mock_db_session)
        base = {}
        override = {"a": 1, "b": {"c": 2}}

        # Act
        result = matcher._merge_configs(base, override)

        # Assert
        assert result == override

    def test_merge_configs_empty_override(self, mock_db_session):
        """Test merge with empty override."""
        # Arrange
        from api.services.template_matcher import TemplateMatcher

        matcher = TemplateMatcher(mock_db_session)
        base = {"a": 1, "b": 2}
        override = {}

        # Act
        result = matcher._merge_configs(base, override)

        # Assert
        assert result == base
