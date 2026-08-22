"""Recording to template matching service"""

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
        """Find matching template for recording (excludes default template)."""
        templates = await self.repo.find_matchable_by_user(user_id)

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
        """Increment template usage counter.

        Binding is done via ``recording.template_id`` elsewhere; config is resolved at runtime
        from the template — not copied into ``processing_preferences``.
        """
        await self.repo.increment_usage(template)
        return recording
