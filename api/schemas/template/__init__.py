"""Template, config, source and preset schemas (fully typed)"""

from .config import BaseConfigCreate, BaseConfigResponse, BaseConfigUpdate
from .from_recording import TemplateFromRecordingRequest
from .input_source import (
    BatchSyncResponse,
    BulkSyncRequest,
    InputSourceCreate,
    InputSourceListItem,
    InputSourceResponse,
    InputSourceUpdate,
    SourceListResponse,
    SourceSyncResult,
)
from .matching_rules import MatchingRules
from .metadata_config import TemplateMetadataConfig, VKMetadataConfig, YouTubeMetadataConfig
from .operations import BulkDeleteResponse, RematchTaskResponse
from .output_config import TemplateOutputConfig
from .output_preset import (
    OutputPresetCreate,
    OutputPresetListItem,
    OutputPresetResponse,
    OutputPresetUpdate,
    PresetListResponse,
)
from .preset_metadata import (
    TopicsDisplayConfig,
    TopicsDisplayFormat,
    VKPresetMetadata,
    VKPrivacyLevel,
    YouTubeLicense,
    YouTubePresetMetadata,
    YouTubePrivacy,
)
from .processing_config import TemplateProcessingConfig, TranscriptionProcessingConfig
from .source_config import (
    GoogleDriveSourceConfig,
    LocalFileSourceConfig,
    SourceConfig,
    YandexDiskSourceConfig,
    ZoomSourceConfig,
)
from .sync import BulkSyncTaskResponse, SourceSyncTaskResponse, SyncSourceResponse, SyncTaskResponse
from .template import (
    RecordingTemplateCreate,
    RecordingTemplateListResponse,
    RecordingTemplateResponse,
    RecordingTemplateUpdate,
    TemplateListResponse,
)

__all__ = [
    "BaseConfigCreate",
    "BaseConfigResponse",
    "BaseConfigUpdate",
    "BatchSyncResponse",
    "BulkDeleteResponse",
    "BulkSyncRequest",
    "BulkSyncTaskResponse",
    "GoogleDriveSourceConfig",
    "InputSourceCreate",
    "InputSourceListItem",
    "InputSourceResponse",
    "InputSourceUpdate",
    "LocalFileSourceConfig",
    "MatchingRules",
    "OutputPresetCreate",
    "OutputPresetListItem",
    "OutputPresetResponse",
    "OutputPresetUpdate",
    "PresetListResponse",
    "RecordingTemplateCreate",
    "RecordingTemplateListResponse",
    "RecordingTemplateResponse",
    "RecordingTemplateUpdate",
    "RematchTaskResponse",
    "SourceConfig",
    "SourceListResponse",
    "SourceSyncResult",
    "SourceSyncTaskResponse",
    "SyncSourceResponse",
    "SyncTaskResponse",
    "TemplateFromRecordingRequest",
    "TemplateListResponse",
    "TemplateMetadataConfig",
    "TemplateOutputConfig",
    "TemplateProcessingConfig",
    "TopicsDisplayConfig",
    "TopicsDisplayFormat",
    "TranscriptionProcessingConfig",
    "VKMetadataConfig",
    "VKPresetMetadata",
    "VKPrivacyLevel",
    "YandexDiskSourceConfig",
    "YouTubeLicense",
    "YouTubeMetadataConfig",
    "YouTubePresetMetadata",
    "YouTubePrivacy",
    "ZoomSourceConfig",
]
