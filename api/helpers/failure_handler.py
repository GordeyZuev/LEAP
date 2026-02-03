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
    """Handle download failure: rollback to INITIALIZED if mapped, else SKIPPED."""
    recording.status = ProcessingStatus.INITIALIZED if recording.is_mapped else ProcessingStatus.SKIPPED
    recording.failed = True
    recording.failed_at_stage = "download"
    recording.failed_reason = error[:1000]
    recording.failed_at = datetime.now(UTC)

    logger.error(f"Download failed {recording.id}: {recording.status.value}")


async def handle_trim_failure(recording: RecordingModel, error: str) -> None:
    """Handle trim failure: rollback to DOWNLOADED for manual intervention."""
    recording.status = ProcessingStatus.DOWNLOADED
    recording.failed = True
    recording.failed_at_stage = "trim"
    recording.failed_reason = error[:1000]
    recording.failed_at = datetime.now(UTC)
    recording.mark_stage_failed(ProcessingStageType.TRIM, error[:1000])

    logger.error(f"Trim failed {recording.id}")


async def handle_transcribe_failure(
    recording: RecordingModel, stage_type: ProcessingStageType, error: str, allow_errors: bool
) -> None:
    """Handle transcription failure with allow_errors logic: skip or rollback."""
    if allow_errors:
        for stage in recording.processing_stages:
            if stage.stage_type == stage_type:
                stage.status = ProcessingStageStatus.SKIPPED
                stage.stage_meta = {"skip_reason": "error", "error": error[:500]}
                break

        _cascade_skip_dependent_stages(recording, stage_type)

        from api.helpers.status_manager import update_aggregate_status

        update_aggregate_status(recording)

        recording.failed = True
        recording.failed_at_stage = stage_type.value.lower()
        recording.failed_reason = f"Skipped (allow_errors=True): {error[:500]}"

        logger.warning(f"{stage_type.value} failed {recording.id}: skipped, continue")
    else:
        recording.status = ProcessingStatus.DOWNLOADED
        recording.failed = True
        recording.failed_at_stage = stage_type.value.lower()
        recording.failed_reason = error[:1000]
        recording.failed_at = datetime.now(UTC)
        recording.mark_stage_failed(stage_type, error[:1000])

        logger.error(f"{stage_type.value} failed {recording.id}: rollback")


def _cascade_skip_dependent_stages(recording: RecordingModel, parent_stage: ProcessingStageType) -> None:
    """Skip stages that depend on parent_stage (TRANSCRIBE → EXTRACT_TOPICS, GENERATE_SUBTITLES)."""
    dependencies = {
        ProcessingStageType.TRANSCRIBE: [ProcessingStageType.EXTRACT_TOPICS, ProcessingStageType.GENERATE_SUBTITLES]
    }

    for dep_stage_type in dependencies.get(parent_stage, []):
        for stage in recording.processing_stages:
            if stage.stage_type == dep_stage_type:
                stage.status = ProcessingStageStatus.SKIPPED
                stage.stage_meta = {"skip_reason": "parent_failed", "parent_stage": parent_stage.value}
                break


async def handle_upload_failure(recording: RecordingModel, platform: str, error: str) -> None:
    """Handle upload failure: mark output as FAILED, recalculate status."""
    from models.recording import TargetStatus

    target_found = False
    for output in recording.outputs:
        if output.target_type.value.lower() == platform.lower():
            output.status = TargetStatus.FAILED
            output.failed = True
            output.failed_reason = error[:1000]
            target_found = True
            logger.error(f"Upload {platform} failed {recording.id}")
            break

    if not target_found:
        logger.warning(f"Output target {platform} not found {recording.id}")
        return

    from api.helpers.status_manager import update_aggregate_status

    update_aggregate_status(recording)

    all_failed = all(o.status == TargetStatus.FAILED for o in recording.outputs)
    if all_failed:
        recording.failed = True
        recording.failed_at_stage = "upload"
        recording.status = ProcessingStatus.PROCESSED
        logger.error(f"All uploads failed {recording.id}")
