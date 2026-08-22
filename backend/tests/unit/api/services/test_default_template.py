"""Unit tests for default template helpers."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.services.default_template import promote_template_to_default


@pytest.mark.unit
class TestPromoteTemplateToDefault:
    @pytest.mark.asyncio
    async def test_swaps_default_flag(self) -> None:
        session = AsyncMock()
        target = MagicMock()
        target.id = 100
        target.is_default = False
        target.is_draft = False
        target.is_active = True

        current_default = MagicMock()
        current_default.id = 94
        current_default.is_default = True

        repo = MagicMock()
        repo.find_by_id = AsyncMock(return_value=target)
        repo.find_default_by_user = AsyncMock(return_value=current_default)
        repo.update = AsyncMock()
        session.execute = AsyncMock()
        session.flush = AsyncMock()

        with patch("api.repositories.template_repos.RecordingTemplateRepository", return_value=repo):
            result = await promote_template_to_default(session, "user-1", 100)

        assert result is target
        assert target.is_default is True
        session.execute.assert_awaited_once()
        repo.update.assert_awaited_once_with(target)

    @pytest.mark.asyncio
    async def test_rejects_draft(self) -> None:
        session = AsyncMock()
        target = MagicMock()
        target.is_default = False
        target.is_draft = True
        target.is_active = False

        repo = MagicMock()
        repo.find_by_id = AsyncMock(return_value=target)

        with patch("api.repositories.template_repos.RecordingTemplateRepository", return_value=repo):
            with pytest.raises(ValueError, match="draft"):
                await promote_template_to_default(session, "user-1", 100)

    @pytest.mark.asyncio
    async def test_rejects_inactive(self) -> None:
        session = AsyncMock()
        target = MagicMock()
        target.is_default = False
        target.is_draft = False
        target.is_active = False

        repo = MagicMock()
        repo.find_by_id = AsyncMock(return_value=target)

        with patch("api.repositories.template_repos.RecordingTemplateRepository", return_value=repo):
            with pytest.raises(ValueError, match="inactive"):
                await promote_template_to_default(session, "user-1", 100)

    @pytest.mark.asyncio
    async def test_rejects_already_default(self) -> None:
        session = AsyncMock()
        target = MagicMock()
        target.is_default = True

        repo = MagicMock()
        repo.find_by_id = AsyncMock(return_value=target)

        with patch("api.repositories.template_repos.RecordingTemplateRepository", return_value=repo):
            with pytest.raises(ValueError, match="already the base"):
                await promote_template_to_default(session, "user-1", 94)
