"""Thumbnail schemas"""

from pydantic import BaseModel, Field


class ThumbnailInfo(BaseModel):
    """Information about thumbnail."""

    name: str = Field(..., description="Name of file")
    url: str = Field(..., description="URL to get file via API")
    is_template: bool = Field(..., description="Is global template")
    size_bytes: int = Field(default=0, description="Size in bytes")
    size_kb: float = Field(default=0.0, description="Size in KB")
    modified_at: float = Field(default=0.0, description="Time of last modification (timestamp)")


class ThumbnailListResponse(BaseModel):
    """List of thumbnails of user."""

    thumbnails: list[ThumbnailInfo] = Field(
        default_factory=list,
        description="Thumbnails of user (including copies of templates, obtained during registration)",
    )


class ThumbnailUploadResponse(BaseModel):
    """Result of loading thumbnail."""

    message: str = Field(..., description="Message about result")
    thumbnail: ThumbnailInfo = Field(..., description="Information about loaded thumbnail")
