"""Helper for syncing processing stages with config changes."""

from database.models import RecordingModel
from models.recording import ProcessingStageStatus, ProcessingStageType


async def sync_stages_with_config(
    recording: RecordingModel,
    processing_config: dict,
) -> None:
    """Mark disabled stages as SKIPPED based on config (only PENDING stages)."""
    if not recording.processing_stages:
        return

    trimming_config = processing_config.get("trimming", {})
    transcription_config = processing_config.get("transcription", {})

    for stage in recording.processing_stages:
        if stage.status != ProcessingStageStatus.PENDING:
            continue

        should_skip = False
        reason = None

        if stage.stage_type == ProcessingStageType.TRIM:
            if not trimming_config.get("enable_trimming", True):
                should_skip = True
                reason = "Trimming disabled in config"

        elif stage.stage_type == ProcessingStageType.TRANSCRIBE:
            if not transcription_config.get("enable_transcription", False):
                should_skip = True
                reason = "Transcription disabled in config"

        elif stage.stage_type == ProcessingStageType.EXTRACT_TOPICS:
            if not transcription_config.get("enable_topics", False):
                should_skip = True
                reason = "Topics disabled in config"

        elif stage.stage_type == ProcessingStageType.GENERATE_SUBTITLES:
            if not transcription_config.get("enable_subtitles", False):
                should_skip = True
                reason = "Subtitles disabled in config"

        if should_skip:
            stage.status = ProcessingStageStatus.SKIPPED
            stage.skip_reason = reason
