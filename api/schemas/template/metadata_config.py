"""Typed schemas for metadata_config"""

from pydantic import BaseModel, Field, field_validator

from api.schemas.common import BASE_MODEL_CONFIG

from .preset_metadata import TopicsDisplayConfig

# ============================================================================
# Platform-specific metadata
# ============================================================================


class VKMetadataConfig(BaseModel):
    """VK-специфичные настройки metadata."""

    model_config = BASE_MODEL_CONFIG

    album_id: str | None = Field(None, description="ID альбома VK")
    group_id: int | None = Field(None, gt=0, description="ID группы VK для публикации")
    thumbnail_name: str | None = Field(
        None,
        description="Имя файла thumbnail для VK (например, 'ml_extra.png'). API автоматически найдет файл в директории пользователя.",
        examples=["ml_extra.png", "hse_ai.jpg", "custom_thumbnail.png"],
    )
    title_template: str | None = Field(None, max_length=500, description="VK-специфичный шаблон заголовка")
    description_template: str | None = Field(
        None, max_length=5000, description="VK-специфичный шаблон описания"
    )


class YouTubeMetadataConfig(BaseModel):
    """YouTube-специфичные настройки metadata."""

    model_config = BASE_MODEL_CONFIG

    privacy: str | None = Field(None, description="Privacy status (public, unlisted, private)")
    playlist_id: str | None = Field(None, description="ID плейлиста YouTube")
    thumbnail_name: str | None = Field(
        None,
        description="Имя файла thumbnail для YouTube (например, 'python_base.png'). API автоматически найдет файл в директории пользователя.",
        examples=["python_base.png", "hse_ai.jpg", "custom_thumbnail.png"],
    )
    title_template: str | None = Field(None, max_length=500, description="YouTube-специфичный шаблон заголовка")
    description_template: str | None = Field(
        None, max_length=5000, description="YouTube-специфичный шаблон описания"
    )


# ============================================================================
# Template Metadata Config (реальная структура с платформенными блоками)
# ============================================================================


class TemplateMetadataConfig(BaseModel):
    """
    Content-specific metadata для Recording Template.

    Структура:
    - vk: VK-специфичные настройки (album_id, thumbnail_name)
    - youtube: YouTube-специфичные настройки (privacy, playlist_id, thumbnail_name)
    - title_template: общий шаблон заголовка (для всех платформ)
    - description_template: общий шаблон описания (для всех платформ)
    - topics_display: общие настройки отображения тем
    - thumbnail_name: имя файла thumbnail (используется если не задан платформо-специфичный)

    Иерархия thumbnail_name:
    1. Если задан vk.thumbnail_name или youtube.thumbnail_name - используется он
    2. Иначе используется общий thumbnail_name
    3. Иначе используется thumbnail из preset

    Формат: только имя файла (например, "ml_extra.png")
    API автоматически ищет файл в директории пользователя:
    - storage/users/user_XXXXXX/thumbnails/

    Note: Каждый пользователь получает копии всех шаблонов при регистрации.

    Переменные в templates:
    - {display_name}, {themes}, {topic}, {topics}, {topics_list}
    - {summary}, {record_time}, {publish_time}, {date}, {duration}
    """

    model_config = BASE_MODEL_CONFIG

    # Платформо-специфичные блоки
    vk: VKMetadataConfig | None = Field(None, description="VK-специфичные настройки")
    youtube: YouTubeMetadataConfig | None = Field(None, description="YouTube-специфичные настройки")

    # Общие настройки (для всех платформ)
    title_template: str | None = Field(
        None,
        max_length=500,
        description="Шаблон заголовка с переменными",
        examples=[
            "Курс ИИ | {themes} ({record_time:DD.MM.YY})",
            "{display_name} - {date}",
            "Обучение с подкреплением | {themes}",
        ],
    )

    description_template: str | None = Field(
        None,
        max_length=5000,
        description="Шаблон описания с переменными",
        examples=[
            "Лекция по курсу\\n\\n{topics}\\n\\nЗаписано: {record_time:DD.MM.YYYY}",
            "{summary}",
            "Темы: {topics_list}\\n\\nДлительность: {duration}",
        ],
    )

    topics_display: TopicsDisplayConfig | None = Field(
        None,
        description="Настройки отображения тем в description (для всех платформ)",
    )

    thumbnail_name: str | None = Field(
        None,
        description="Имя файла thumbnail для всех платформ (если не указан платформо-специфичный). API автоматически найдет файл в директории пользователя.",
        examples=[
            "applied_python.png",
            "ml_extra.png",
            "hse_ai.jpg"
        ],
    )

    @field_validator("title_template")
    @classmethod
    def validate_title_template(cls, v: str | None) -> str | None:
        if v is not None:
            v = v.strip()
            if not v:
                return None
            # Проверка что есть хоть одна переменная
            valid_vars = ["{display_name}", "{themes}", "{topic}", "{date}", "{record_time}", "{duration}"]
            if not any(var in v for var in valid_vars):
                raise ValueError(f"title_template должен содержать хоть одну переменную из: {', '.join(valid_vars)}")
        return v
