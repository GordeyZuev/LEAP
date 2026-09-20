"""Typed schemas for input source config"""

from typing import Any, Literal

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

from api.schemas.common import BASE_MODEL_CONFIG
from api.schemas.common.validators import validate_regex_pattern
from utils.safe_http import (
    YANDEX_DISK_PUBLIC_SHARE_SUFFIXES,
    YTDLP_HOST_SUFFIXES,
    UnsafeUrlError,
    assert_allowlisted_https_url,
)
from yandex_disk_module.paths import normalize_disk_path


def _allowlisted_https(url: str, suffixes: tuple[str, ...]) -> str:
    try:
        return assert_allowlisted_https_url(url, suffixes)
    except UnsafeUrlError as exc:
        raise ValueError(str(exc)) from exc


class ZoomSourceConfig(BaseModel):
    model_config = BASE_MODEL_CONFIG

    user_id: str | None = Field(None, description="Zoom user ID for filtering (optional)")
    include_trash: bool = Field(False, description="Include deleted recordings")
    recording_type: Literal["cloud", "all"] = Field("cloud", description="Recording type: cloud or all")

    # Master Account support
    is_master_account: bool = Field(
        False,
        description="Sync recordings from multiple users (master + sub-accounts)",
    )
    user_emails: list[str] | None = Field(
        None,
        description=(
            "List of user emails to sync recordings from. "
            "Required if is_master_account=True. "
            "Example: ['admin@company.com', 'user1@company.com']"
        ),
        min_length=1,
    )

    @model_validator(mode="after")
    def validate_master_account(self):
        """Validate Master Account configuration."""
        if self.is_master_account and not self.user_emails:
            raise ValueError("Master Account source requires user_emails list")
        if not self.is_master_account and self.user_emails:
            raise ValueError("user_emails should only be set when is_master_account=True")
        return self


class MtsLinkSourceConfig(BaseModel):
    """Config for MTS Link ingestion (org API key + explicit lecturer emails).

    The credential is always organization-wide, so ``user_emails`` is what limits
    a sync to specific lecturers — without it a sync would pull the whole org.
    """

    model_config = BASE_MODEL_CONFIG

    user_emails: list[EmailStr] = Field(
        ...,
        description="Lecturer emails to sync recordings from (resolved to MTS Link user IDs)",
        examples=[["lecturer@example.com"]],
        min_length=1,
    )
    conversion_quality: Literal["720", "1080"] = Field("720", description="MP4 conversion quality")
    conversion_view: Literal["none", "chat", "questions", "minichat"] = Field(
        "none",
        description="What MTS Link bakes into the MP4 frame; 'none' keeps only presenter video",
    )
    fetch_chat: bool = Field(True, description="Save the session chat next to the video")
    fetch_session_files: bool = Field(True, description="Save session attachments (slides, PDFs) next to the video")


class GoogleDriveSourceConfig(BaseModel):
    model_config = BASE_MODEL_CONFIG

    folder_id: str = Field(..., description="Google Drive folder ID")
    recursive: bool = Field(True, description="Recursive search in subfolders")
    file_pattern: str | None = Field(
        None,
        description="Regex pattern for file filtering",
        examples=[".*\\.mp4$", "Lecture.*\\.mp4"],
    )

    @field_validator("file_pattern")
    @classmethod
    def validate_pattern(cls, v: str | None) -> str | None:
        return validate_regex_pattern(v, field_name="file_pattern")


class YandexDiskSourceConfig(BaseModel):
    model_config = BASE_MODEL_CONFIG

    folder_path: str | None = Field(
        None,
        description="Yandex Disk folder path (requires OAuth credential)",
        examples=["/Video/Lectures"],
    )
    public_url: str | None = Field(
        None,
        description="Public link to file/folder (no OAuth needed)",
        examples=["https://disk.yandex.ru/d/AbCdEf123"],
    )
    recursive: bool = Field(True, description="Recursive search in subfolders")
    file_pattern: str | None = Field(None, description="Regex pattern for file filtering")

    @field_validator("folder_path")
    @classmethod
    def normalize_folder_path(cls, v: str | None) -> str | None:
        if not v:
            return v
        return normalize_disk_path(v)

    @field_validator("public_url")
    @classmethod
    def validate_public_url(cls, v: str | None) -> str | None:
        if not v:
            return v
        return _allowlisted_https(v, YANDEX_DISK_PUBLIC_SHARE_SUFFIXES)

    @field_validator("file_pattern")
    @classmethod
    def validate_pattern(cls, v: str | None) -> str | None:
        return validate_regex_pattern(v, field_name="file_pattern")

    @model_validator(mode="after")
    def validate_source_mode(self):
        """Either folder_path (OAuth) or public_url, not both."""
        if not self.folder_path and not self.public_url:
            raise ValueError("Either folder_path or public_url must be provided")
        if self.folder_path and self.public_url:
            raise ValueError("Provide folder_path or public_url, not both")
        return self


class VideoUrlSourceConfig(BaseModel):
    """Config for yt-dlp based video sources (YouTube, VK, Rutube, etc.)."""

    model_config = BASE_MODEL_CONFIG

    url: str = Field(..., description="Video or playlist URL")
    video_platform: str | None = Field(
        None,
        description="Platform name (auto-detected if not set): youtube, vk, rutube, other",
    )
    is_playlist: bool = Field(False, description="Treat URL as playlist/channel")
    quality: Literal["best", "1080p", "720p", "480p"] = Field("best", description="Video quality preference")
    format_preference: Literal["mp4", "mp3", "audio", "any"] = Field(
        "mp4", description="Container format: mp4 (video), mp3/audio (audio only), any"
    )

    @field_validator("url")
    @classmethod
    def validate_video_url(cls, v: str) -> str:
        return _allowlisted_https(v, YTDLP_HOST_SUFFIXES)


class LocalFileSourceConfig(BaseModel):
    model_config = BASE_MODEL_CONFIG


SourceConfig = (
    ZoomSourceConfig
    | MtsLinkSourceConfig
    | GoogleDriveSourceConfig
    | YandexDiskSourceConfig
    | VideoUrlSourceConfig
    | LocalFileSourceConfig
)

_CONFIG_BY_PLATFORM: dict[str, type[BaseModel]] = {
    "ZOOM": ZoomSourceConfig,
    "MTS_LINK": MtsLinkSourceConfig,
    "GOOGLE_DRIVE": GoogleDriveSourceConfig,
    "YANDEX_DISK": YandexDiskSourceConfig,
    "VIDEO_URL": VideoUrlSourceConfig,
    "LOCAL": LocalFileSourceConfig,
}


def parse_source_config_for_platform(platform: str, config: Any) -> BaseModel:
    """Validate ``config`` as the schema for ``platform``.

    Untagged ``SourceConfig`` unions otherwise match ``ZoomSourceConfig`` (all
    fields optional, extra ignored) and silently drop ``url`` / ``public_url``.
    """
    if isinstance(config, BaseModel):
        config = config.model_dump(exclude_none=True)
    model = _CONFIG_BY_PLATFORM.get(str(platform).upper())
    if model is None:
        raise ValueError(f"Unknown source platform {platform}")
    return model.model_validate(config)
