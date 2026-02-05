"""Recording-related schemas."""

from .filters import RecordingFilters
from .operations import (
    ConfigSaveResponse,
    DryRunResponse,
    MappingStatusResponse,
    PauseRecordingResponse,
    RecordingBulkOperationResponse,
    RecordingOperationResponse,
    TemplateInfoResponse,
)
from .request import (
    BulkDownloadRequest,
    BulkRunRequest,
    BulkSubtitlesRequest,
    BulkTopicsRequest,
    BulkTranscribeRequest,
    BulkTrimRequest,
    BulkUploadRequest,
)
from .response import (
    RecordingListResponse,
    RecordingResponse,
)

__all__ = [
    # Request schemas
    "BulkDownloadRequest",
    "BulkRunRequest",
    "BulkSubtitlesRequest",
    "BulkTopicsRequest",
    "BulkTranscribeRequest",
    "BulkTrimRequest",
    "BulkUploadRequest",
    "ConfigSaveResponse",
    # Operations schemas
    "DryRunResponse",
    "MappingStatusResponse",
    "PauseRecordingResponse",
    "RecordingBulkOperationResponse",
    # Filters
    "RecordingFilters",
    "RecordingListResponse",
    "RecordingOperationResponse",
    # Response schemas
    "RecordingResponse",
    "TemplateInfoResponse",
]
