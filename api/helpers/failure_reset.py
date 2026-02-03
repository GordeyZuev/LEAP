"""Helper for resetting failure flags on retry operations.

Provides centralized logic for clearing failure state when retrying failed operations.
Follows DRY principle - single source of truth for failure reset.
"""


from database.models import RecordingModel
from logger import get_logger

logger = get_logger(__name__)


def reset_recording_failure(recording: RecordingModel, stage: str | None = None) -> None:
    """Reset failure flags for recording retry."""
    if not recording.failed:
        return

    previous_stage = recording.failed_at_stage

    recording.failed = False
    recording.failed_at_stage = None
    recording.failed_reason = None
    recording.failed_at = None

    stage_info = f" {stage}" if stage else ""
    logger.info(f"Retry{stage_info} {recording.id} (was: {previous_stage})")


def should_reset_on_retry(recording: RecordingModel, expected_stage: str) -> bool:
    """Check if failure flags should be reset (only if failed at expected stage)."""
    return recording.failed and recording.failed_at_stage == expected_stage
