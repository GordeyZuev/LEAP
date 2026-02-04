"""Typed schemas for various configuration types

These schemas are used for validation of config_data in BaseConfigModel.
"""

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class TrimmingConfigData(BaseModel):
    """Configuration for video trimming."""

    # Audio detection
    enable_trimming: bool = Field(True, description="Enable video trimming")
    audio_detection: bool = Field(True, description="Use audio detection")
    silence_threshold: float = Field(-40.0, ge=-60.0, le=0.0, description="Silence threshold in dB")
    min_silence_duration: float = Field(2.0, ge=0.1, description="Minimum silence duration (sec)")
    padding_before: float = Field(5.0, ge=0.0, description="Padding before audio (sec)")
    padding_after: float = Field(5.0, ge=0.0, description="Padding after audio (sec)")

    # Trimming
    remove_intro: bool = Field(False, description="Remove intro")
    remove_outro: bool = Field(False, description="Remove outro")
    intro_duration: float = Field(30.0, ge=0.0, description="Intro duration (sec)")
    outro_duration: float = Field(30.0, ge=0.0, description="Outro duration (sec)")

    # System settings (not changed by user)
    video_codec: str = Field("copy", description="Video codec")
    audio_codec: str = Field("copy", description="Audio codec")
    video_bitrate: str = Field("original", description="Video bitrate")
    audio_bitrate: str = Field("original", description="Audio bitrate")
    resolution: str = Field("original", description="Resolution")
    fps: int = Field(0, ge=0, description="FPS (0 = no change)")
    output_format: str = Field("mp4", description="Output file format")


class TranscriptionConfigData(BaseModel):
    """Configuration for transcription."""

    provider: Literal["fireworks", "deepseek"] = Field("fireworks", description="Transcription provider")
    model: str = Field("whisper-v3-turbo", description="Transcription model")
    language: str = Field("ru", description="Audio language")
    generate_subtitles: bool = Field(True, description="Generate subtitles")
    subtitle_formats: list[str] = Field(default_factory=lambda: ["srt", "vtt"], description="Subtitle formats")

    temperature: float = Field(0.0, ge=0.0, le=1.0, description="Model temperature")
    prompt: str | None = Field(None, description="Context prompt")

    @field_validator("subtitle_formats")
    @classmethod
    def validate_subtitle_formats(cls, v: list[str]) -> list[str]:
        """Validate subtitle formats."""
        allowed = ["srt", "vtt", "txt"]
        for fmt in v:
            if fmt not in allowed:
                raise ValueError(f"Unsupported subtitle format: {fmt}. Allowed: {allowed}")
        return v


class UploadConfigData(BaseModel):
    """Configuration for platform upload."""

    max_file_size_mb: int = Field(5000, ge=1, description="Maximum file size (MB)")
    supported_formats: list[str] = Field(
        default_factory=lambda: ["mp4", "avi", "mov", "mkv", "webm"], description="Supported formats"
    )
    retry_attempts: int = Field(3, ge=1, le=10, description="Retry attempts on error")
    retry_delay: int = Field(5, ge=0, description="Delay between retries (seconds)")
    default_privacy: Literal["private", "unlisted", "public"] = Field("unlisted", description="Default privacy")


class MappingRule(BaseModel):
    """Mapping rule for video titles."""

    pattern: str = Field(..., min_length=1, description="Pattern for matching")
    title_template: str = Field(..., min_length=1, description="Title template")
    thumbnail: str | None = Field(None, description="Thumbnail path")
    youtube_playlist_id: str | None = Field(None, description="YouTube playlist ID")
    vk_album_id: str | None = Field(None, description="VK album ID")


class VideoMappingConfigData(BaseModel):
    """Configuration for video title mapping."""

    mapping_rules: list[MappingRule] = Field(default_factory=list, description="Mapping rules")
    default_title_template: str = Field("{original_title} | {topic} ({date})", description="Default title template")
    default_thumbnail: str = Field("storage/shared/thumbnails/default.png", description="Default thumbnail")
    date_format: str = Field("DD.MM.YYYY", description="Date format")
    thumbnail_directory: str = Field(
        "storage/shared/thumbnails/", description="Directory for global template thumbnails"
    )

    @field_validator("mapping_rules")
    @classmethod
    def validate_mapping_rules(cls, v: list[MappingRule]) -> list[MappingRule]:
        """Validate mapping rules for duplicates."""
        patterns = [rule.pattern for rule in v]
        if len(patterns) != len(set(patterns)):
            raise ValueError("Duplicate patterns found in mapping rules")
        return v


class ZoomSyncConfigData(BaseModel):
    """Configuration for Zoom synchronization."""

    sync_mode: Literal["all", "recent", "specific"] = Field("recent", description="Synchronization mode")
    days_back: int = Field(30, ge=1, le=365, description="Days to sync back")
    include_trash: bool = Field(False, description="Include deleted recordings")
    auto_download: bool = Field(True, description="Auto-download files")
    download_quality: Literal["hd", "sd", "audio_only"] = Field("hd", description="Download quality")


class YandexDiskSyncConfigData(BaseModel):
    """Конфигурация для синхронизации Yandex Disk."""

    folder_path: str | None = Field(None, description="Path to folder on Yandex Disk")
    folder_url: str | None = Field(None, description="Public link to folder")
    recursive: bool = Field(False, description="Recursive folder traversal")
    file_patterns: list[str] = Field(default_factory=lambda: ["*.mp4"], description="File patterns")

    @field_validator("folder_path", "folder_url")
    @classmethod
    def validate_folder(cls, v: str | None, _info) -> str | None:
        """Validate folder path or URL."""
        return v

    def model_post_init(self, __context) -> None:
        """Validation after initialization."""
        if not self.folder_path and not self.folder_url:
            raise ValueError("Either folder_path or folder_url must be specified")


# Config type to schema mapping
CONFIG_TYPE_SCHEMAS: dict[str, type[BaseModel]] = {
    "trimming": TrimmingConfigData,
    "transcription": TranscriptionConfigData,
    "upload": UploadConfigData,
    "video_mapping": VideoMappingConfigData,
    "zoom_sync": ZoomSyncConfigData,
    "yandex_disk_sync": YandexDiskSyncConfigData,
}


def validate_config_by_type(config_type: str, config_data: dict[str, Any]) -> BaseModel:
    """
    Validate config_data by type.

    Args:
        config_type: Configuration type
        config_data: Configuration data

    Returns:
        Validated Pydantic model

    Raises:
        ValueError: If type is unknown or data is invalid
    """
    if config_type not in CONFIG_TYPE_SCHEMAS:
        raise ValueError(f"Unknown config type: {config_type}. Allowed: {list(CONFIG_TYPE_SCHEMAS.keys())}")

    schema_class = CONFIG_TYPE_SCHEMAS[config_type]
    return schema_class.model_validate(config_data)
