"""Thumbnail schemas"""

from pydantic import BaseModel, Field


class ThumbnailInfo(BaseModel):
    """Информация о thumbnail."""

    name: str = Field(..., description="Имя файла")
    url: str = Field(..., description="URL для получения файла через API")
    is_template: bool = Field(..., description="Является ли глобальным template")
    size_bytes: int = Field(default=0, description="Размер в байтах")
    size_kb: float = Field(default=0.0, description="Размер в KB")
    modified_at: float = Field(default=0.0, description="Время последнего изменения (timestamp)")


class ThumbnailListResponse(BaseModel):
    """Список thumbnails пользователя."""

    thumbnails: list[ThumbnailInfo] = Field(
        default_factory=list,
        description="Thumbnails пользователя (включая копии шаблонов, полученные при регистрации)"
    )


class ThumbnailUploadResponse(BaseModel):
    """Результат загрузки thumbnail."""

    message: str = Field(..., description="Сообщение о результате")
    thumbnail: ThumbnailInfo = Field(..., description="Информация о загруженном thumbnail")
