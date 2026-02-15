from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class TrimmingConfig(BaseModel):
    enable_trimming: bool = True
    audio_detection: bool = True
    silence_threshold: float = Field(default=-40.0, le=0.0, ge=-100.0)
    min_silence_duration: float = Field(default=2.0, ge=0.0)
    padding_before: float = Field(default=5.0, ge=0.0)
    padding_after: float = Field(default=5.0, ge=0.0)


class TranscriptionConfig(BaseModel):
    enable_transcription: bool = True
    provider: str = "fireworks"
    language: str = "ru"
    prompt: str = ""
    vocabulary: list[str] = Field(default_factory=list, description="Key terms for transcriber")
    temperature: float = Field(default=0.0, ge=0.0, le=1.0)
    allow_errors: bool = False
    enable_topics: bool = True
    granularity: Literal["short", "medium", "long"] = "long"
    enable_subtitles: bool = True
    enable_translation: bool = False
    translation_language: str = "en"


class DownloadConfig(BaseModel):
    auto_download: bool = False
    max_file_size_mb: int = Field(default=5000, gt=0)
    quality: Literal["high", "medium", "low"] = "high"
    retry_attempts: int = Field(default=3, ge=0, le=10)
    retry_delay: int = Field(default=5, ge=0)


class UploadConfig(BaseModel):
    auto_upload: bool = False
    upload_captions: bool = True
    default_platforms: list[str] = Field(default_factory=list)
    default_preset_ids: dict[str, int] = Field(default_factory=dict)


class TopicsDisplayConfig(BaseModel):
    enabled: bool = True
    max_count: int = Field(default=999, ge=1)
    min_length: int = Field(default=0, ge=0)
    max_length: int = Field(default=999, ge=1)
    display_location: Literal["description", "comment", "both"] = "description"
    format: Literal["numbered_list", "bullet_list", "plain"] = "numbered_list"
    separator: str = "\n"
    prefix: str = "Topics:"
    include_timestamps: bool = False

    @model_validator(mode="after")
    def validate_length_range(self):
        if self.max_length < self.min_length:
            raise ValueError("max_length must be >= min_length")
        return self


class MetadataConfig(BaseModel):
    title_template: str = "{display_name} | {topic} ({date})"
    description_template: str = "Recording from {date}"
    date_format: str = "DD.MM.YYYY"
    tags: list[str] = Field(default_factory=list)
    thumbnail_name: str | None = None
    category: str | None = None
    topics_display: TopicsDisplayConfig = Field(default_factory=TopicsDisplayConfig)


class RetentionConfig(BaseModel):
    soft_delete_days: int = Field(default=3, ge=1)
    hard_delete_days: int = Field(default=30, ge=1)
    auto_expire_days: int = Field(default=90, ge=1)

    @model_validator(mode="after")
    def validate_retention_logic(self):
        if self.hard_delete_days < self.soft_delete_days:
            raise ValueError("hard_delete_days must be >= soft_delete_days")
        return self


class YouTubePlatformSettings(BaseModel):
    enabled: bool = False
    default_privacy: Literal["public", "unlisted", "private"] = "unlisted"
    default_language: str = "ru"


class VKPlatformSettings(BaseModel):
    enabled: bool = False
    privacy_view: Literal[0, 1, 2, 3] = 0  # 0=all, 1=friends, 2=friends of friends, 3=only me
    privacy_comment: Literal[0, 1, 2, 3] = 1  # Who can comment
    no_comments: bool = False
    repeat: bool = False


# For backward compatibility and other platforms
class PlatformSettings(BaseModel):
    enabled: bool = False
    default_privacy: str | int = "unlisted"
    default_language: str = "ru"
    privacy_comment: str | int | None = None
    no_comments: bool | None = None
    repeat: bool | None = None


class UserConfigData(BaseModel):
    trimming: TrimmingConfig = Field(default_factory=TrimmingConfig)
    transcription: TranscriptionConfig = Field(default_factory=TranscriptionConfig)
    download: DownloadConfig = Field(default_factory=DownloadConfig)
    upload: UploadConfig = Field(default_factory=UploadConfig)
    metadata: MetadataConfig = Field(default_factory=MetadataConfig)
    retention: RetentionConfig = Field(default_factory=RetentionConfig)
    platforms: dict[str, YouTubePlatformSettings | VKPlatformSettings | PlatformSettings] = Field(default_factory=dict)


class UserConfigResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: str
    config_data: UserConfigData
    created_at: datetime
    updated_at: datetime


class UserConfigUpdate(BaseModel):
    trimming: TrimmingConfig | None = None
    transcription: TranscriptionConfig | None = None
    download: DownloadConfig | None = None
    upload: UploadConfig | None = None
    metadata: MetadataConfig | None = None
    retention: RetentionConfig | None = None
    platforms: dict[str, YouTubePlatformSettings | VKPlatformSettings | PlatformSettings] | None = None
