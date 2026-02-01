from datetime import datetime
from enum import Enum
from typing import Any, TypeVar

from logger import get_logger

T = TypeVar("T", bound=Enum)
logger = get_logger(__name__)


def _normalize_enum(value: T | str, enum_class: type[T]) -> T:
    """Normalize enum value: if already Enum, return it, otherwise create from string."""
    return value if isinstance(value, enum_class) else enum_class(value)


class ProcessingStatus(Enum):
    """Processing statuses for video recording (aggregated status from processing_stages/outputs)"""

    PENDING_SOURCE = "PENDING_SOURCE"  # Pending processing on source (Zoom)
    INITIALIZED = "INITIALIZED"  # Initialized (loaded from Zoom API)
    DOWNLOADING = "DOWNLOADING"  # In progress of downloading (runtime)
    DOWNLOADED = "DOWNLOADED"  # Downloaded
    PROCESSING = "PROCESSING"  # In progress of any processing stage (aggregate for stages IN_PROGRESS)
    PROCESSED = "PROCESSED"  # All processing stages completed or skipped (aggregate)
    UPLOADING = "UPLOADING"  # In progress of uploading (runtime)
    UPLOADED = "UPLOADED"  # Uploaded to API
    READY = "READY"  # Ready (all stages completed, including upload)
    SKIPPED = "SKIPPED"  # Skipped
    EXPIRED = "EXPIRED"  # Expired (retention policy applied)
    # FAILED removed - using recording.failed (boolean) + failed_reason


class SourceType(Enum):
    """Type of video source."""

    ZOOM = "ZOOM"
    LOCAL_FILE = "LOCAL_FILE"
    GOOGLE_DRIVE = "GOOGLE_DRIVE"
    YOUTUBE = "YOUTUBE"
    OTHER = "OTHER"


class TargetType(Enum):
    """Type of output/publication."""

    YOUTUBE = "YOUTUBE"
    VK = "VK"
    LOCAL_STORAGE = "LOCAL_STORAGE"
    GOOGLE_DRIVE = "GOOGLE_DRIVE"
    OTHER = "OTHER"


class TargetStatus(Enum):
    """Statuses of uploading to output platforms."""

    NOT_UPLOADED = "NOT_UPLOADED"
    UPLOADING = "UPLOADING"
    UPLOADED = "UPLOADED"
    FAILED = "FAILED"


class ProcessingStageType(Enum):
    """Types of processing pipeline stages (detail for ProcessingStatus.PROCESSING/PROCESSED)."""

    TRIM = "TRIM"  # Video trimming (silence removal)
    TRANSCRIBE = "TRANSCRIBE"  # Transcription
    EXTRACT_TOPICS = "EXTRACT_TOPICS"  # Extraction of topics
    GENERATE_SUBTITLES = "GENERATE_SUBTITLES"  # Generation of subtitles
    # TRANSLATION = "TRANSLATION"  # Translation


class ProcessingStageStatus(Enum):
    """Statuses of individual processing stage."""

    PENDING = "PENDING"  # Pending
    IN_PROGRESS = "IN_PROGRESS"  # In progress
    COMPLETED = "COMPLETED"  # Completed successfully
    FAILED = "FAILED"  # Failed
    SKIPPED = "SKIPPED"  # Skipped (disabled in config)


class OutputTarget:
    """Individual output target (YouTube, VK, disk, etc.)."""

    def __init__(
        self,
        target_type: TargetType,
        status: TargetStatus = TargetStatus.NOT_UPLOADED,
        target_meta: dict[str, Any] | None = None,
        uploaded_at: datetime | None = None,
    ):
        self.target_type = target_type
        self.status = status
        self.target_meta: dict[str, Any] = target_meta or {}
        self.uploaded_at = uploaded_at

    def get_link(self) -> str | None:
        return self.target_meta.get("target_link") or self.target_meta.get("video_url")

    def mark_uploaded(self, link: str | None = None, meta: dict[str, Any] | None = None):
        if link:
            self.target_meta["target_link"] = link
        if meta:
            self.target_meta.update(meta)
        self.status = TargetStatus.UPLOADED
        self.uploaded_at = datetime.utcnow()


