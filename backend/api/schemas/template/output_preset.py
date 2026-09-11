"""Output preset schemas (fully typed)"""

from datetime import datetime
from typing import Any, Literal, Self

from pydantic import BaseModel, Field, field_validator, model_validator

from api.schemas.common import BASE_MODEL_CONFIG, ORM_MODEL_CONFIG, strip_and_validate_name
from api.schemas.common.pagination import PaginatedResponse

from .preset_metadata import (
    LeapPresetMetadata,
    VKPresetMetadata,
    YandexDiskPresetMetadata,
    YouTubePresetMetadata,
    coerce_preset_metadata,
)

_PresetMetaUnion = YouTubePresetMetadata | VKPresetMetadata | YandexDiskPresetMetadata | LeapPresetMetadata


def _coerce_preset_payload(data: Any) -> Any:
    if isinstance(data, dict):
        mapping = dict(data)
    else:
        mapping = {
            "id": getattr(data, "id", None),
            "user_id": getattr(data, "user_id", None),
            "name": getattr(data, "name", None),
            "description": getattr(data, "description", None),
            "platform": getattr(data, "platform", None),
            "credential_id": getattr(data, "credential_id", None),
            "preset_metadata": getattr(data, "preset_metadata", None),
            "is_active": getattr(data, "is_active", None),
            "created_at": getattr(data, "created_at", None),
            "updated_at": getattr(data, "updated_at", None),
        }
        mapping = {
            k: v
            for k, v in mapping.items()
            if v is not None or k in ("description", "credential_id", "preset_metadata")
        }
    platform = mapping.get("platform")
    if platform is not None and "preset_metadata" in mapping:
        mapping["preset_metadata"] = coerce_preset_metadata(str(platform), mapping.get("preset_metadata"))
    return mapping


class OutputPresetBase(BaseModel):
    model_config = BASE_MODEL_CONFIG

    name: str = Field(..., min_length=1, max_length=255, description="Preset name")
    description: str | None = Field(None, max_length=1000, description="Preset description")
    platform: Literal["youtube", "vk", "yandex_disk", "leap"] = Field(
        ...,
        description="youtube/vk/yandex_disk copies, or leap (share/courses, no credential)",
    )

    preset_metadata: _PresetMetaUnion = Field(..., description="Platform-specific settings")

    @field_validator("name", mode="before")
    @classmethod
    def strip_name(cls, v: str) -> str:
        return strip_and_validate_name(v)

    @model_validator(mode="before")
    @classmethod
    def _coerce_metadata_by_platform(cls, data: Any) -> Any:
        return _coerce_preset_payload(data)


class OutputPresetCreate(OutputPresetBase):
    credential_id: int | None = Field(None, gt=0, description="Credential ID; omit for leap presets")
    is_active: bool = Field(True, description="Inactive presets are skipped when publishing")

    @model_validator(mode="after")
    def _credential_rules(self) -> Self:
        if self.platform == "leap":
            if self.credential_id is not None:
                raise ValueError("leap presets must not have a credential")
        elif self.credential_id is None:
            raise ValueError("credential_id is required for upload presets")
        return self


class OutputPresetUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = Field(None, max_length=1000)
    credential_id: int | None = Field(None, gt=0)
    preset_metadata: _PresetMetaUnion | None = None
    is_active: bool | None = None


class OutputPresetListItem(BaseModel):
    """Lightweight preset for list views (excludes heavy preset_metadata)."""

    model_config = ORM_MODEL_CONFIG

    id: int
    name: str
    platform: str
    credential_id: int | None = None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class OutputPresetResponse(OutputPresetBase):
    """Full preset detail including preset_metadata."""

    model_config = ORM_MODEL_CONFIG

    id: int
    user_id: str
    credential_id: int | None = None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class PresetListResponse(PaginatedResponse):
    """Paginated list of output presets."""

    items: list[OutputPresetListItem]
