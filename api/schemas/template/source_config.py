"""Typed schemas for input source config"""

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from api.schemas.common import BASE_MODEL_CONFIG
from api.schemas.common.validators import validate_regex_pattern


class ZoomSourceConfig(BaseModel):
    model_config = BASE_MODEL_CONFIG

    user_id: str | None = Field(None, description="Zoom user ID for filtering (optional)")
    include_trash: bool = Field(False, description="Include deleted recordings")
    recording_type: Literal["cloud", "all"] = Field("cloud", description="Recording type: cloud or all")


class GoogleDriveSourceConfig(BaseModel):
    model_config = BASE_MODEL_CONFIG

    folder_id: str = Field(..., description="Google Drive folder ID")
    recursive: bool = Field(True, description="Recursive search in subfolders")
    file_pattern: str | None = Field(
        None,
        description="Regex pattern for file filtering",
        examples=[".*\\.mp4$", "Lecture.*\\.mp4"],
    )

    @field_validator("file_pattern")
    @classmethod
    def validate_pattern(cls, v: str | None) -> str | None:
        return validate_regex_pattern(v, field_name="file_pattern")


class YandexDiskSourceConfig(BaseModel):
    model_config = BASE_MODEL_CONFIG

    folder_path: str = Field(..., description="Yandex Disk folder path", examples=["/Video/Lectures"])
    recursive: bool = Field(True, description="Recursive search in subfolders")
    file_pattern: str | None = Field(None, description="Regex pattern for file filtering")

    @field_validator("file_pattern")
    @classmethod
    def validate_pattern(cls, v: str | None) -> str | None:
        return validate_regex_pattern(v, field_name="file_pattern")


class LocalFileSourceConfig(BaseModel):
    model_config = BASE_MODEL_CONFIG


SourceConfig = ZoomSourceConfig | GoogleDriveSourceConfig | YandexDiskSourceConfig | LocalFileSourceConfig
