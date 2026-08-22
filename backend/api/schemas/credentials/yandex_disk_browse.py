"""Yandex Disk browse API schemas."""

from typing import Literal

from pydantic import BaseModel, Field

from api.schemas.common import BASE_MODEL_CONFIG


class YandexDiskBrowseItem(BaseModel):
    model_config = BASE_MODEL_CONFIG

    name: str = Field(..., description="Resource name")
    path: str = Field(..., description="Normalized Disk path (e.g. /Video)")
    type: Literal["dir", "file"] = Field(..., description="Resource type")
    size: int | None = Field(None, description="File size in bytes")
    mime_type: str | None = Field(None, description="MIME type when available")


class YandexDiskBrowseResponse(BaseModel):
    model_config = BASE_MODEL_CONFIG

    path: str = Field(..., description="Current folder path")
    items: list[YandexDiskBrowseItem] = Field(default_factory=list)
    total: int = Field(..., description="Total items in folder")
    offset: int = Field(..., description="Pagination offset")
    limit: int = Field(..., description="Pagination limit")
