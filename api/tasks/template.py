"""Celery tasks для работы с templates."""


from sqlalchemy import select

from api.celery_app import celery_app
from api.dependencies import get_async_session_maker
from api.repositories.template_repos import RecordingTemplateRepository
from api.routers.input_sources import _find_matching_template
from api.tasks.base import TemplateTask
from config.settings import get_settings
from database.models import RecordingModel
from logger import get_logger
from models.recording import ProcessingStatus

logger = get_logger()
settings = get_settings()


@celery_app.task(
    bind=True,
    base=TemplateTask,
    name="api.tasks.template.rematch_recordings",
    max_retries=settings.celery.task_default_max_retries,
    default_retry_delay=settings.celery.task_default_retry_delay,
)
def rematch_recordings_task(
    self,
    template_id: int,
    user_id: str,
    only_unmapped: bool = True,
) -> dict:
    """
    Re-match recordings after creation/update of template.

    Checks all SKIPPED recordings and updates those that matched to template.
    Updates is_mapped=True, template_id and status=INITIALIZED.

    Args:
        template_id: ID of template for matching
        user_id: ID of user
        only_unmapped: Check only unmapped (SKIPPED) recordings (default: True)

    Returns:
        Dictionary with results:
        - success: bool
        - checked: number of checked recordings
        - matched: number of matched recordings
        - updated: number of updated recordings
        - recordings: list of IDs of updated recordings
    """
    try:
        logger.info(
            f"[Task {self.request.id}] Starting re-match for template {template_id}, "
            f"user {user_id}, only_unmapped={only_unmapped}"
        )

        self.update_progress(user_id, 10, "Loading template...", step="rematch")

        # Use run_async for proper event loop isolation
        result = self.run_async(_async_rematch_recordings(self, template_id, user_id, only_unmapped))

        logger.info(
            f"[Task {self.request.id}] Re-match completed: "
            f"checked={result['checked']}, matched={result['matched']}, updated={result['updated']}"
        )

        return self.build_result(
            user_id=user_id,
            status="completed",
            result=result,
        )

    except Exception as exc:
        logger.error(f"[Task {self.request.id}] Error in re-match: {exc!r}", exc_info=True)
        raise self.retry(exc=exc)


async def _async_rematch_recordings(task_self, template_id: int, user_id: str, only_unmapped: bool) -> dict:
    """
    Async функция для re-match recordings.

    Args:
        task_self: Celery task instance
        template_id: ID template
        user_id: ID пользователя
        only_unmapped: Только unmapped recordings

    Returns:
        Dict с результатами
    """
    session_maker = get_async_session_maker()

    async with session_maker() as session:
        template_repo = RecordingTemplateRepository(session)

        task_self.update_progress(user_id, 20, "Loading template...", step="rematch")

        # Get template
        template = await template_repo.find_by_id(template_id, user_id)
        if not template:
            raise ValueError(f"Template {template_id} not found for user {user_id}")

        if not template.is_active or template.is_draft:
            raise ValueError(
                f"Template {template_id} is not active (is_active={template.is_active}, is_draft={template.is_draft})"
            )

        task_self.update_progress(
            user_id,
            30,
            "Loading recordings...",
            step="rematch",
            template_name=template.name,
        )

        # Get recordings for checking
        query = select(RecordingModel).where(RecordingModel.user_id == user_id)

        if only_unmapped:
            # Only unmapped (SKIPPED/PENDING_SOURCE) recordings
            query = query.where(
                RecordingModel.is_mapped == False,  # noqa: E712
                RecordingModel.status.in_([ProcessingStatus.SKIPPED, ProcessingStatus.PENDING_SOURCE]),
            )

        query = query.order_by(RecordingModel.created_at.desc())

        result = await session.execute(query)
        recordings = result.scalars().all()

        logger.info(f"[Re-match] Found {len(recordings)} recordings to check for template {template_id}")

        task_self.update_progress(
            user_id,
            40,
            f"Checking {len(recordings)} recordings...",
            step="rematch",
        )

        matched_count = 0
        updated_count = 0
        updated_recording_ids = []

        for idx, recording in enumerate(recordings):
            # Check matching
            matched_template = _find_matching_template(
                display_name=recording.display_name,
                source_id=recording.input_source_id or 0,
                templates=[template],
            )

            if matched_template:
                matched_count += 1

                # Update recording only if it is unmapped
                if not recording.is_mapped:
                    old_status = recording.status
                    recording.is_mapped = True
                    recording.template_id = template.id

                    # Keep PENDING_SOURCE status if source is still processing
                    if old_status != ProcessingStatus.PENDING_SOURCE:
                        recording.status = ProcessingStatus.INITIALIZED
                        new_status = ProcessingStatus.INITIALIZED
                    else:
                        new_status = ProcessingStatus.PENDING_SOURCE

                    updated_count += 1
                    updated_recording_ids.append(recording.id)

                    logger.info(
                        f"[Re-match] Updated recording {recording.id} '{recording.display_name}': "
                        f"{old_status} → {new_status} (template={template.id})"
                    )

            # Update progress
            if idx % 10 == 0:
                progress = 40 + int((idx / len(recordings)) * 50)
                task_self.update_progress(
                    user_id,
                    progress,
                    f"Checked {idx}/{len(recordings)} recordings...",
                    step="rematch",
                    matched_so_far=matched_count,
                )

        # Save changes
        if updated_count > 0:
            task_self.update_progress(user_id, 95, "Saving changes...", step="rematch")

            await session.commit()

            logger.info(f"[Re-match] Committed {updated_count} updates for template {template_id}")

        return {
            "success": True,
            "template_id": template_id,
            "template_name": template.name,
            "checked": len(recordings),
            "matched": matched_count,
            "updated": updated_count,
            "recordings": updated_recording_ids,
        }
