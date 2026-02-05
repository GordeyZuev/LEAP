"""Recording request schemas"""

from datetime import date

from pydantic import BaseModel, ConfigDict, Field, model_validator

from api.schemas.processing.preferences import ProcessingPreferences
from api.schemas.recording.filters import RecordingFilters
from api.schemas.validators import DateRangeMixin


class ProcessRecordingRequest(BaseModel):
    """Request for processing recording."""

    transcription_model: str = Field("fireworks", description="Transcription model")
    granularity: str = Field("long", description="Topic extraction detail level (short/long)")
    topic_model: str = Field("deepseek", description="Topic extraction model")
    platforms: list[str] = Field(default_factory=list, description="Upload platforms")
    no_transcription: bool = Field(False, description="Skip transcription")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "transcription_model": "fireworks",
                "granularity": "long",
                "topic_model": "deepseek",
                "platforms": ["youtube"],
                "no_transcription": False,
            }
        }
    )


class DateRangeRequest(BaseModel, DateRangeMixin):
    """Base request with date range."""

    from_date: date | None = Field(
        None,
        description="Start date. Formats: YYYY-MM-DD, DD/MM/YYYY, DD-MM-YYYY",
        examples=["2025-12-01", "01/12/2025", "01-12-2025"],
    )
    to_date: date | None = Field(
        None,
        description="End date (inclusive). If not specified - until now",
        examples=["2026-01-31", "31/01/2026"],
    )
    last_days: int | None = Field(
        None,
        ge=0,
        le=365,
        description="Last N days. Overrides from_date/to_date. 0 = today only",
        examples=[7, 14, 30],
    )

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {"last_days": 10},
                {"from_date": "2025-12-01", "to_date": "2026-01-31"},
                {"from_date": "01/12/2025"},
            ]
        }
    )


class BatchProcessRequest(DateRangeRequest):
    """Request for batch processing."""

    select_all: bool = Field(False, description="Process all found recordings")
    recording_ids: list[int] | None = Field(
        None, description="List of specific recording IDs. If specified - ignores dates"
    )
    platforms: list[str] = Field(default_factory=list, description="Upload platforms (youtube, vk)")
    no_transcription: bool = Field(False, description="Skip transcription")

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {"last_days": 7, "platforms": ["youtube"], "no_transcription": False},
                {"recording_ids": [1, 2, 3], "platforms": ["youtube", "vk"]},
            ]
        }
    )


class GenerateSubtitlesRequest(BaseModel):
    """Request for subtitle generation."""

    recording_ids: list[int] = Field(..., description="Recording IDs", min_length=1)
    formats: list[str] = Field(default=["srt", "vtt"], description="Subtitle formats")

    model_config = ConfigDict(json_schema_extra={"example": {"recording_ids": [1, 2, 3], "formats": ["srt", "vtt"]}})


class UploadRecordingsRequest(BaseModel):
    """Request for uploading recordings."""

    recording_ids: list[int] = Field(..., description="Recording IDs", min_length=1)
    platforms: list[str] = Field(..., description="Upload platforms (youtube, vk)", min_length=1)
    upload_captions: bool | None = Field(None, description="Upload captions. Default from config")

    model_config = ConfigDict(
        json_schema_extra={"example": {"recording_ids": [1, 2, 3], "platforms": ["youtube"], "upload_captions": True}}
    )


class UpdateRecordingRequest(BaseModel):
    """Request for updating recording."""

    processing_preferences: ProcessingPreferences | None = Field(None, description="Processing preferences")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "processing_preferences": {
                    "enable_transcription": True,
                    "enable_subtitles": True,
                    "enable_topics": True,
                    "granularity": "long",
                    "transcription_model": "fireworks",
                    "topic_model": "deepseek",
                }
            }
        }
    )


# ============================================================================
# Bulk Operations - Base Classes
# ============================================================================


class BulkOperationRequest(BaseModel):
    """
    Base schema for all bulk operations.

    Supports two modes:
    1. Explicit list of recording_ids
    2. Automatic selection by filters

    Only one mode can be used at a time.
    """

    recording_ids: list[int] | None = Field(None, description="Explicit list of recording IDs", min_length=1)
    filters: RecordingFilters | None = Field(None, description="Filters for automatic selection")
    limit: int = Field(50, ge=1, le=200, description="Maximum recordings when using filters")

    @model_validator(mode="after")
    def validate_input(self):
        """Validate that either recording_ids or filters is specified."""
        if not self.recording_ids and not self.filters:
            raise ValueError("Specify recording_ids or filters")
        if self.recording_ids and self.filters:
            raise ValueError("Specify only recording_ids OR filters, not both")
        return self

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {"recording_ids": [1, 2, 3, 4, 5]},
                {
                    "filters": {
                        "template_id": 5,
                        "status": ["INITIALIZED"],
                        "is_mapped": True,
                    },
                    "limit": 50,
                },
            ]
        }
    )


# ============================================================================
# Bulk Operations - Specific Request Schemas
# ============================================================================


class BulkDownloadRequest(BulkOperationRequest):
    """Bulk download recordings from Zoom."""

    force: bool = Field(False, description="Re-download if already downloaded")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "filters": {
                    "source_id": 10,
                    "status": ["INITIALIZED", "PENDING_SOURCE"],
                    "from_date": "2025-01-01",
                    "to_date": "2025-12-31",
                },
                "force": False,
                "limit": 50,
            }
        }
    )


