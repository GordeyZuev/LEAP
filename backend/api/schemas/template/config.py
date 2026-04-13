"""Base configuration schemas"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from api.schemas.common import BASE_MODEL_CONFIG, ORM_MODEL_CONFIG, strip_and_validate_name


class BaseConfigBase(BaseModel):
    model_config = BASE_MODEL_CONFIG

    name: str = Field(..., min_length=1, max_length=255, description="Name of configuration")
    description: str | None = Field(None, max_length=1000, description="Description of configuration")
    config_type: str | None = Field(None, description="Type of configuration (processing, transcription, etc)")
    config_data: dict[str, Any] = Field(..., description="Data of configuration")

    @field_validator("name", mode="before")
    @classmethod
    def strip_name(cls, v: str) -> str:
        return strip_and_validate_name(v)

    @field_validator("config_data")
    @classmethod
    def validate_config_data(cls, v: dict[str, Any]) -> dict[str, Any]:
        if not v:
            raise ValueError("config_data cannot be empty")

        if "max_file_size_mb" in v:
            try:
                size = float(v["max_file_size_mb"])
                if size <= 0:
                    raise ValueError("max_file_size_mb must be positive")
            except (ValueError, TypeError) as e:
                raise ValueError(f"Invalid max_file_size_mb: {e}") from e

        if "allowed_formats" in v and not isinstance(v["allowed_formats"], list):
            raise ValueError("allowed_formats must be a list")

        return v

    @model_validator(mode="after")
    def validate_config_by_type(self) -> "BaseConfigBase":
        if self.config_type:
            try:
                from api.schemas.config_types import validate_config_by_type

                validate_config_by_type(self.config_type, self.config_data)
            except Exception as e:
                raise ValueError(f"Invalid config_data for type '{self.config_type}': {e}") from e
        return self


class BaseConfigCreate(BaseConfigBase):
    is_global: bool = Field(False, description="Global configuration (admin only)")


class BaseConfigUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    config_data: dict[str, Any] | None = None
    is_active: bool | None = None


class BaseConfigResponse(BaseConfigBase):
    model_config = ORM_MODEL_CONFIG

    id: int
    user_id: str | None
    is_active: bool
    is_global: bool = Field(False, description="Global configuration")
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_orm_model(cls, model) -> "BaseConfigResponse":
        """Create from ORM model."""
        return cls(
            id=model.id,
            name=model.name,
            description=model.description,
            config_type=model.config_type,
            config_data=model.config_data,
            user_id=model.user_id,
            is_active=model.is_active,
            is_global=(model.user_id is None),
            created_at=model.created_at,
            updated_at=model.updated_at,
        )
