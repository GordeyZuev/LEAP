"""Failure handling service for processing tasks.

Handles status rollback, stage updates, and cascade skip logic.
Centralized logic following DRY principle.
"""

from datetime import UTC, datetime

from database.models import RecordingModel
from logger import get_logger
from models.recording import ProcessingStageStatus, ProcessingStageType, ProcessingStatus

logger = get_logger(__name__)


async def handle_download_failure(recording: RecordingModel, error: str) -> None:
    """
    Handle download failure: rollback to INITIALIZED or SKIPPED.

    Rollback logic:
    - If is_mapped=True → INITIALIZED (can retry download)
    - If is_mapped=False → SKIPPED (not mapped to template)

    Args:
        recording: RecordingModel instance
        error: Error message
    """
    if recording.is_mapped:
        recording.status = ProcessingStatus.INITIALIZED
    else:
        recording.status = ProcessingStatus.SKIPPED

    recording.failed = True
    recording.failed_at_stage = "download"
    recording.failed_reason = error[:1000]
    recording.failed_at = datetime.now(UTC)

    logger.error(
        f"Download failed for recording {recording.id}: rollback to {recording.status.value}, "
        f"error: {error[:200]}"
    )


async def handle_trim_failure(recording: RecordingModel, error: str) -> None:
    """
    Handle trim failure: rollback to DOWNLOADED, mark stage FAILED.

    Trim is critical - rollback to DOWNLOADED for manual intervention.

    Args:
        recording: RecordingModel instance
        error: Error message
    """
    recording.status = ProcessingStatus.DOWNLOADED
    recording.failed = True
    recording.failed_at_stage = "trim"
    recording.failed_reason = error[:1000]
    recording.failed_at = datetime.now(UTC)

    recording.mark_stage_failed(ProcessingStageType.TRIM, error[:1000])

    logger.error(
        f"Trim failed for recording {recording.id}: rollback to DOWNLOADED, "
        f"error: {error[:200]}"
    )


async def handle_transcribe_failure(
    recording: RecordingModel, stage_type: ProcessingStageType, error: str, allow_errors: bool
) -> None:
    """
    Handle transcription-related failure with allow_errors logic.

    Logic:
    - If allow_errors=True: skip stage + cascade skip dependents, continue to upload
    - If allow_errors=False: rollback to DOWNLOADED, mark as failed

    Args:
        recording: RecordingModel instance
        stage_type: Failed stage type (TRANSCRIBE, EXTRACT_TOPICS, GENERATE_SUBTITLES)
        error: Error message
        allow_errors: Allow continuation on error (from config)
    """
    if allow_errors:
        # Skip failed stage
        for stage in recording.processing_stages:
            if stage.stage_type == stage_type:
                stage.status = ProcessingStageStatus.SKIPPED
                stage.stage_meta = {"skip_reason": "error", "error": error[:500]}
                break

        # Cascade skip dependent stages
        _cascade_skip_dependent_stages(recording, stage_type)

        # Status → PROCESSED (continue to upload)
        from api.helpers.status_manager import update_aggregate_status

        update_aggregate_status(recording)

        # Mark as failed but allow continuation
        recording.failed = True
        recording.failed_at_stage = stage_type.value.lower()
        recording.failed_reason = f"Skipped due to error (allow_errors=True): {error[:500]}"

        logger.warning(
            f"Transcription stage {stage_type.value} failed for recording {recording.id}: "
            f"skipped with allow_errors=True, status={recording.status.value}"
        )
    else:
        # Rollback to DOWNLOADED
        recording.status = ProcessingStatus.DOWNLOADED
        recording.failed = True
        recording.failed_at_stage = stage_type.value.lower()
        recording.failed_reason = error[:1000]
        recording.failed_at = datetime.now(UTC)

        # Mark stage as FAILED
        recording.mark_stage_failed(stage_type, error[:1000])

        logger.error(
            f"Transcription stage {stage_type.value} failed for recording {recording.id}: "
            f"rollback to DOWNLOADED, error: {error[:200]}"
        )


def _cascade_skip_dependent_stages(recording: RecordingModel, parent_stage: ProcessingStageType) -> None:
    """
    Skip stages that depend on parent_stage.

    Current dependencies:
    - TRANSCRIBE → EXTRACT_TOPICS, GENERATE_SUBTITLES

    Args:
        recording: RecordingModel instance
        parent_stage: Parent stage that failed
    """
    dependencies = {
        ProcessingStageType.TRANSCRIBE: [ProcessingStageType.EXTRACT_TOPICS, ProcessingStageType.GENERATE_SUBTITLES]
    }

    dependent_stages = dependencies.get(parent_stage, [])

    for dep_stage_type in dependent_stages:
        # Find and skip dependent stage
        for stage in recording.processing_stages:
            if stage.stage_type == dep_stage_type:
                stage.status = ProcessingStageStatus.SKIPPED
                stage.stage_meta = {"skip_reason": "parent_failed", "parent_stage": parent_stage.value}
                logger.info(
                    f"Cascade skip: stage {dep_stage_type.value} skipped due to parent {parent_stage.value} failure"
                )
                break


async def handle_upload_failure(recording: RecordingModel, platform: str, error: str) -> None:
    """
    Handle upload failure: mark output as FAILED, recalculate status.

    Logic:
    - Mark specific output_target as FAILED
    - Recalculate aggregate status (may be UPLOADED if partial, or PROCESSED if all failed)
    - If all uploads failed → mark recording.failed=True

    Args:
        recording: RecordingModel instance
        platform: Platform that failed (youtube, vk)
        error: Error message
    """
    from models.recording import TargetStatus

    # Find and mark output target as FAILED
    target_found = False
    for output in recording.outputs:
        if output.target_type.value.lower() == platform.lower():
            output.status = TargetStatus.FAILED
            output.failed = True
            output.failed_reason = error[:1000]
            target_found = True
            logger.error(f"Upload to {platform} failed for recording {recording.id}: {error[:200]}")
            break

    if not target_found:
        logger.warning(f"Output target {platform} not found for recording {recording.id}")
        return

    # Recalculate aggregate status
    from api.helpers.status_manager import update_aggregate_status

    new_status = update_aggregate_status(recording)

    # If all uploads failed → mark recording as failed
    all_failed = all(o.status == TargetStatus.FAILED for o in recording.outputs)
    if all_failed:
        recording.failed = True
        recording.failed_at_stage = "upload"
        recording.status = ProcessingStatus.PROCESSED  # rollback from UPLOADING

        logger.error(f"All uploads failed for recording {recording.id}: rollback to PROCESSED")
    else:
        logger.info(f"Partial upload for recording {recording.id}: new status={new_status.value}")
