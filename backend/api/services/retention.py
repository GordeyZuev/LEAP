"""Retention deadlines.

Soft delete hides a recording and leaves its objects in the bucket. Hard delete
removes the recording prefix and the database row. ``hard_delete_at`` is counted
from ``deleted_at``, not from a separate file-cleanup delay.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

from logger import get_logger

logger = get_logger()

DELETE_STATES_DUE = frozenset({"soft", "hard"})


def hard_delete_deadline(deleted_at: datetime, hard_delete_days: int) -> datetime:
    """When a hidden recording is removed from storage and the database."""
    return deleted_at + timedelta(days=int(hard_delete_days))


def still_due_for_hard_delete(recording: Any, now: datetime) -> bool:
    """True when a refetched row should still be wiped.

    A restore that lands after the maintenance task has already listed ids
    clears ``deleted`` and ``hard_delete_at``. Legacy rows with
    ``delete_state='hard'`` stay eligible so they are not left in the database.
    """
    if getattr(recording, "delete_state", None) not in DELETE_STATES_DUE:
        return False
    deadline = recording.hard_delete_at
    if deadline is None or deadline >= now:
        return False
    if recording.delete_state == "hard":
        return True
    return bool(recording.deleted)


def effective_retention_exempt(override: bool | None, template_exempt: bool) -> bool:
    """Recording override wins. NULL follows the template."""
    if override is not None:
        return override
    return template_exempt


def retention_exempt_from_layers(*processing_configs: Any) -> bool:
    """Merge template flags in resolver order. A later explicit value wins."""
    exempt = False
    for processing_config in processing_configs:
        if not isinstance(processing_config, dict):
            continue
        transcription = processing_config.get("transcription")
        if isinstance(transcription, dict) and "retention_exempt" in transcription:
            exempt = bool(transcription["retention_exempt"])
    return exempt


def apply_retention_deadline(
    recording: Any, template_exempt: bool, user_config: dict, now: datetime | None = None
) -> None:
    """Set or clear auto-hide from the effective flag.

    An existing date is left in place. Turning protection on clears it. Turning
    protection off when there is no date starts the clock from now.
    """
    if recording.deleted:
        return
    moment = now or datetime.now(UTC)
    if effective_retention_exempt(recording.retention_exempt, template_exempt):
        recording.expire_at = None
        return
    if recording.expire_at is None:
        days = int((user_config.get("retention") or {}).get("auto_expire_days") or 90)
        recording.expire_at = moment + timedelta(days=days)


async def template_retention_flags(session: Any, recordings: list[Any]) -> dict[int, bool]:
    """Template flag for each recording: default template, then its bound template."""
    if not recordings:
        return {}
    from sqlalchemy import select

    from database.template_models import RecordingTemplateModel

    user_ids = {recording.user_id for recording in recordings if recording.user_id}
    if not user_ids:
        return {recording.id: False for recording in recordings}
    result = await session.execute(
        select(
            RecordingTemplateModel.user_id,
            RecordingTemplateModel.id,
            RecordingTemplateModel.is_default,
            RecordingTemplateModel.processing_config,
        ).where(RecordingTemplateModel.user_id.in_(user_ids))
    )
    default_by_user: dict[str, Any] = {}
    config_by_id: dict[int, Any] = {}
    for user_id, template_id, is_default, processing_config in result.all():
        config_by_id[template_id] = processing_config
        if is_default:
            default_by_user[user_id] = (template_id, processing_config)

    flags: dict[int, bool] = {}
    for recording in recordings:
        default_id, default_config = default_by_user.get(recording.user_id, (None, None))
        layers: list[Any] = [default_config]
        if recording.template_id and recording.template_id != default_id:
            layers.append(config_by_id.get(recording.template_id))
        flags[recording.id] = retention_exempt_from_layers(*layers)
    return flags


def revoke_pipeline(recording: Any) -> None:
    """Stop a running chain when the recording is hidden."""
    task_id = getattr(recording, "pipeline_task_id", None)
    if task_id:
        try:
            from api.celery_app import celery_app

            celery_app.control.revoke(task_id, terminate=False)
        except Exception as exc:
            logger.warning(f"Failed to revoke pipeline | rec={getattr(recording, 'id', None)} | error={exc}")
    recording.on_air = False
    recording.pipeline_task_id = None
