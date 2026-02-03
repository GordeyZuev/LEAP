"""Automatic update of aggregated recording status from stages and outputs."""

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
    """Update and return aggregated recording status."""
    new_status = compute_aggregate_status(recording)
    recording.status = new_status
    return new_status


def should_allow_download(recording: RecordingModel) -> bool:
    """
    Check if recording download from source can be started.

    Download is allowed if:
    1. Recording in INITIALIZED status
    2. Not in download process (DOWNLOADING)
    """
    if recording.status in [ProcessingStatus.SKIPPED, ProcessingStatus.PENDING_SOURCE]:
        return False
    return recording.status == ProcessingStatus.INITIALIZED


def should_allow_run(recording: RecordingModel) -> bool:
    """Check if recording processing can be started (DOWNLOADED or PROCESSED status)."""
    if recording.status in [ProcessingStatus.SKIPPED, ProcessingStatus.PENDING_SOURCE]:
        return False
    return recording.status in [ProcessingStatus.DOWNLOADED, ProcessingStatus.PROCESSED]


def should_allow_transcription(recording: RecordingModel) -> bool:
    """Check if transcription can be started (PROCESSED status, no IN_PROGRESS stages)."""
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

    return transcribe_stage.status in [ProcessingStageStatus.PENDING, ProcessingStageStatus.FAILED]


def should_allow_upload(recording: RecordingModel, target_type: str) -> bool:
    """Check if upload to platform can be started (all stages complete, target not uploaded)."""
    if recording.failed or recording.deleted:
        return False

    if recording.status in [ProcessingStatus.SKIPPED, ProcessingStatus.PENDING_SOURCE, ProcessingStatus.EXPIRED]:
        return False

    if recording.status in [ProcessingStatus.INITIALIZED, ProcessingStatus.DOWNLOADING]:
        return False

    if recording.processing_stages:
        active_stages = [s for s in recording.processing_stages if s.status != ProcessingStageStatus.SKIPPED]
        if active_stages and not all(stage.status == ProcessingStageStatus.COMPLETED for stage in active_stages):
            return False

    target = next((o for o in recording.outputs if o.target_type == target_type), None)
    if target is None:
        return True

    return target.status in [TargetStatus.NOT_UPLOADED, TargetStatus.FAILED]
