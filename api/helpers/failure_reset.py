"""Helper for resetting failure flags on retry operations.

Provides centralized logic for clearing failure state when retrying failed operations.
Follows DRY principle - single source of truth for failure reset.
"""


from database.models import RecordingModel
from logger import get_logger

logger = get_logger(__name__)


def reset_recording_failure(recording: RecordingModel, stage: str | None = None) -> None:
    """
    Reset failure flags for recording retry.

    Use cases:
    - Retry after download failure
    - Retry after processing failure
    - Retry after upload failure

    Args:
        recording: RecordingModel instance
        stage: Optional stage that is being retried (for logging)

    Example:
        ```python
        if recording.failed and recording.failed_at_stage == "download":
            reset_recording_failure(recording, stage="download")
            # Continue with retry logic
        ```
    """
    if not recording.failed:
        return  # Nothing to reset

    previous_stage = recording.failed_at_stage
    previous_reason = recording.failed_reason

    # Clear all failure flags
    recording.failed = False
    recording.failed_at_stage = None
    recording.failed_reason = None
    recording.failed_at = None

    # Log retry attempt
    stage_info = f" at stage '{stage}'" if stage else ""
    logger.info(
        f"Retrying recording {recording.id}{stage_info} after previous failure: "
        f"stage={previous_stage}, reason={previous_reason[:100] if previous_reason else 'N/A'}"
    )


def should_reset_on_retry(recording: RecordingModel, expected_stage: str) -> bool:
    """
    Check if failure flags should be reset for retry.

    Only reset if recording failed at the expected stage.
    Prevents accidental reset when retrying wrong stage.

    Args:
        recording: RecordingModel instance
        expected_stage: Expected failed_at_stage value

    Returns:
        True if should reset (failed at expected stage)

    Example:
        ```python
        if should_reset_on_retry(recording, "download"):
            reset_recording_failure(recording, "download")
        ```
    """
    return recording.failed and recording.failed_at_stage == expected_stage
