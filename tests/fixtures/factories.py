"""Factory functions for creating test data."""

from datetime import UTC, datetime
from unittest.mock import MagicMock

from models.recording import ProcessingStatus, SourceType, TargetStatus, TargetType


def create_mock_recording(
    record_id: int = 1,
    display_name: str = "Test Recording",
    user_id: str = "user_123",
    status: ProcessingStatus = ProcessingStatus.DOWNLOADED,
    template_id: int | None = None,
    input_source_id: int | None = None,
    is_mapped: bool = False,
    blank_record: bool = False,
    deleted: bool = False,
    failed: bool = False,
    **kwargs,
):
    """Create mock Recording object for testing."""
    recording = MagicMock()
    recording.id = record_id
    recording.display_name = display_name
    recording.user_id = user_id
    recording.status = status
    recording.template_id = template_id
    recording.input_source_id = input_source_id
    recording.is_mapped = is_mapped
    recording.blank_record = blank_record
    recording.deleted = deleted
    recording.failed = failed
    recording.on_pause = kwargs.get("on_pause", False)
    recording.pause_requested_at = kwargs.get("pause_requested_at")
    recording.start_time = kwargs.get("start_time", datetime.now(UTC))
    recording.duration = kwargs.get("duration", 3600)
    recording.local_video_path = kwargs.get("local_video_path")
    recording.processed_video_path = kwargs.get("processed_video_path")
    recording.processed_audio_path = kwargs.get("processed_audio_path")
    recording.transcription_dir = kwargs.get("transcription_dir")
    recording.video_file_size = kwargs.get("video_file_size")
    recording.failed_reason = kwargs.get("failed_reason")
    recording.failed_at_stage = kwargs.get("failed_at_stage")
    recording.created_at = kwargs.get("created_at", datetime.now(UTC))
    recording.updated_at = kwargs.get("updated_at", datetime.now(UTC))
    recording.deleted_at = kwargs.get("deleted_at")
    recording.delete_state = kwargs.get("delete_state", "active")
    recording.deletion_reason = kwargs.get("deletion_reason")
    recording.soft_deleted_at = kwargs.get("soft_deleted_at")
    recording.hard_delete_at = kwargs.get("hard_delete_at")
    recording.expire_at = kwargs.get("expire_at")

    # Mock relationships
    recording.template = kwargs.get("template")
    recording.source = kwargs.get("source")
    recording.input_source = kwargs.get("input_source")
    recording.owner = kwargs.get("owner")
    recording.outputs = kwargs.get("outputs", [])
    recording.processing_stages = kwargs.get("processing_stages", [])

    return recording


def create_mock_template(
    template_id: int = 1,
    name: str = "Test Template",
    user_id: str = "user_123",
    description: str | None = None,
    matching_rules: dict | None = None,
    processing_config: dict | None = None,
    metadata_config: dict | None = None,
    output_config: dict | None = None,
    is_draft: bool = False,
    is_active: bool = True,
    **kwargs,
):
    """Create mock RecordingTemplate object for testing."""
    template = MagicMock()
    template.id = template_id
    template.name = name
    template.user_id = user_id
    template.description = description
    template.matching_rules = matching_rules or {}
    template.processing_config = processing_config
    template.metadata_config = metadata_config
    template.output_config = output_config
    template.is_draft = is_draft
    template.is_active = is_active
    template.used_count = kwargs.get("used_count", 0)
    template.last_used_at = kwargs.get("last_used_at")
    template.created_at = kwargs.get("created_at", datetime.now(UTC))
    template.updated_at = kwargs.get("updated_at", datetime.now(UTC))

    return template


def create_mock_credential(
    credential_id: int = 1,
    user_id: str = "user_123",
    platform: str = "youtube",
    credential_data: dict | None = None,
    is_active: bool = True,
    **kwargs,
):
    """Create mock UserCredential object for testing."""
    credential = MagicMock()
    credential.id = credential_id
    credential.user_id = user_id
    credential.platform = platform
    credential.credential_data = credential_data or {}
    credential.is_active = is_active
    credential.created_at = kwargs.get("created_at", datetime.now(UTC))
    credential.updated_at = kwargs.get("updated_at", datetime.now(UTC))

    return credential