class BulkTrimRequest(BulkOperationRequest):
    """Bulk video processing (FFmpeg - silence removal)."""

    silence_threshold: float = Field(-40.0, description="Silence threshold in dB")
    min_silence_duration: float = Field(2.0, description="Minimum silence duration in seconds")
    padding_before: float = Field(5.0, description="Padding before speech in seconds")
    padding_after: float = Field(5.0, description="Padding after speech in seconds")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "filters": {
                    "template_id": 5,
                    "status": ["DOWNLOADED"],
                    "from_date": "2025-12-01",
                    "to_date": "2025-12-31",
                },
                "silence_threshold": -35.0,
                "min_silence_duration": 2.0,
                "padding_before": 5.0,
                "padding_after": 5.0,
                "limit": 50,
            }
        }
    )


class BulkTranscribeRequest(BulkOperationRequest):
    """Bulk transcription of recordings."""

    use_batch_api: bool = Field(False, description="Use Fireworks Batch API (saves ~50%, but slower)")
    poll_interval: float = Field(10.0, description="Polling interval for Batch API (seconds)")
    max_wait_time: float = Field(3600.0, description="Maximum wait time for Batch API (seconds)")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "filters": {
                    "status": ["DOWNLOADED", "PROCESSED"],
                    "is_mapped": True,
                    "from_date": "2025-12-01",
                    "to_date": "2025-12-31",
                },
                "use_batch_api": True,
                "poll_interval": 10.0,
                "max_wait_time": 3600.0,
                "limit": 100,
            }
        }
    )


class BulkTopicsRequest(BulkOperationRequest):
    """Bulk topic extraction from transcriptions."""

    granularity: str = Field("long", description="Extraction mode ('short' - large topics | 'long' - detailed)")
    version_id: str | None = Field(None, description="Version ID (if not specified, generated automatically)")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "filters": {
                    "template_id": 5,
                    "status": ["PROCESSED"],
                },
                "granularity": "long",
                "version_id": None,
                "limit": 50,
            }
        }
    )


class BulkSubtitlesRequest(BulkOperationRequest):
    """Bulk subtitle generation."""

    formats: list[str] = Field(default=["srt", "vtt"], description="Subtitle formats to generate")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "filters": {
                    "template_id": 5,
                    "status": ["PROCESSED"],
                },
                "formats": ["srt", "vtt"],
                "limit": 50,
            }
        }
    )


class BulkUploadRequest(BulkOperationRequest):
    """Bulk upload recordings to platforms."""

    platforms: list[str] | None = Field(None, description="Upload platforms (youtube, vk). If None - from preset")
    preset_id: int | None = Field(None, description="Override preset ID for all recordings")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "filters": {
                    "template_id": 5,
                    "status": ["PROCESSED"],
                    "is_mapped": True,
                    "from_date": "2025-12-01",
                    "to_date": "2025-12-31",
                },
                "platforms": ["youtube", "vk"],
                "preset_id": None,
                "limit": 30,
            }
        }
    )


class BulkRunRequest(BulkOperationRequest):
    """Bulk full pipeline run (download → trim → transcribe → topics → upload)."""

    template_id: int | None = Field(None, description="Runtime template for all recordings")
    bind_template: bool = Field(False, description="Bind template to all recordings")
    processing_config: dict | None = Field(None, description="Override processing config for all recordings")
    metadata_config: dict | None = Field(None, description="Override metadata config for all recordings")
    output_config: dict | None = Field(None, description="Override output config for all recordings")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "template_id": 5,
                "bind_template": False,
                "filters": {
                    "template_id": 5,
                    "status": ["INITIALIZED"],
                    "is_mapped": True,
                    "failed": False,
                    "from_date": "2025-01-01",
                    "to_date": "2025-12-31",
                },
                "processing_config": {
                    "transcription": {
                        "enable_transcription": True,
                        "language": "ru",
                        "enable_topics": True,
                        "granularity": "long",
                    }
                },
                "metadata_config": {
                    "title_template": "{themes}",
                    "description_template": "{summary}\\n\\n{topics}",
                    "youtube": {
                        "playlist_id": "PLxxx",
                        "privacy": "unlisted",
                        "thumbnail_name": "python_base.png",
                    },
                    "vk": {
                        "album_id": "123456",
                        "group_id": 123456,
                        "thumbnail_name": "applied_python.png",
                        "privacy_view": 0,
                        "privacy_comment": 0,
                    },
                },
                "output_config": {
                    "preset_ids": [10],
                    "auto_upload": True,
                    "upload_captions": True,
                },
                "limit": 50,
            }
        }
    )


class BulkPauseRequest(BulkOperationRequest):
    """Bulk pause recordings."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {"recording_ids": [1, 2, 3]},
                {
                    "filters": {
                        "status": ["DOWNLOADING", "PROCESSING", "UPLOADING"],
                    },
                    "limit": 50,
                },
            ]
        }
    )


class BulkDeleteRequest(BulkOperationRequest):
    """Bulk soft delete recordings."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {"recording_ids": [1, 2, 3, 4, 5]},
                {
                    "filters": {
                        "failed": True,
                        "from_date": "2025-01-01",
                        "to_date": "2025-12-31",
                    },
                    "limit": 50,
                },
            ]
        }
    )
