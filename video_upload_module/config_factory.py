"""Config classes for video upload module."""

from pydantic import BaseModel, Field


class YouTubeConfig(BaseModel):
    enabled: bool = True
    default_privacy: str = "unlisted"
    default_language: str = "ru"
    scopes: list[str] = Field(
        default_factory=lambda: [
            "https://www.googleapis.com/auth/youtube.upload",
            "https://www.googleapis.com/auth/youtube.force-ssl",
        ]
    )
    client_secrets_file: str = ""
    credentials_file: str = ""


class VKConfig(BaseModel):
    enabled: bool = True
    group_id: int | None = None
    access_token: str = ""
    privacy_view: int = 0
    privacy_comment: int = 0
    no_comments: bool = False
    repeat: bool = False
    album_id: int | None = None


class YouTubeUploadConfig(YouTubeConfig):
    pass


class VKUploadConfig(VKConfig):
    pass


class UploadConfig(BaseModel):
    platform: str = Field(description="Platform name (youtube, vk)")
    enabled: bool = True


__all__ = [
    "UploadConfig",
    "VKConfig",
    "VKUploadConfig",
    "YouTubeConfig",
    "YouTubeUploadConfig",
]
