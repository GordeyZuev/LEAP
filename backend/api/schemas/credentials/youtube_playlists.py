"""YouTube playlist management API schemas."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class YouTubePlaylist(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    title: str
    description: str = ""
    privacy_status: Literal["public", "private", "unlisted"] = "private"
    item_count: int = 0
    url: str


class YouTubePlaylistListResponse(BaseModel):
    items: list[YouTubePlaylist] = Field(default_factory=list)
    next_page_token: str | None = None
    total: int = 0


class YouTubePlaylistCreateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=150)
    description: str = Field("", max_length=5000)
    privacy_status: Literal["public", "private", "unlisted"] = "unlisted"

    @field_validator("title")
    @classmethod
    def title_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Playlist title must not be blank")
        return value


class YouTubePlaylistUpdateRequest(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=150)
    description: str | None = Field(None, max_length=5000)
    privacy_status: Literal["public", "private", "unlisted"] | None = None

    @field_validator("title")
    @classmethod
    def title_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("Playlist title must not be blank")
        return value
