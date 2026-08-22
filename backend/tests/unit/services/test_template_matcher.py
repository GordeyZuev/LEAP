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
        from api.services.template_matcher import TemplateMatcher

        user_id = "user_123"
        matcher = TemplateMatcher(mock_db_session)

        recording = create_mock_recording(display_name="Python Advanced Course", user_id=user_id)

        mock_template = create_mock_template(
            template_id=1,
            name="Python Courses",
            user_id=user_id,
            matching_rules={"display_name_pattern": ".*Python.*"},
        )
        matcher.repo.find_matchable_by_user = AsyncMock(return_value=[mock_template])
        matcher._matches_template = MagicMock(return_value=True)

        result = await matcher.find_matching_template(recording, user_id)

        assert result is not None
        assert result.id == mock_template.id

    @pytest.mark.asyncio
    async def test_find_matching_template_no_match(self, mock_db_session):
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
        matcher.repo.find_matchable_by_user = AsyncMock(return_value=[mock_template])
        matcher._matches_template = MagicMock(return_value=False)

        result = await matcher.find_matching_template(recording, user_id)
        assert result is None

    @pytest.mark.asyncio
    async def test_find_matching_template_uses_matchable_repo(self, mock_db_session):
        from api.services.template_matcher import TemplateMatcher

        user_id = "user_123"
        matcher = TemplateMatcher(mock_db_session)
        recording = create_mock_recording(display_name="Python Course", user_id=user_id)
        mock_template = create_mock_template(template_id=1, user_id=user_id, is_draft=False, is_active=True)
        matcher.repo.find_matchable_by_user = AsyncMock(return_value=[mock_template])
        matcher._matches_template = MagicMock(return_value=True)

        result = await matcher.find_matching_template(recording, user_id)

        assert result is not None
        matcher.repo.find_matchable_by_user.assert_called_once_with(user_id)


@pytest.mark.unit
class TestApplyTemplate:
    @pytest.mark.asyncio
    async def test_apply_template_does_not_mutate_preferences(self, mock_db_session):
        from api.services.template_matcher import TemplateMatcher

        matcher = TemplateMatcher(mock_db_session)
        recording = create_mock_recording(record_id=1, user_id="user_123")
        recording.processing_preferences = {"trimming": {"enabled": False}}

        template = create_mock_template(
            template_id=1,
            user_id="user_123",
            processing_config={"trimming": {"enabled": True, "threshold": -40}},
            output_config={"auto_upload": True, "preset_ids": [1, 2]},
        )

        matcher.repo.increment_usage = AsyncMock()

        result = await matcher.apply_template(recording, template)

        assert result.processing_preferences == {"trimming": {"enabled": False}}
        assert "output_config" not in (result.processing_preferences or {})
        matcher.repo.increment_usage.assert_called_once_with(template)

    @pytest.mark.asyncio
    async def test_apply_template_increments_usage_counter(self, mock_db_session):
        from api.services.template_matcher import TemplateMatcher

        matcher = TemplateMatcher(mock_db_session)
        recording = create_mock_recording(record_id=1, user_id="user_123")
        template = create_mock_template(template_id=1, user_id="user_123")
        matcher.repo.increment_usage = AsyncMock()

        await matcher.apply_template(recording, template)

        matcher.repo.increment_usage.assert_called_once_with(template)