def create_mock_output_preset(
    preset_id: int = 1,
    name: str = "Test Preset",
    user_id: str = "user_123",
    platform: str = "youtube",
    credential_id: int = 1,
    preset_metadata: dict | None = None,
    is_active: bool = True,
    **kwargs,
):
    """Create mock OutputPreset object for testing."""
    preset = MagicMock()
    preset.id = preset_id
    preset.name = name
    preset.user_id = user_id
    preset.platform = platform
    preset.credential_id = credential_id
    preset.preset_metadata = preset_metadata or {}
    preset.is_active = is_active
    preset.created_at = kwargs.get("created_at", datetime.now(UTC))
    preset.updated_at = kwargs.get("updated_at", datetime.now(UTC))

    # Mock relationship
    preset.credential = kwargs.get("credential")

    return preset


def create_mock_input_source(
    source_id: int = 1,
    name: str = "Test Source",
    user_id: str = "user_123",
    source_type: str = "zoom",
    credential_id: int | None = None,
    config: dict | None = None,
    is_active: bool = True,
    **kwargs,
):
    """Create mock InputSource object for testing."""
    source = MagicMock()
    source.id = source_id
    source.name = name
    source.user_id = user_id
    source.source_type = source_type
    source.credential_id = credential_id
    source.config = config or {}
    source.is_active = is_active
    source.last_sync_at = kwargs.get("last_sync_at")
    source.created_at = kwargs.get("created_at", datetime.now(UTC))
    source.updated_at = kwargs.get("updated_at", datetime.now(UTC))

    # Mock relationship
    source.credential = kwargs.get("credential")

    return source


def create_mock_output_target(
    target_id: int = 1,
    recording_id: int = 1,
    user_id: str = "user_123",
    target_type: TargetType = TargetType.YOUTUBE,
    status: TargetStatus = TargetStatus.NOT_UPLOADED,
    target_meta: dict | None = None,
    preset_id: int | None = None,
    failed: bool = False,
    **kwargs,
):
    """Create mock OutputTarget object for testing."""
    target = MagicMock()
    target.id = target_id
    target.recording_id = recording_id
    target.user_id = user_id
    target.target_type = target_type
    target.status = status
    target.target_meta = target_meta or {}
    target.preset_id = preset_id
    target.failed = failed
    target.failed_reason = kwargs.get("failed_reason")
    target.failed_at = kwargs.get("failed_at")
    target.retry_count = kwargs.get("retry_count", 0)
    target.uploaded_at = kwargs.get("uploaded_at")
    target.created_at = kwargs.get("created_at", datetime.now(UTC))
    target.updated_at = kwargs.get("updated_at", datetime.now(UTC))

    # Mock relationship
    target.preset = kwargs.get("preset")

    return target


def create_mock_source_metadata(
    metadata_id: int = 1,
    recording_id: int = 1,
    user_id: str = "user_123",
    source_type: SourceType = SourceType.ZOOM,
    source_key: str = "test_key",
    meta: dict | None = None,
    input_source_id: int | None = None,
    **kwargs,
):
    """Create mock SourceMetadata object for testing."""
    source = MagicMock()
    source.id = metadata_id
    source.recording_id = recording_id
    source.user_id = user_id
    source.source_type = source_type
    source.source_key = source_key
    source.meta = meta or {}
    source.input_source_id = input_source_id
    source.created_at = kwargs.get("created_at", datetime.now(UTC))
    source.updated_at = kwargs.get("updated_at", datetime.now(UTC))

    # Mock relationship
    source.input_source = kwargs.get("input_source")

    return source


def create_mock_processing_stage(
    stage_id: int = 1,
    recording_id: int = 1,
    user_id: str = "user_123",
    stage_type: str = "download",
    status: str = "completed",
    failed: bool = False,
    **kwargs,
):
    """Create mock ProcessingStage object for testing."""
    stage = MagicMock()
    stage.id = stage_id
    stage.recording_id = recording_id
    stage.user_id = user_id
    stage.stage_type = MagicMock(value=stage_type)
    stage.status = MagicMock(value=status)
    stage.failed = failed
    stage.failed_reason = kwargs.get("failed_reason")
    stage.failed_at = kwargs.get("failed_at")
    stage.retry_count = kwargs.get("retry_count", 0)
    stage.completed_at = kwargs.get("completed_at")
    stage.stage_meta = kwargs.get("stage_meta", {})
    stage.created_at = kwargs.get("created_at", datetime.now(UTC))
    stage.updated_at = kwargs.get("updated_at", datetime.now(UTC))

    return stage
