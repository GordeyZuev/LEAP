"""Output preset schemas (fully typed)"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from api.schemas.common import BASE_MODEL_CONFIG, ORM_MODEL_CONFIG, strip_and_validate_name
from api.schemas.common.pagination import PaginatedResponse

from .preset_metadata import VKPresetMetadata, YouTubePresetMetadata


class OutputPresetBase(BaseModel):
    model_config = BASE_MODEL_CONFIG

    name: str = Field(..., min_length=1, max_length=255, description="Preset name")
    description: str | None = Field(None, max_length=1000, description="Preset description")
    platform: Literal["youtube", "vk"] = Field(..., description="Platform (youtube or vk)")

    preset_metadata: YouTubePresetMetadata | VKPresetMetadata = Field(
        ...,
        description="Platform-specific settings",
    )

    @field_validator("name", mode="before")
    @classmethod
    def strip_name(cls, v: str) -> str:
        return strip_and_validate_name(v)


class OutputPresetCreate(OutputPresetBase):
    credential_id: int = Field(..., gt=0, description="Credential ID for this platform")


class OutputPresetUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = Field(None, max_length=1000)
    credential_id: int | None = Field(None, gt=0)
    preset_metadata: YouTubePresetMetadata | VKPresetMetadata | None = None
    is_active: bool | None = None


class OutputPresetListItem(BaseModel):
    """Lightweight preset for list views (excludes heavy preset_metadata)."""

    model_config = ORM_MODEL_CONFIG

    id: int
    name: str
    platform: str
    credential_id: int
    is_active: bool
    created_at: datetime
    updated_at: datetime


class OutputPresetResponse(OutputPresetBase):
    """Full preset detail including preset_metadata."""

    model_config = ORM_MODEL_CONFIG

    id: int
    user_id: str
    credential_id: int
    is_active: bool
    created_at: datetime
    updated_at: datetime


class PresetListResponse(PaginatedResponse):
    """Paginated list of output presets."""

    items: list[OutputPresetListItem]
