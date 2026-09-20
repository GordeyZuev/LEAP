"""Failure handling service for processing tasks.

Handles status rollback, stage updates, and cascade skip logic.
Centralized logic following DRY principle.
"""

from datetime import UTC, datetime

from api.helpers.blank_record import BLANK_REASON_NO_SPEECH, apply_blank_record
from database.models import RecordingModel
from logger import format_details, format_status_change, get_logger
from models.recording import ProcessingStageStatus, ProcessingStageType, ProcessingStatus

logger = get_logger(__name__)


_POST_DOWNLOAD_STATUSES = frozenset(
    {
        ProcessingStatus.DOWNLOADED,
        ProcessingStatus.PROCESSING,
        ProcessingStatus.PROCESSED,
        ProcessingStatus.UPLOADING,
        ProcessingStatus.UPLOADED,
        ProcessingStatus.READY,
    }
)


async def handle_download_failure(recording: RecordingModel, error: str) -> None:
    """Handle download failure.

    A late Celery retry must not roll a finished (or in-flight post-download)
    recording back to SKIPPED/INITIALIZED — that hides existing storage files.
    """
    old_status = recording.status
    if old_status in _POST_DOWNLOAD_STATUSES:
        recording.status = old_status
    elif recording.local_video_path:
        recording.status = ProcessingStatus.DOWNLOADED
    else:
        recording.status = ProcessingStatus.INITIALIZED if recording.is_mapped else ProcessingStatus.SKIPPED
    recording.failed = True
    recording.failed_at_stage = "download"
    recording.failed_reason = error[:1000]
    recording.failed_at = datetime.now(UTC)

    status = recording.status
    logger.error(
        f"Download failed | {format_status_change('Recording', old_status, status)} | "
        f"{format_details(rec=recording.id)}"
    )


async def handle_trim_failure(recording: RecordingModel, error: str) -> None:
    """Handle trim failure: rollback to DOWNLOADED for manual intervention."""
    old_status = recording.status
    recording.status = ProcessingStatus.DOWNLOADED
    recording.failed = True
    recording.failed_at_stage = "trim"
    recording.failed_reason = error[:1000]
    recording.failed_at = datetime.now(UTC)
    recording.mark_stage_failed(ProcessingStageType.TRIM, error[:1000])

    logger.error(
        f"Trim failed | {format_status_change('Recording', old_status, ProcessingStatus.DOWNLOADED)} | "
        f"{format_details(rec=recording.id)}"
    )


def stage_error_may_skip(exc: BaseException) -> bool:
    """Quota and the soft time limit stay hard failures even when allow_errors is set."""
    from celery.exceptions import SoftTimeLimitExceeded

    from api.services.quota_service import QuotaExceededError

    hard = (SoftTimeLimitExceeded, QuotaExceededError)
    if isinstance(exc, hard):
        return False
    cause = exc.__cause__ or exc.__context__
    return not isinstance(cause, hard)


def _mark_stage_skipped(
    recording: RecordingModel,
    stage_type: ProcessingStageType,
    meta: dict,
    *,
    create: bool = True,
) -> None:
    if create:
        stage = recording._get_or_create_stage(stage_type)
    else:
        stage = next((item for item in recording.processing_stages if item.stage_type == stage_type), None)
        if stage is None:
            return
    stage.status = ProcessingStageStatus.SKIPPED
    stage.failed = False
    stage.stage_meta = meta


async def skip_stage_if_allow_errors(
    recording_id: int,
    user_id: str,
    stage_type: ProcessingStageType,
    error: str,
) -> bool:
    """Skip the stage when allow_errors is set. Leave on_air for the rest of the chain."""
    from api.dependencies import get_async_session_maker
    from api.repositories.recording_repos import RecordingRepository
    from api.services.config_utils import resolve_full_config

    async with get_async_session_maker()() as session:
        repo = RecordingRepository(session)
        recording = await repo.get_by_id(recording_id, user_id)
        if not recording:
            return False
        full_config, _ = await resolve_full_config(session, recording_id, user_id, manual_override=None)
        if not full_config.get("transcription", {}).get("allow_errors", False):
            return False
        await handle_transcribe_failure(recording, stage_type, error, allow_errors=True)
        await repo.update(recording)
        await session.commit()
        return True


