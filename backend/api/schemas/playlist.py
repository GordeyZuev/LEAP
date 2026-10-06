"""Pydantic schemas for playlists."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from api.schemas.common import BASE_MODEL_CONFIG, ORM_MODEL_CONFIG, strip_and_validate_name
from api.schemas.common.pagination import PaginatedResponse
from database.playlist_models import VideoSort


class PlaylistCreate(BaseModel):
    model_config = BASE_MODEL_CONFIG

    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = Field(None, max_length=4000)

    @field_validator("name", mode="before")
    @classmethod
    def strip_name(cls, v: str) -> str:
        return strip_and_validate_name(v)

    @field_validator("description", mode="before")
    @classmethod
    def keep_description_whitespace(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if isinstance(v, str):
            return None if not v.strip() else v
        return v


class PlaylistUpdate(BaseModel):
    model_config = BASE_MODEL_CONFIG

    name: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = Field(None, max_length=4000)
    item_sort: VideoSort | None = Field(
        None, description="Saved order rule, applied now and to added videos; null keeps the current order as custom"
    )

    @field_validator("name", mode="before")
    @classmethod
    def strip_name(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return strip_and_validate_name(v)

    @field_validator("description", mode="before")
    @classmethod
    def keep_description_whitespace(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if isinstance(v, str):
            return None if not v.strip() else v
        return v


class PlaylistSummary(BaseModel):
    """Membership chip on a recording detail page."""

    model_config = ORM_MODEL_CONFIG

    id: int
    name: str
    item_id: int


class PlaylistListItem(BaseModel):
    model_config = ORM_MODEL_CONFIG

    id: int
    name: str
    description: str | None = None
    video_count: int = 0
    duration_sum: float = 0
    view_count: int = Field(0, description="Sum of all-time LEAP views of the playlist's videos.")
    share_token: uuid.UUID | None = Field(
        default=None,
        description="Owner token for /share/p/{uuid}. Public GET is 404 unless share_enabled.",
    )
    share_enabled: bool = False
    poster_url: str | None = None
    poster_asset_key: str | None = Field(
        None,
        description="Stable poster identity for the cover recording; unchanged across presign refreshes.",
    )
    poster_refresh_at_ms: int | None = None
    has_custom_cover: bool = False
    created_at: datetime
    updated_at: datetime


class PlaylistListResponse(PaginatedResponse):
    items: list[PlaylistListItem]


class PlaylistShareInfo(BaseModel):
    share_token: uuid.UUID | None = None
    share_enabled: bool = False
    share_created_at: datetime | None = None


class PlaylistResponse(BaseModel):
    model_config = ORM_MODEL_CONFIG

    id: int
    name: str
    description: str | None = None
    video_count: int = 0
    duration_sum: float = 0
    share_token: uuid.UUID | None = None
    share_enabled: bool = False
    share_created_at: datetime | None = None
    has_custom_cover: bool = False
    item_sort: VideoSort | None = Field(None, description="Saved order rule; null when the order is custom")
    poster_url: str | None = None
    poster_asset_key: str | None = None
    created_at: datetime
    updated_at: datetime


class PlaylistShareResponse(BaseModel):
    share_token: uuid.UUID
    share_enabled: bool = True


class PlaylistAddItemsRequest(BaseModel):
    recording_ids: list[int] = Field(..., min_length=1, max_length=200)


class PlaylistReorderRequest(BaseModel):
    item_ids: list[int] = Field(..., min_length=1)


class PlaylistGroupWrite(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)

    @field_validator("name", mode="before")
    @classmethod
    def strip_name(cls, value: str) -> str:
        return strip_and_validate_name(value)


class PlaylistGroupResponse(BaseModel):
    id: int
    name: str
    position: int
    item_count: int = 0


class PublicChannelLink(BaseModel):
    slug: str
    name: str


class PublicPosterResponse(BaseModel):
    url: str
    asset_key: str | None = None


class PlaylistItemGroupUpdate(BaseModel):
    group_id: int | None = None


class PlaylistItemResponse(BaseModel):
    model_config = ORM_MODEL_CONFIG

    id: int
    recording_id: int
    position: int = Field(description="0-based index in the whole playlist, without gaps; unaffected by filters")
    group_id: int | None = None
    display_name: str
    title: str
    start_time: datetime
    duration: float
    playable: bool
    unavailable_reason: str | None = None
    poster_url: str | None = None
    poster_fallback_url: str | None = Field(
        None,
        description="Frame poster URL when the primary thumbnail fails to load.",
    )
    poster_asset_key: str | None = Field(
        None,
        description="Stable poster identity; unchanged when presigned URLs are refreshed.",
    )
    poster_refresh_at_ms: int | None = None
    deleted: bool = False
    blank_record: bool = False
    view_count: int = 0


class PlaylistItemsResponse(PaginatedResponse):
    items: list[PlaylistItemResponse]


class PublicPlaylistItem(BaseModel):
    id: int
    position: int = Field(description="0-based index in the whole playlist, without gaps")
    group_id: int | None = None
    title: str
    duration: float
    start_time: datetime
    playable: bool
    unavailable_reason: str | None = None
    poster_url: str | None = None
    poster_asset_key: str | None = Field(
        None,
        description="Stable poster identity; unchanged when presigned URLs are refreshed.",
    )
    view_count: int = 0


class PublicPlaylistResponse(BaseModel):
    name: str
    description: str | None = None
    channels: list[PublicChannelLink] = Field(default_factory=list)
    groups: list[PlaylistGroupResponse] = Field(default_factory=list)
    items: list[PublicPlaylistItem]