class ProcessingStage:
    """Individual processing stage (FSM model)."""

    def __init__(
        self,
        stage_type: ProcessingStageType,
        status: ProcessingStageStatus = ProcessingStageStatus.PENDING,
        failed: bool = False,
        failed_at: datetime | None = None,
        failed_reason: str | None = None,
        retry_count: int = 0,
        stage_meta: dict[str, Any] | None = None,
        completed_at: datetime | None = None,
    ):
        self.stage_type = stage_type
        self.status = status
        self.failed = failed
        self.failed_at = failed_at
        self.failed_reason = failed_reason
        self.retry_count = retry_count
        self.stage_meta: dict[str, Any] = stage_meta or {}
        self.completed_at = completed_at

    def mark_completed(self, meta: dict[str, Any] | None = None):
        """Mark stage as completed (FSM: transition to COMPLETED)."""
        self.status = ProcessingStageStatus.COMPLETED
        self.failed = False
        self.completed_at = datetime.utcnow()
        if meta:
            self.stage_meta.update(meta)

    def mark_in_progress(self):
        """Mark stage as in progress (FSM: transition to IN_PROGRESS)."""
        self.status = ProcessingStageStatus.IN_PROGRESS
        # Reset failed when new start
        if self.failed:
            self.failed = False

    def mark_failed(self, reason: str):
        """Mark stage as failed (FSM: transition to FAILED)."""
        self.status = ProcessingStageStatus.FAILED
        self.failed = True
        self.failed_at = datetime.utcnow()
        self.failed_reason = reason
        self.retry_count += 1

    def mark_skipped(self):
        """Mark stage as skipped (FSM: transition to SKIPPED)."""
        self.status = ProcessingStageStatus.SKIPPED

    def can_retry(self, max_retries: int = 2) -> bool:
        """Check if stage can be retried (FSM: check transitions)."""
        return self.failed and self.status == ProcessingStageStatus.FAILED and self.retry_count < max_retries

    def prepare_retry(self):
        """Prepare stage for retry (FSM: transition from FAILED to IN_PROGRESS)."""
        if not self.can_retry():
            raise ValueError(f"Cannot retry stage {self.stage_type.value}: retry limit exceeded")
        self.status = ProcessingStageStatus.IN_PROGRESS
        # failed_at and failed_reason are kept for history


