"""Pydantic schemas for playlists."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from api.schemas.common import BASE_MODEL_CONFIG, ORM_MODEL_CONFIG, strip_and_validate_name
from api.schemas.common.pagination import PaginatedResponse


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
    share_enabled: bool = False
    poster_url: str | None = None
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
    created_at: datetime
    updated_at: datetime


class PlaylistShareResponse(BaseModel):
    share_token: uuid.UUID
    share_enabled: bool = True


class PlaylistAddItemsRequest(BaseModel):
    recording_ids: list[int] = Field(..., min_length=1, max_length=200)


class PlaylistReorderRequest(BaseModel):
    item_ids: list[int] = Field(..., min_length=1)


class PlaylistItemResponse(BaseModel):
    model_config = ORM_MODEL_CONFIG

    id: int
    recording_id: int
    position: int
    display_name: str
    start_time: datetime
    duration: float
    playable: bool
    unavailable_reason: str | None = None
    poster_url: str | None = None
    deleted: bool = False
    blank_record: bool = False


class PlaylistItemsResponse(PaginatedResponse):
    items: list[PlaylistItemResponse]


class PublicPlaylistItem(BaseModel):
    id: int
    position: int
    title: str
    duration: float
    start_time: datetime
    playable: bool
    unavailable_reason: str | None = None
    poster_url: str | None = None


class PublicPlaylistResponse(BaseModel):
    name: str
    description: str | None = None
    items: list[PublicPlaylistItem]
