"""Helper for automatic update of aggregated recording status.

Main status (ProcessingStatus) is computed based on:
- processing_stages (detailed stages)
- outputs (upload targets)
"""

from datetime import UTC

from database.models import RecordingModel
from models.recording import (
    ProcessingStageStatus,
    ProcessingStatus,
    TargetStatus,
)


def compute_aggregate_status(recording: RecordingModel) -> ProcessingStatus:
    """
    Compute aggregated recording status from processing_stages and outputs.

    Priority logic:
    1. EXPIRED - if deleted and retention expired
    2. SKIPPED, PENDING_SOURCE - special statuses
    3. PROCESSING - any stage IN_PROGRESS (takes priority over base statuses)
    4. Base statuses (INITIALIZED, DOWNLOADING, DOWNLOADED)
    5. PROCESSED - all active stages COMPLETED or SKIPPED
    6. UPLOADING - any output UPLOADING
    7. READY - all outputs UPLOADED

    Args:
        recording: RecordingModel

    Returns:
        ProcessingStatus
    """
    from datetime import datetime

    current_status = recording.status

    # 1. Check EXPIRED first (terminal state)
    if recording.deleted and recording.deletion_reason == "expired":
        return ProcessingStatus.EXPIRED

    # Also check expire_at timestamp
    if recording.expire_at and recording.expire_at <= datetime.now(UTC):
        return ProcessingStatus.EXPIRED

    # 2. Check special statuses
    if current_status in [ProcessingStatus.SKIPPED, ProcessingStatus.PENDING_SOURCE]:
        return current_status

    # 3. Check for IN_PROGRESS stages first (takes priority over base statuses like DOWNLOADED)
    if recording.processing_stages:
        if any(s.status == ProcessingStageStatus.IN_PROGRESS for s in recording.processing_stages):
            return ProcessingStatus.PROCESSING

    # 4. Base statuses (no stages dependency)
    if current_status in [
        ProcessingStatus.INITIALIZED,
        ProcessingStatus.DOWNLOADING,
        ProcessingStatus.DOWNLOADED,
    ]:
        return current_status

    # 5. Check processing_stages for completion
    if recording.processing_stages:
        # 5.1. All stages COMPLETED or SKIPPED → PROCESSED
        # Filter out SKIPPED stages when checking completion
        active_stages = [s for s in recording.processing_stages if s.status != ProcessingStageStatus.SKIPPED]
        if active_stages and all(s.status == ProcessingStageStatus.COMPLETED for s in active_stages):
            # All active stages done, check outputs
            if recording.outputs:
                output_statuses = [output.status for output in recording.outputs]
                if any(status == TargetStatus.UPLOADING for status in output_statuses):
                    return ProcessingStatus.UPLOADING
                if all(status == TargetStatus.UPLOADED for status in output_statuses):
                    return ProcessingStatus.READY
            return ProcessingStatus.PROCESSED

        # 5.2. All stages PENDING or SKIPPED → PROCESSED (ready to start)
        if all(
            s.status in [ProcessingStageStatus.PENDING, ProcessingStageStatus.SKIPPED]
            for s in recording.processing_stages
        ):
            return ProcessingStatus.PROCESSED

    # 6. Check outputs for upload status
    if recording.outputs:
        output_statuses = [output.status for output in recording.outputs]

        # 6.1. At least one UPLOADING → UPLOADING
        if any(status == TargetStatus.UPLOADING for status in output_statuses):
            return ProcessingStatus.UPLOADING

        # 6.2. All UPLOADED → READY
        if all(status == TargetStatus.UPLOADED for status in output_statuses):
            return ProcessingStatus.READY

        # 6.3. Partial upload (some UPLOADED, some FAILED) → UPLOADED
        uploaded_count = sum(1 for status in output_statuses if status == TargetStatus.UPLOADED)
        if uploaded_count > 0 and uploaded_count < len(output_statuses):
            return ProcessingStatus.UPLOADED

        # 6.4. Mixed or NOT_UPLOADED → PROCESSED (ready to upload)
        return ProcessingStatus.PROCESSED

    # Default: PROCESSED (processing complete, no uploads configured)
    return ProcessingStatus.PROCESSED


