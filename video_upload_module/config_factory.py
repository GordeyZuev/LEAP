"""
Minimal config factory for video upload module.

All configuration now comes from database (user_credentials table).
These classes are kept for internal video_upload_module structure only.
"""

from pydantic import BaseModel, Field


class YouTubeConfig(BaseModel):
    """YouTube upload configuration"""

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
    """VK upload configuration"""

    enabled: bool = True
    group_id: int | None = None
    access_token: str = ""
    privacy_view: int = 0
    privacy_comment: int = 0
    no_comments: bool = False
    repeat: bool = False
    album_id: int | None = None


class YouTubeUploadConfig(YouTubeConfig):
    """YouTube upload config (alias for compatibility)"""



class VKUploadConfig(VKConfig):
    """VK upload config (alias for compatibility)"""



class UploadConfig(BaseModel):
    """Generic upload configuration"""

    platform: str = Field(description="Platform name (youtube, vk)")
    enabled: bool = True


__all__ = [
    "UploadConfig",
    "VKConfig",
    "VKUploadConfig",
    "YouTubeConfig",
    "YouTubeUploadConfig",
]
