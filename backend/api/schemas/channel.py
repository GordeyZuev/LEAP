"""Pydantic schemas for LEAP channels."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from api.helpers.channel_slug import validate_channel_slug
from api.schemas.common import BASE_MODEL_CONFIG, ORM_MODEL_CONFIG, strip_and_validate_name
from api.schemas.common.pagination import PaginatedResponse


class ChannelCreate(BaseModel):
    model_config = BASE_MODEL_CONFIG

    name: str = Field(..., min_length=1, max_length=200)
    slug: str | None = Field(None, min_length=5, max_length=64)
    description: str | None = Field(None, max_length=4000)

    @field_validator("name", mode="before")
    @classmethod
    def strip_name(cls, v: str) -> str:
        return strip_and_validate_name(v)

    @field_validator("slug", mode="before")
    @classmethod
    def normalize_slug(cls, v: str | None) -> str | None:
        if v is None or (isinstance(v, str) and not v.strip()):
            return None
        return validate_channel_slug(str(v))

    @field_validator("description", mode="before")
    @classmethod
    def keep_description(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if isinstance(v, str):
            return None if not v.strip() else v
        return v


class ChannelUpdate(BaseModel):
    model_config = BASE_MODEL_CONFIG

    name: str | None = Field(None, min_length=1, max_length=200)
    slug: str | None = Field(None, min_length=5, max_length=64)
    description: str | None = Field(None, max_length=4000)

    @field_validator("name", mode="before")
    @classmethod
    def strip_name(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return strip_and_validate_name(v)

    @field_validator("slug", mode="before")
    @classmethod
    def normalize_slug(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return validate_channel_slug(str(v))

    @field_validator("description", mode="before")
    @classmethod
    def keep_description(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if isinstance(v, str):
            return None if not v.strip() else v
        return v


class ChannelSummary(BaseModel):
    model_config = ORM_MODEL_CONFIG

    id: int
    name: str
    slug: str
    membership_id: int


class ChannelListItem(BaseModel):
    model_config = ORM_MODEL_CONFIG

    id: int
    name: str
    slug: str
    description: str | None = None
    share_enabled: bool = False
    video_count: int = 0
    playlist_count: int = 0
    banner_url: str | None = None
    created_at: datetime
    updated_at: datetime


class ChannelListResponse(PaginatedResponse):
    items: list[ChannelListItem]


class ChannelResponse(BaseModel):
    model_config = ORM_MODEL_CONFIG

    id: int
    name: str
    slug: str
    description: str | None = None
    share_enabled: bool = False
    video_count: int = 0
    playlist_count: int = 0
    banner_url: str | None = None
    created_at: datetime
    updated_at: datetime


class ChannelShareResponse(BaseModel):
    slug: str
    share_enabled: bool = True


class ChannelAddIdsRequest(BaseModel):
    ids: list[int] = Field(..., min_length=1, max_length=200)


class ChannelReorderRequest(BaseModel):
    ids: list[int] = Field(..., min_length=1)


class ChannelVideoRow(BaseModel):
    recording_id: int
    position: int
    title: str
    start_time: datetime | None = None
    duration: float
    share_enabled: bool
    playable: bool
    public_visible: bool
    hidden_reason: str | None = None
    poster_url: str | None = None
    poster_asset_key: str | None = None
    share_token: str | None = None


class ChannelPlaylistRow(BaseModel):
    playlist_id: int
    position: int
    name: str
    video_count: int = 0
    duration_sum: float = 0
    share_enabled: bool
    public_visible: bool
    hidden_reason: str | None = None
    poster_url: str | None = None
    poster_asset_key: str | None = None
    share_token: str | None = None
    has_custom_cover: bool = False


class ChannelMembershipListResponse(PaginatedResponse):
    items: list[ChannelVideoRow] | list[ChannelPlaylistRow]


class PublicChannelVideo(BaseModel):
    title: str
    duration: float
    start_time: datetime | None = None
    poster_url: str | None = None
    poster_asset_key: str | None = None
    share_token: str
    blurb: str | None = None


class PublicChannelPlaylist(BaseModel):
    name: str
    video_count: int
    duration_sum: float
    poster_url: str | None = None
    poster_asset_key: str | None = None
    share_token: str
    blurb: str | None = None


class PublicChannelResponse(BaseModel):
    name: str
    slug: str
    description: str | None = None
    banner_url: str | None = None
    videos: list[PublicChannelVideo]
    playlists: list[PublicChannelPlaylist]
