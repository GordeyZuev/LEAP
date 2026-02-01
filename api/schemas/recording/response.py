"""Recording response schemas"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, computed_field

from api.schemas.common.pagination import PaginatedResponse
from models import ProcessingStageStatus, ProcessingStatus, SourceType, TargetStatus, TargetType


class SourceResponse(BaseModel):
    """Recording source metadata."""

    source_type: SourceType
    source_key: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class PresetInfo(BaseModel):
    """Output preset information."""

    id: int
    name: str


class OutputTargetResponse(BaseModel):
    """Output target platform configuration."""

    id: int
    target_type: TargetType
    status: TargetStatus
    target_meta: dict[str, Any] = Field(default_factory=dict)
    uploaded_at: datetime | None = None
    failed: bool = False
    failed_at: datetime | None = None
    failed_reason: str | None = None
    retry_count: int = 0
    preset: PresetInfo | None = None


class ProcessingStageResponse(BaseModel):
    """Processing stage status."""

    stage_type: str
    status: str
    failed: bool
    failed_at: datetime | None = None
    failed_reason: str | None = None
    retry_count: int = 0
    completed_at: datetime | None = None


class SourceInfo(BaseModel):
    """Source information for list view."""

    type: SourceType
    name: str | None = None
    input_source_id: int | None = None


class UploadInfo(BaseModel):
    """Upload information for single platform."""

    status: str
    url: str | None = None
    uploaded_at: datetime | None = None
    error: str | None = None


class ReadyToUploadMixin(BaseModel):
    """Mixin for computing ready_to_upload field."""

    status: ProcessingStatus
    failed: bool
    deleted: bool
    processing_stages: list[ProcessingStageResponse]

    @computed_field
    @property
    def ready_to_upload(self) -> bool:
        """Check if recording is ready to upload to platforms.

        Returns True when:
        - All active processing_stages are COMPLETED (ignores SKIPPED stages)
        - Status is DOWNLOADED or later (PROCESSING, PROCESSED, UPLOADING, etc.)
        - Not failed
        - Not deleted

        Note: This is a general readiness indicator. Server-side validation
        (should_allow_upload) performs additional checks for specific platforms.
        """
        if self.failed or self.deleted:
            return False

        if self.status not in [
            ProcessingStatus.DOWNLOADED,
            ProcessingStatus.PROCESSING,
            ProcessingStatus.PROCESSED,
            ProcessingStatus.UPLOADING,
            ProcessingStatus.READY,
        ]:
            return False

        if self.processing_stages:
            active_stages = [
                s for s in self.processing_stages if s.status != ProcessingStageStatus.SKIPPED.value
            ]

            if active_stages:
                all_completed = all(
                    stage.status == ProcessingStageStatus.COMPLETED.value for stage in active_stages
                )
                if not all_completed:
                    return False

        return True


class RecordingListItem(ReadyToUploadMixin):
    """Recording item for list view (optimized for UI table)."""

    id: int
    display_name: str
    start_time: datetime
    duration: int
    status: ProcessingStatus
    failed: bool
    failed_at_stage: str | None = None
    is_mapped: bool
    template_id: int | None = None
    template_name: str | None = None
    source: SourceInfo | None = None
    uploads: dict[str, UploadInfo] = Field(default_factory=dict)
    processing_stages: list[ProcessingStageResponse] = Field(default_factory=list)
    deleted: bool = False
    deleted_at: datetime | None = None
    delete_state: str = "active"
    deletion_reason: str | None = None
    soft_deleted_at: datetime | None = None
    hard_delete_at: datetime | None = None
    expire_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class RecordingResponse(ReadyToUploadMixin):
    """Full recording response with all details."""

    id: int
    display_name: str
    start_time: datetime
    duration: int
    status: ProcessingStatus
    is_mapped: bool
    blank_record: bool = Field(False, description="Whether recording is too short/small to process")
    processing_preferences: dict[str, Any] | None = None
    source: SourceResponse | None = None
    outputs: list[OutputTargetResponse] = Field(default_factory=list)
    processing_stages: list[ProcessingStageResponse] = Field(default_factory=list)
    failed: bool = False
    failed_at: datetime | None = None
    failed_reason: str | None = None
    failed_at_stage: str | None = None
    video_file_size: int | None = None
    deleted: bool = False
    deleted_at: datetime | None = None
    delete_state: str = "active"
    deletion_reason: str | None = None
    soft_deleted_at: datetime | None = None
    hard_delete_at: datetime | None = None
    expire_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    @computed_field
    @property
    def upload_summary(self) -> dict[str, Any] | None:
        """
        Compute upload summary for partial uploads.

        Returns summary when there are uploads (completed or failed):
        - total: total number of outputs
        - uploaded: successfully uploaded count
        - failed: failed upload count
        - partial: True if some uploaded and some failed

        Returns None if no outputs or all NOT_UPLOADED.
        """
        if not self.outputs:
            return None

        total = len(self.outputs)
        uploaded = sum(1 for o in self.outputs if o.status == TargetStatus.UPLOADED)
        failed = sum(1 for o in self.outputs if o.status == TargetStatus.FAILED)

        # Only return summary if there are actual uploads (completed or failed)
        if uploaded == 0 and failed == 0:
            return None

        return {"total": total, "uploaded": uploaded, "failed": failed, "partial": 0 < uploaded < total}

    class Config:
        from_attributes = True


class RecordingListResponse(PaginatedResponse):
    """Response with list of recordings (optimized for UI)."""

    items: list[RecordingListItem]


class RunRecordingResponse(BaseModel):
    """Response for run request."""

    message: str
    recording_id: int
    status: ProcessingStatus
    estimated_time: int | None = Field(None, description="Estimated time in seconds")
