"""Recording to template matching service"""

from typing import Any, cast

from sqlalchemy.ext.asyncio import AsyncSession

from api.repositories.template_repos import RecordingTemplateRepository
from database.template_models import RecordingTemplateModel
from models import MeetingRecording


class TemplateMatcher:
    """Service for automatic recording-to-template matching."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = RecordingTemplateRepository(session)

    async def find_matching_template(
        self,
        recording: MeetingRecording,
        user_id: str,
    ) -> RecordingTemplateModel | None:
        """Find matching template for recording."""
        templates = await self.repo.find_active_by_user(user_id)

        for template in templates:
            if self._matches_template(recording, template):
                return template

        return None

    def _matches_template(
        self,
        recording: MeetingRecording,
        template: RecordingTemplateModel,
    ) -> bool:
        """Check if recording matches template."""
        if not template.matching_rules:
            return False

        from api.routers.input_sources import _find_matching_template

        matched = _find_matching_template(
            display_name=recording.display_name,
            source_id=recording.input_source_id or 0,
            templates=[template],
        )

        return matched is not None

    async def apply_template(
        self,
        recording: MeetingRecording,
        template: RecordingTemplateModel,
    ) -> MeetingRecording:
        """
        Apply template to recording.

        NOTE: metadata_config is no longer used - metadata is configured in output_preset.preset_metadata
        """
        if template.processing_config:
            recording.processing_preferences = self._merge_configs(
                recording.processing_preferences or {},
                cast("dict", template.processing_config),
            )

        if template.output_config:
            if recording.processing_preferences is None:
                recording.processing_preferences = {}
            recording.processing_preferences["output_config"] = template.output_config

        await self.repo.increment_usage(template)

        return recording

    def _merge_configs(self, base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
        """Deep merge configs (override takes precedence)."""
        result = base.copy()

        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._merge_configs(result[key], value)
            else:
                result[key] = value

        return result