async def handle_transcribe_failure(
    recording: RecordingModel, stage_type: ProcessingStageType, error: str, allow_errors: bool
) -> None:
    """Handle transcription failure with allow_errors logic: skip or rollback."""
    if allow_errors:
        _mark_stage_skipped(
            recording,
            stage_type,
            {"skip_reason": "error", "error": error[:500]},
        )
        _cascade_skip_dependent_stages(recording, stage_type)

        from api.helpers.status_manager import update_aggregate_status

        update_aggregate_status(recording)
        logger.warning(f"{stage_type.value} failed, skipped (allow_errors) | {format_details(rec=recording.id)}")
    else:
        old_status = recording.status
        recording.status = ProcessingStatus.DOWNLOADED
        recording.failed = True
        recording.failed_at_stage = stage_type.value.lower()
        recording.failed_reason = error[:1000]
        recording.failed_at = datetime.now(UTC)
        recording.mark_stage_failed(stage_type, error[:1000])

        logger.error(
            f"{stage_type.value} failed | {format_status_change('Recording', old_status, ProcessingStatus.DOWNLOADED)} | "
            f"{format_details(rec=recording.id)}"
        )


async def handle_empty_transcript(recording: RecordingModel) -> None:
    """No speech in ASR: mark blank and skip remaining transcript-dependent stages."""
    apply_blank_record(recording, True, reason=BLANK_REASON_NO_SPEECH, force_status_skip=True)
    for stage in recording.processing_stages:
        if stage.stage_type == ProcessingStageType.TRANSCRIBE:
            stage.status = ProcessingStageStatus.SKIPPED
            stage.stage_meta = {"skip_reason": "empty_transcript"}
            break
    _cascade_skip_dependent_stages(recording, ProcessingStageType.TRANSCRIBE)
    from api.helpers.status_manager import update_aggregate_status

    update_aggregate_status(recording)
    logger.info(f"Empty transcript treated as blank | {format_details(rec=recording.id)}")


def _cascade_skip_dependent_stages(recording: RecordingModel, parent_stage: ProcessingStageType) -> None:
    """Skip stages that depend on parent_stage (TRANSCRIBE → EXTRACT_TOPICS, GENERATE_SUBTITLES)."""
    dependencies = {
        ProcessingStageType.TRANSCRIBE: [ProcessingStageType.EXTRACT_TOPICS, ProcessingStageType.GENERATE_SUBTITLES]
    }

    for dep_stage_type in dependencies.get(parent_stage, []):
        _mark_stage_skipped(
            recording,
            dep_stage_type,
            {"skip_reason": "parent_failed", "parent_stage": parent_stage.value},
            create=False,
        )


async def handle_upload_failure(recording: RecordingModel, platform: str, error: str) -> None:
    """Handle upload failure: mark output as FAILED, recalculate status."""
    from models.recording import TargetStatus

    target_found = False
    for output in recording.outputs:
        if output.target_type.lower() == platform.lower():
            old_status = output.status
            output.status = TargetStatus.FAILED
            output.failed = True
            output.failed_reason = error[:1000]
            target_found = True
            logger.error(
                f"Upload failed | {format_status_change('Output', old_status, TargetStatus.FAILED)} | "
                f"{format_details(rec=recording.id, platform=platform)}"
            )
            break

    if not target_found:
        logger.warning(f"Output target not found | {format_details(rec=recording.id, platform=platform)}")
        return

    from api.helpers.status_manager import update_aggregate_status

    update_aggregate_status(recording)

    all_failed = all(o.status == TargetStatus.FAILED for o in recording.outputs)
    if all_failed:
        recording.failed = True
        recording.failed_at_stage = "upload"
        recording.status = ProcessingStatus.PROCESSED
        logger.error(f"All uploads failed | {format_details(rec=recording.id)}")
