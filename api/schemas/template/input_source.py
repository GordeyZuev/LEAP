"""Input source schemas (fully typed)"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from api.schemas.common import BASE_MODEL_CONFIG, ORM_MODEL_CONFIG, strip_and_validate_name
from api.schemas.common.pagination import PaginatedResponse

from .source_config import GoogleDriveSourceConfig, LocalFileSourceConfig, YandexDiskSourceConfig, ZoomSourceConfig


class InputSourceBase(BaseModel):
    model_config = BASE_MODEL_CONFIG

    name: str = Field(..., min_length=3, max_length=255, description="Source name")
    description: str | None = Field(None, max_length=1000, description="Source description")

    config: ZoomSourceConfig | GoogleDriveSourceConfig | YandexDiskSourceConfig | LocalFileSourceConfig | None = Field(
        None,
        description="Platform-specific config",
    )

    @field_validator("name", mode="before")
    @classmethod
    def strip_name(cls, v: str) -> str:
        return strip_and_validate_name(v)


class InputSourceCreate(BaseModel):
    model_config = BASE_MODEL_CONFIG

    name: str = Field(..., min_length=3, max_length=255, description="Source name")
    description: str | None = Field(None, max_length=1000, description="Source description")
    platform: Literal["ZOOM", "GOOGLE_DRIVE", "YANDEX_DISK", "LOCAL"] = Field(..., description="Platform")
    credential_id: int | None = Field(None, gt=0, description="Credential ID (required for all except LOCAL)")

    config: ZoomSourceConfig | GoogleDriveSourceConfig | YandexDiskSourceConfig | LocalFileSourceConfig | None = Field(
        None,
        description="Platform-specific config",
    )

    @field_validator("name", mode="before")
    @classmethod
    def strip_name(cls, v: str) -> str:
        return strip_and_validate_name(v)

    @model_validator(mode="after")
    def validate_source(self) -> "InputSourceCreate":
        if self.platform != "LOCAL" and not self.credential_id:
            raise ValueError(f"Platform {self.platform} requires credential_id")

        if self.platform == "LOCAL" and self.credential_id:
            raise ValueError("LOCAL source should not have credential_id")

        return self


class InputSourceUpdate(BaseModel):
    name: str | None = Field(None, min_length=3, max_length=255)
    description: str | None = Field(None, max_length=1000)
    credential_id: int | None = Field(None, gt=0)
    config: ZoomSourceConfig | GoogleDriveSourceConfig | YandexDiskSourceConfig | LocalFileSourceConfig | None = None
    is_active: bool | None = None


class InputSourceListItem(BaseModel):
    """Lightweight source for list views (excludes heavy config)."""

    model_config = ORM_MODEL_CONFIG

    id: int
    name: str
    source_type: str
    credential_id: int | None
    is_active: bool
    last_sync_at: datetime | None
    created_at: datetime
    updated_at: datetime


class InputSourceResponse(BaseModel):
    """Full source detail including platform-specific config."""

    model_config = ORM_MODEL_CONFIG

    id: int
    user_id: str
    name: str
    description: str | None
    source_type: str
    credential_id: int | None
    config: ZoomSourceConfig | GoogleDriveSourceConfig | YandexDiskSourceConfig | LocalFileSourceConfig | None
    is_active: bool
    last_sync_at: datetime | None
    created_at: datetime
    updated_at: datetime


class SourceListResponse(PaginatedResponse):
    """Paginated list of input sources."""

    items: list[InputSourceListItem]


class BulkSyncRequest(BaseModel):
    model_config = BASE_MODEL_CONFIG

    source_ids: list[int] = Field(..., min_length=1, max_length=50, description="List of source IDs to sync")
    from_date: str = Field("2025-01-01", description="Start date in YYYY-MM-DD format")
    to_date: str | None = Field(None, description="End date in YYYY-MM-DD format (optional)")


class SourceSyncResult(BaseModel):
    model_config = BASE_MODEL_CONFIG

    source_id: int
    source_name: str | None = None
    status: str
    recordings_found: int | None = None
    recordings_saved: int | None = None
    recordings_updated: int | None = None
    error: str | None = None


class BatchSyncResponse(BaseModel):
    model_config = BASE_MODEL_CONFIG

    message: str
    total_sources: int
    successful: int
    failed: int
    results: list[SourceSyncResult]
