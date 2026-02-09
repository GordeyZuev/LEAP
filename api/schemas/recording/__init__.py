"""Recording-related schemas."""

from .filters import RecordingFilters
from .operations import (
    ConfigSaveResponse,
    ConfigUpdateResponse,
    DeleteRecordingResponse,
    DryRunResponse,
    MappingStatusResponse,
    PauseRecordingResponse,
    RecordingBulkDeleteResponse,
    RecordingBulkOperationResponse,
    RecordingConfigResponse,
    RecordingOperationResponse,
    ResetRecordingResponse,
    RestoreRecordingResponse,
    TemplateBindResponse,
    TemplateInfoResponse,
    TemplateUnbindResponse,
)
from .request import (
    BulkDeleteRequest,
    BulkDownloadRequest,
    BulkRunRequest,
    BulkSubtitlesRequest,
    BulkTopicsRequest,
    BulkTranscribeRequest,
    BulkTrimRequest,
    BulkUploadRequest,
    ConfigOverrideRequest,
    TrimVideoRequest,
)
from .response import (
    DetailedRecordingResponse,
    RecordingListItem,
    RecordingListResponse,
    RecordingResponse,
)

__all__ = [
    # Request schemas
    "BulkDeleteRequest",
    "BulkDownloadRequest",
    "BulkRunRequest",
    "BulkSubtitlesRequest",
    "BulkTopicsRequest",
    "BulkTranscribeRequest",
    "BulkTrimRequest",
    "BulkUploadRequest",
    "ConfigOverrideRequest",
    "ConfigSaveResponse",
    "ConfigUpdateResponse",
    "DeleteRecordingResponse",
    # Response schemas
    "DetailedRecordingResponse",
    # Operations schemas
    "DryRunResponse",
    "MappingStatusResponse",
    "PauseRecordingResponse",
    "RecordingBulkDeleteResponse",
    "RecordingBulkOperationResponse",
    "RecordingConfigResponse",
    # Filters
    "RecordingFilters",
    "RecordingListItem",
    "RecordingListResponse",
    "RecordingOperationResponse",
    "RecordingResponse",
    "ResetRecordingResponse",
    "RestoreRecordingResponse",
    "TemplateBindResponse",
    "TemplateInfoResponse",
    "TemplateUnbindResponse",
    "TrimVideoRequest",
]
