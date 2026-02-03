"""Template, config, source and preset schemas (fully typed)"""

from .config import BaseConfigCreate, BaseConfigResponse, BaseConfigUpdate
from .input_source import (
    BatchSyncResponse,
    BulkSyncRequest,
    InputSourceCreate,
    InputSourceResponse,
    InputSourceUpdate,
    SourceSyncResult,
)
from .matching_rules import MatchingRules
from .metadata_config import TemplateMetadataConfig, VKMetadataConfig, YouTubeMetadataConfig
from .operations import BulkDeleteResponse, RematchTaskResponse
from .output_config import TemplateOutputConfig
from .output_preset import OutputPresetCreate, OutputPresetResponse, OutputPresetUpdate
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
from .sync import SyncSourceResponse, SyncTaskResponse
from .template import (
    RecordingTemplateCreate,
    RecordingTemplateListResponse,
    RecordingTemplateResponse,
    RecordingTemplateUpdate,
)

__all__ = [
    "BaseConfigCreate",
    "BaseConfigResponse",
    "BaseConfigUpdate",
    "BatchSyncResponse",
    "BulkDeleteResponse",
    "BulkSyncRequest",
    "GoogleDriveSourceConfig",
    "InputSourceCreate",
    "InputSourceResponse",
    "InputSourceUpdate",
    "LocalFileSourceConfig",
    "MatchingRules",
    "OutputPresetCreate",
    "OutputPresetResponse",
    "OutputPresetUpdate",
    "RecordingTemplateCreate",
    "RecordingTemplateListResponse",
    "RecordingTemplateResponse",
    "RecordingTemplateUpdate",
    "RematchTaskResponse",
    "SourceConfig",
    "SourceSyncResult",
    "SyncSourceResponse",
    "SyncTaskResponse",
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