class MeetingRecording:
    """
    Class for representing Zoom meeting recording

    Contains all necessary information about the recording and methods for managing the processing status.
    """

    def __init__(self, meeting_data: dict[str, Any]):
        self.db_id: int | None = None
        self.user_id: int | None = meeting_data.get("user_id")
        self.display_name: str = meeting_data.get("display_name") or meeting_data.get("topic", "")
        self.start_time: str = meeting_data.get("start_time", "")
        self.duration: int = meeting_data.get("duration", 0)
        self.status: ProcessingStatus = meeting_data.get("status", ProcessingStatus.INITIALIZED)
        self.is_mapped: bool = bool(meeting_data.get("is_mapped", False))
        self.expire_at: datetime | None = meeting_data.get("expire_at")

        self.failed: bool = bool(meeting_data.get("failed", False))
        self.failed_at: datetime | None = meeting_data.get("failed_at")
        self.failed_reason: str | None = meeting_data.get("failed_reason")
        self.failed_at_stage: str | None = meeting_data.get("failed_at_stage")
        self.retry_count: int = int(meeting_data.get("retry_count", 0))

        # Source
        source_type_raw = meeting_data.get("source_type") or SourceType.ZOOM.value
        self.source_type: SourceType = _normalize_enum(source_type_raw, SourceType)
        self.source_key: str = meeting_data.get("source_key") or str(meeting_data.get("id", ""))
        self.source_metadata: dict[str, Any] = meeting_data.get("source_metadata", {}) or {}

        # Files/paths (relative to media_dir)
        self.local_video_path: str | None = meeting_data.get("local_video_path")
        self.processed_video_path: str | None = meeting_data.get("processed_video_path")
        self.processed_audio_path: str | None = meeting_data.get("processed_audio_path")
        self.transcription_dir: str | None = meeting_data.get("transcription_dir")
        self.downloaded_at: datetime | None = meeting_data.get("downloaded_at")

        # Additional info about files and downloading (for Zoom sources)
        self.video_file_size: int | None = meeting_data.get("video_file_size")
        self.video_file_download_url: str | None = meeting_data.get("video_file_download_url")
        self.download_access_token: str | None = meeting_data.get("download_access_token")
        self.password: str | None = meeting_data.get("password")
        self.recording_play_passcode: str | None = meeting_data.get("recording_play_passcode")

        # Raw transcription and topics data
        self.transcription_info: Any | None = meeting_data.get("transcription_info")
        self.topic_timestamps: list[dict[str, Any]] | None = meeting_data.get("topic_timestamps")
        self.main_topics: list[str] | None = meeting_data.get("main_topics")

        # Processing settings
        self.processing_preferences: dict[str, Any] | None = meeting_data.get("processing_preferences")

        # Outputs
        raw_targets = meeting_data.get("output_targets", []) or []
        self.output_targets: list[OutputTarget] = []
        for raw in raw_targets:
            if isinstance(raw, OutputTarget):
                self.output_targets.append(raw)
            elif isinstance(raw, dict) and "target_type" in raw:
                try:
                    target_type = _normalize_enum(raw["target_type"], TargetType)
                    status_raw = raw.get("status", TargetStatus.NOT_UPLOADED)
                    status = _normalize_enum(status_raw, TargetStatus)
                    self.output_targets.append(
                        OutputTarget(
                            target_type=target_type,
                            status=status,
                            target_meta=raw.get("target_meta"),
                            uploaded_at=raw.get("uploaded_at"),
                        )
                    )
                except Exception as e:
                    logger.debug(f"Failed to parse output target: {e}")
                    continue

        self.meeting_id: str = (
            meeting_data.get("uuid", "")
            or meeting_data.get("id", "")
            or self.source_metadata.get("meeting_uuid", "")
            or self.source_metadata.get("meeting_id", "")
        )
        self.account: str = meeting_data.get("account", "default") or self.source_metadata.get("account", "default")
        self.part_index: int | None = meeting_data.get("part_index")
        self.total_visible_parts: int | None = meeting_data.get("total_visible_parts")

        raw_stages = meeting_data.get("processing_stages", []) or []
        self.processing_stages: list[ProcessingStage] = []
        for raw in raw_stages:
            if isinstance(raw, ProcessingStage):
                self.processing_stages.append(raw)
            elif isinstance(raw, dict) and "stage_type" in raw:
                try:
                    stage_type = _normalize_enum(raw["stage_type"], ProcessingStageType)
                    status_raw = raw.get("status", ProcessingStageStatus.PENDING)
                    status = _normalize_enum(status_raw, ProcessingStageStatus)
                    self.processing_stages.append(
                        ProcessingStage(
                            stage_type=stage_type,
                            status=status,
                            failed=bool(raw.get("failed", False)),
                            failed_at=raw.get("failed_at"),
                            failed_reason=raw.get("failed_reason"),
                            retry_count=int(raw.get("retry_count", 0)),
                            stage_meta=raw.get("stage_meta"),
                            completed_at=raw.get("completed_at"),
                        )
                    )
                except Exception as e:
                    logger.debug(f"Failed to parse processing stage: {e}")
                    continue

        self._process_recording_files(meeting_data.get("recording_files", []))

    def _process_recording_files(self, recording_files: list[dict[str, Any]]) -> None:
        """
        Processing recording files from Zoom API response.

        Args:
            recording_files: List of recording files from API
        """
        # Priorities for selecting MP4 file (higher priority means better)
        mp4_priorities = {
            "shared_screen_with_speaker_view": 3,  # Best option - screen + speaker
            "shared_screen": 2,  # Good option - only screen
            "active_speaker": 1,  # Basic option - only speaker
        }

        best_mp4_file = None
        best_priority = -1
        best_size = -1

        for file_data in recording_files:
            file_type = file_data.get("file_type", "")
            file_size = file_data.get("file_size", 0)
            download_url = file_data.get("download_url", "")
            recording_type = file_data.get("recording_type", "")
            download_access_token = file_data.get("download_access_token")

            if file_type == "MP4":
                priority = mp4_priorities.get(recording_type, 0)
                if priority > best_priority or (priority == best_priority and file_size > best_size):
                    best_priority = priority
                    best_size = file_size or 0
                    best_mp4_file = {
                        "file_size": file_size,
                        "download_url": download_url,
                        "recording_type": recording_type,
                        "download_access_token": download_access_token,
                    }

        if best_mp4_file:
            self.video_file_size = best_mp4_file["file_size"]
            self.video_file_download_url = best_mp4_file["download_url"]
            if best_mp4_file.get("download_access_token"):
                self.download_access_token = best_mp4_file["download_access_token"]

    def update_status(
        self,
        new_status: ProcessingStatus,
        failed: bool = False,
        failed_reason: str | None = None,
        failed_at_stage: str | None = None,
    ) -> None:
        """
        Update recording status with support for FSM fields (ADR-015).

        Args:
            new_status: New status
            failed: Flag of error (if True, status is rolled back)
            failed_reason: Reason of error
            failed_at_stage: Stage, on which the error occurred
        """
        self.status = new_status
        if failed:
            self.failed = True
            self.failed_at = datetime.utcnow()
            if failed_reason:
                self.failed_reason = failed_reason
            if failed_at_stage:
                self.failed_at_stage = failed_at_stage
        else:
            # Reset failed when successful transition
            self.failed = False

    def mark_failure(
        self,
        reason: str,
        rollback_to_status: ProcessingStatus | None = None,
        failed_at_stage: str | None = None,
    ) -> None:
        """
        Mark recording as failed with rollback of status (ADR-015).

        Args:
            reason: Reason of error
            rollback_to_status: Status for rollback (if None, determined automatically)
            failed_at_stage: Stage, on which the error occurred
        """
        # Determine status for rollback
        if rollback_to_status is None:
            # Automatic determination of previous status
            if self.status == ProcessingStatus.DOWNLOADING:
                rollback_to_status = ProcessingStatus.INITIALIZED
            elif self.status == ProcessingStatus.PROCESSING:
                rollback_to_status = ProcessingStatus.DOWNLOADED
            elif self.status == ProcessingStatus.UPLOADING:
                # Rollback to PROCESSED
                rollback_to_status = ProcessingStatus.PROCESSED
            else:
                # If status is not in progress, leave as is
                rollback_to_status = self.status

        # Rollback status and set FSM fields
        self.status = rollback_to_status
        self.failed = True
        self.failed_at = datetime.utcnow()
        self.failed_reason = reason
        if failed_at_stage:
            self.failed_at_stage = failed_at_stage

    def has_video(self) -> bool:
        """Check if video file exists"""
        return self.video_file_download_url is not None

    def has_chat(self) -> bool:
        """Check if chat exists"""
        return False  # Not implemented yet

    def is_processed(self) -> bool:
        """Check if recording is processed"""
        return self.status in [ProcessingStatus.PROCESSED, ProcessingStatus.UPLOADED]

    def is_failed(self) -> bool:
        """
        Check if processing is failed (FSM: check failed flag).

        According to ADR-015, errors are processed through failed=true flag,
        not through status FAILED. When an error occurs, the status is rolled back to the previous stage.
        """
        return self.failed

    def is_long_enough(self, min_duration_minutes: int = 30) -> bool:
        """Check if recording is long enough"""
        return self.duration >= min_duration_minutes

    def is_downloaded(self) -> bool:
        """Check if recording is downloaded"""
        return self.status in [
            ProcessingStatus.DOWNLOADED,
            ProcessingStatus.PROCESSED,
            ProcessingStatus.UPLOADED,
        ]

    def is_ready_for_processing(self) -> bool:
        """Check if recording is ready for processing"""
        return self.status == ProcessingStatus.DOWNLOADED and self.local_video_path is not None

    def is_ready_for_upload(self) -> bool:
        """
        Check if recording is ready for upload.

        Recording is ready if:
        - Status PROCESSED
        - Processed video exists

        Note: Use should_allow_upload() from status_manager for complete validation.
        """
        return (
            self.status == ProcessingStatus.PROCESSED
            and self.processed_video_path is not None
        )

    # Working with targets
    def get_target(self, target_type: TargetType) -> OutputTarget | None:
        for target in self.output_targets:
            if target.target_type == target_type:
                return target
        return None

    def ensure_target(self, target_type: TargetType) -> OutputTarget:
        existing = self.get_target(target_type)
        if existing:
            return existing
        new_target = OutputTarget(target_type=target_type)
        self.output_targets.append(new_target)
        return new_target

    # Working with processing stages (FSM)
    def get_stage(self, stage_type: ProcessingStageType) -> ProcessingStage | None:
        """Get processing stage by type."""
        for stage in self.processing_stages:
            if stage.stage_type == stage_type:
                return stage
        return None

    def ensure_stage(self, stage_type: ProcessingStageType) -> ProcessingStage:
        """Create or get processing stage."""
        existing = self.get_stage(stage_type)
        if existing:
            return existing
        new_stage = ProcessingStage(stage_type=stage_type)
        self.processing_stages.append(new_stage)
        return new_stage

    def mark_stage_completed(self, stage_type: ProcessingStageType, meta: dict[str, Any] | None = None) -> None:
        """Mark stage as completed (FSM: successful transition)."""
        stage = self.ensure_stage(stage_type)
        stage.mark_completed(meta=meta)
        # Note: Aggregate status should be updated via status_manager.update_aggregate_status()

    def mark_stage_in_progress(self, stage_type: ProcessingStageType) -> None:
        """Mark stage as in progress (FSM: transition to IN_PROGRESS)."""
        stage = self.ensure_stage(stage_type)
        stage.mark_in_progress()
        # Note: Aggregate status should be updated via status_manager.update_aggregate_status()

    def mark_stage_failed(
        self,
        stage_type: ProcessingStageType,
        reason: str,
        rollback_to_status: ProcessingStatus | None = None,
    ) -> None:
        """
        Mark stage as failed (FSM: transition to FAILED with rollback).

        Args:
            stage_type: Type of stage
            reason: Reason of error
            rollback_to_status: Status for rollback (if None, determined automatically)
        """
        stage = self.ensure_stage(stage_type)
        stage.mark_failed(reason)

        # Rollback aggregated status
        if rollback_to_status is None:
            rollback_to_status = self._get_previous_status_for_stage(stage_type)
        if rollback_to_status:
            self.status = rollback_to_status

        # Set FSM fields
        self.failed = True
        self.failed_at = datetime.utcnow()
        self.failed_reason = reason
        self.failed_at_stage = stage_type.value

    def mark_stage_skipped(self, stage_type: ProcessingStageType) -> None:
        """Mark stage as skipped (FSM: transition to SKIPPED)."""
        stage = self.ensure_stage(stage_type)
        stage.mark_skipped()
        # Note: Aggregate status should be updated via status_manager.update_aggregate_status()

    def can_retry_stage(self, stage_type: ProcessingStageType, max_retries: int = 2) -> bool:
        """Check if stage can be retried."""
        stage = self.get_stage(stage_type)
        if not stage:
            return False
        return stage.can_retry(max_retries=max_retries)

    def prepare_stage_retry(self, stage_type: ProcessingStageType) -> None:
        """Prepare stage for retry (FSM: transition from FAILED to IN_PROGRESS)."""
        stage = self.get_stage(stage_type)
        if not stage:
            raise ValueError(f"Stage {stage_type.value} not found")
        stage.prepare_retry()
        # Reset overall failed flag when retrying
        if self.failed_at_stage == stage_type.value:
            self.failed = False
        # Note: Aggregate status should be updated via status_manager.update_aggregate_status()

    def _get_previous_status_for_stage(self, stage_type: ProcessingStageType) -> ProcessingStatus | None:
        """
        Get previous status for rollback when stage fails (FSM logic).

        Args:
            stage_type: Type of stage, on which the error occurred

        Returns:
            Previous status for rollback
        """
        # All processing stages rollback to PROCESSED (or DOWNLOADED if no stages completed)
        stage_to_previous_status = {
            ProcessingStageType.TRIM: ProcessingStatus.DOWNLOADED,
            ProcessingStageType.TRANSCRIBE: ProcessingStatus.PROCESSED,
            ProcessingStageType.EXTRACT_TOPICS: ProcessingStatus.PROCESSED,
            ProcessingStageType.GENERATE_SUBTITLES: ProcessingStatus.PROCESSED,
        }

        return stage_to_previous_status.get(stage_type, ProcessingStatus.PROCESSED)

    def _update_aggregate_status(self) -> None:
        """
        DEPRECATED: Use status_manager.update_aggregate_status() instead.

        This method is kept for backward compatibility but should not be used.
        All status updates should go through status_manager.compute_aggregate_status()
        and status_manager.update_aggregate_status() for unified status logic.
        """
        # This method is deprecated - use status_manager.update_aggregate_status() instead
        return

    def get_primary_audio_path(self) -> str | None:
        """Get path to primary audio file."""
        if self.processed_audio_path:
            return self.processed_audio_path
        return None

    # Access to Zoom API metadata

    def get_zoom_metadata(self, key: str, default: Any = None) -> Any:
        """
        Get value from Zoom API metadata with fallback to zoom_api_response.

        Priority of search:
        1. Direct value in source_metadata (if exists)
        2. Value in zoom_api_response
        3. Value in zoom_api_details
        4. default

        Args:
            key: Key to search (e.g. 'share_url', 'account_id', 'host_id')
            default: Default value if key is not found

        Returns:
            Value from metadata or zoom_api_response, or default
        """
        if not self.source_metadata:
            return default

        # First check direct value in source_metadata
        if key in self.source_metadata:
            return self.source_metadata[key]

        # Then check in zoom_api_response
        zoom_response = self.source_metadata.get("zoom_api_response")
        if isinstance(zoom_response, dict) and key in zoom_response:
            return zoom_response[key]

        # And in zoom_api_details
        zoom_details = self.source_metadata.get("zoom_api_details")
        if isinstance(zoom_details, dict) and key in zoom_details:
            return zoom_details[key]

        return default

    @property
    def share_url(self) -> str | None:
        """Link to view recording in Zoom."""
        return self.get_zoom_metadata("share_url")

    @property
    def account_id(self) -> str | None:
        """ID of Zoom account."""
        return self.get_zoom_metadata("account_id")

    @property
    def host_id(self) -> str | None:
        """ID of meeting host."""
        return self.get_zoom_metadata("host_id")

    @property
    def timezone(self) -> str:
        """Timezone of meeting."""
        value = self.get_zoom_metadata("timezone")
        return value if value else "UTC"

    @property
    def total_size(self) -> int:
        """Total size of all recording files in bytes."""
        value = self.get_zoom_metadata("total_size")
        return value if value is not None else 0

    @property
    def recording_count(self) -> int:
        """Number of recording files."""
        value = self.get_zoom_metadata("recording_count")
        return value if value is not None else 0

    @property
    def auto_delete_date(self) -> str | None:
        """Date of automatic deletion of recording."""
        return self.get_zoom_metadata("auto_delete_date")

    @property
    def zoom_api_response(self) -> dict[str, Any] | None:
        """Full response from Zoom API (get_recordings)."""
        if not self.source_metadata:
            return None
        response = self.source_metadata.get("zoom_api_response")
        return response if isinstance(response, dict) else None

    @property
    def zoom_api_details(self) -> dict[str, Any] | None:
        """Full detailed response from Zoom API (get_recording_details)."""
        if not self.source_metadata:
            return None
        details = self.source_metadata.get("zoom_api_details")
        return details if isinstance(details, dict) else None

    def get_all_recording_files(self) -> list[dict[str, Any]]:
        """
        Get all recording files from zoom_api_response.

        Returns:
            List of all recording_files from full API response (including MP4, CHAT, TRANSCRIPT)
        """
        response = self.zoom_api_response
        if isinstance(response, dict):
            files = response.get("recording_files", [])
            return files if isinstance(files, list) else []
        return []

    def targets_summary(self) -> dict[str, Any]:
        summary = {}
        for target in self.output_targets:
            summary[target.target_type.value] = {
                "status": target.status.value,
                "link": target.get_link(),
            }
        return summary

    def get_processing_progress(self) -> dict[str, Any]:
        """
        Get information about processing progress.

        Returns:
            Dictionary with information about progress
        """
        progress = {
            "status": self.status.value,
            "downloaded": self.is_downloaded(),
            "processed": self.is_processed(),
        }

        # Add paths to files if they exist
        if self.local_video_path:
            progress["local_file"] = self.local_video_path
        if self.processed_video_path:
            progress["processed_file"] = self.processed_video_path
        if self.processed_audio_path:
            progress["processed_audio_path"] = self.processed_audio_path
        if self.transcription_dir:
            progress["transcription_dir"] = self.transcription_dir

        # Add information about transcription
        if self.topic_timestamps:
            progress["topics_count"] = len(self.topic_timestamps)
        if self.main_topics:
            progress["main_topics"] = self.main_topics

        # Add information about targets
        if self.output_targets:
            progress["outputs"] = self.targets_summary()

        return progress

    def reset_to_initial_state(self) -> None:
        """Reset recording to initial state"""
        self.local_video_path = None
        self.processed_video_path = None
        self.processed_audio_path = None
        self.downloaded_at = None
        self.transcription_dir = None
        self.topic_timestamps = None
        self.main_topics = None