def update_aggregate_status(recording: RecordingModel) -> ProcessingStatus:
    """
    Update aggregated recording status.

    Args:
        recording: RecordingModel

    Returns:
        New ProcessingStatus
    """
    new_status = compute_aggregate_status(recording)
    recording.status = new_status
    return new_status


def should_allow_download(recording: RecordingModel) -> bool:
    """
    Check if recording download from source can be started.

    Download is allowed if:
    1. Recording in INITIALIZED status
    2. Not in download process (DOWNLOADING)

    Args:
        recording: RecordingModel

    Returns:
        True if download is allowed
    """
    if recording.status in [ProcessingStatus.SKIPPED, ProcessingStatus.PENDING_SOURCE]:
        return False

    return recording.status == ProcessingStatus.INITIALIZED


def should_allow_run(recording: RecordingModel) -> bool:
    """
    Check if recording processing (run) can be started.

    Processing is allowed if:
    1. Recording in DOWNLOADED status (already downloaded)
    2. Not SKIPPED/PENDING_SOURCE

    Args:
        recording: RecordingModel

    Returns:
        True if processing is allowed
    """
    if recording.status in [ProcessingStatus.SKIPPED, ProcessingStatus.PENDING_SOURCE]:
        return False

    return recording.status in [ProcessingStatus.DOWNLOADED, ProcessingStatus.PROCESSED]


def should_allow_transcription(recording: RecordingModel) -> bool:
    """
    Check if transcription can be started for recording.

    Transcription is allowed if:
    1. Recording in PROCESSED status (basic processing complete)
    2. Not SKIPPED/PENDING_SOURCE
    3. No active processing_stages (IN_PROGRESS)
    4. TRANSCRIBE stage either absent or in PENDING or FAILED status

    Args:
        recording: RecordingModel

    Returns:
        True if transcription is allowed
    """
    if recording.status in [ProcessingStatus.SKIPPED, ProcessingStatus.PENDING_SOURCE]:
        return False

    if recording.status != ProcessingStatus.PROCESSED:
        return False

    if not recording.processing_stages:
        return True

    from models.recording import ProcessingStageType

    transcribe_stage = None
    for stage in recording.processing_stages:
        if stage.stage_type == ProcessingStageType.TRANSCRIBE:
            transcribe_stage = stage
            break

        if stage.status == ProcessingStageStatus.IN_PROGRESS:
            return False

    if transcribe_stage is None:
        return True

    return transcribe_stage.status in [
        ProcessingStageStatus.PENDING,
        ProcessingStageStatus.FAILED,
    ]


def should_allow_upload(recording: RecordingModel, target_type: str) -> bool:
    """
    Check if upload to platform can be started.

    Upload is allowed if:
    1. Recording not failed and not deleted
    2. Recording not in SKIPPED/PENDING_SOURCE/EXPIRED status
    3. Recording in status >= DOWNLOADED
    4. All processing_stages completed (COMPLETED or SKIPPED) or no stages
    5. Target for this platform either absent or NOT_UPLOADED or FAILED

    Args:
        recording: RecordingModel
        target_type: Platform type (TargetType value)

    Returns:
        True if upload is allowed
    """
    if recording.failed or recording.deleted:
        return False

    if recording.status in [
        ProcessingStatus.SKIPPED,
        ProcessingStatus.PENDING_SOURCE,
        ProcessingStatus.EXPIRED,
    ]:
        return False

    if recording.status in [ProcessingStatus.INITIALIZED, ProcessingStatus.DOWNLOADING]:
        return False

    if recording.processing_stages:
        # Filter out SKIPPED stages
        active_stages = [s for s in recording.processing_stages if s.status != ProcessingStageStatus.SKIPPED]
        if active_stages:
            all_completed = all(stage.status == ProcessingStageStatus.COMPLETED for stage in active_stages)
            if not all_completed:
                return False

    target = None
    for output in recording.outputs:
        if output.target_type == target_type:
            target = output
            break

    if target is None:
        return True

    return target.status in [TargetStatus.NOT_UPLOADED, TargetStatus.FAILED]
