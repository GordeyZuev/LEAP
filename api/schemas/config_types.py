"""Typed schemas for various configuration types

These schemas are used for validation of config_data in BaseConfigModel.
"""

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class TrimmingConfigData(BaseModel):
    """Configuration for video trimming."""

    # Audio detection
    enable_trimming: bool = Field(True, description="Enable video trimming")
    audio_detection: bool = Field(True, description="Use audio detection")
    silence_threshold: float = Field(-40.0, ge=-60.0, le=0.0, description="Silence threshold in dB")
    min_silence_duration: float = Field(2.0, ge=0.1, description="Minimum silence duration (sec)")
    padding_before: float = Field(5.0, ge=0.0, description="Padding before audio (sec)")
    padding_after: float = Field(5.0, ge=0.0, description="Padding after audio (sec)")

    # Trimming
    remove_intro: bool = Field(False, description="Remove intro")
    remove_outro: bool = Field(False, description="Remove outro")
    intro_duration: float = Field(30.0, ge=0.0, description="Intro duration (sec)")
    outro_duration: float = Field(30.0, ge=0.0, description="Outro duration (sec)")

    # System settings (not changed by user)
    video_codec: str = Field("copy", description="Video codec")
    audio_codec: str = Field("copy", description="Audio codec")
    video_bitrate: str = Field("original", description="Video bitrate")
    audio_bitrate: str = Field("original", description="Audio bitrate")
    resolution: str = Field("original", description="Resolution")
    fps: int = Field(0, ge=0, description="FPS (0 = no change)")
    output_format: str = Field("mp4", description="Output file format")


class TranscriptionConfigData(BaseModel):
    """Конфигурация для транскрибации."""

    provider: Literal["fireworks", "deepseek", "openai"] = Field("fireworks", description="Провайдер транскрибации")
    model: str = Field("whisper-v3-turbo", description="Модель для транскрибации")
    language: str = Field("ru", description="Язык аудио")
    generate_subtitles: bool = Field(True, description="Генерировать субтитры")
    subtitle_formats: list[str] = Field(default_factory=lambda: ["srt", "vtt"], description="Форматы субтитров")

    # Дополнительные настройки
    temperature: float = Field(0.0, ge=0.0, le=1.0, description="Temperature для модели")
    prompt: str | None = Field(None, description="Промпт для контекста")

    @field_validator("subtitle_formats")
    @classmethod
    def validate_subtitle_formats(cls, v: list[str]) -> list[str]:
        """Валидация форматов субтитров."""
        allowed = ["srt", "vtt", "txt"]
        for fmt in v:
            if fmt not in allowed:
                raise ValueError(f"Unsupported subtitle format: {fmt}. Allowed: {allowed}")
        return v


class UploadConfigData(BaseModel):
    """Конфигурация для загрузки на платформы."""

    max_file_size_mb: int = Field(5000, ge=1, description="Максимальный размер файла (МБ)")
    supported_formats: list[str] = Field(
        default_factory=lambda: ["mp4", "avi", "mov", "mkv", "webm"], description="Поддерживаемые форматы"
    )
    retry_attempts: int = Field(3, ge=1, le=10, description="Количество попыток при ошибке")
    retry_delay: int = Field(5, ge=0, description="Задержка между попытками (сек)")
    default_privacy: Literal["private", "unlisted", "public"] = Field(
        "unlisted", description="Приватность по умолчанию"
    )


class MappingRule(BaseModel):
    """Правило маппинга для названий видео."""

    pattern: str = Field(..., min_length=1, description="Паттерн для сопоставления")
    title_template: str = Field(..., min_length=1, description="Шаблон названия")
    thumbnail: str | None = Field(None, description="Путь к миниатюре")
    youtube_playlist_id: str | None = Field(None, description="ID плейлиста YouTube")
    vk_album_id: str | None = Field(None, description="ID альбома VK")


class VideoMappingConfigData(BaseModel):
    """Конфигурация для маппинга названий видео."""

    mapping_rules: list[MappingRule] = Field(default_factory=list, description="Правила маппинга")
    default_title_template: str = Field(
        "{original_title} | {topic} ({date})", description="Шаблон названия по умолчанию"
    )
    default_thumbnail: str = Field("storage/shared/thumbnails/default.png", description="Миниатюра по умолчанию")
    date_format: str = Field("DD.MM.YYYY", description="Формат даты")
    thumbnail_directory: str = Field(
        "storage/shared/thumbnails/", description="Директория для глобальных template миниатюр"
    )

    @field_validator("mapping_rules")
    @classmethod
    def validate_mapping_rules(cls, v: list[MappingRule]) -> list[MappingRule]:
        """Валидация правил маппинга."""
        patterns = [rule.pattern for rule in v]
        if len(patterns) != len(set(patterns)):
            raise ValueError("Duplicate patterns found in mapping rules")
        return v


class ZoomSyncConfigData(BaseModel):
    """Конфигурация для синхронизации Zoom."""

    sync_mode: Literal["all", "recent", "specific"] = Field("recent", description="Режим синхронизации")
    days_back: int = Field(30, ge=1, le=365, description="Количество дней для синхронизации")
    include_trash: bool = Field(False, description="Включать удаленные записи")
    auto_download: bool = Field(True, description="Автоматически скачивать файлы")
    download_quality: Literal["hd", "sd", "audio_only"] = Field("hd", description="Качество скачивания")


class YandexDiskSyncConfigData(BaseModel):
    """Конфигурация для синхронизации Yandex Disk."""

    folder_path: str | None = Field(None, description="Путь к папке на Yandex Disk")
    folder_url: str | None = Field(None, description="Публичная ссылка на папку")
    recursive: bool = Field(False, description="Рекурсивный обход папок")
    file_patterns: list[str] = Field(default_factory=lambda: ["*.mp4"], description="Паттерны файлов")

    @field_validator("folder_path", "folder_url")
    @classmethod
    def validate_folder(cls, v: str | None, _info) -> str | None:
        """Валидация папки - должен быть указан либо путь, либо URL."""
        # Проверка будет на уровне модели
        return v

    def model_post_init(self, __context) -> None:
        """Проверка после инициализации."""
        if not self.folder_path and not self.folder_url:
            raise ValueError("Either folder_path or folder_url must be specified")


# Config type to schema mapping
CONFIG_TYPE_SCHEMAS: dict[str, type[BaseModel]] = {
    "trimming": TrimmingConfigData,
    "transcription": TranscriptionConfigData,
    "upload": UploadConfigData,
    "video_mapping": VideoMappingConfigData,
    "zoom_sync": ZoomSyncConfigData,
    "yandex_disk_sync": YandexDiskSyncConfigData,
}


def validate_config_by_type(config_type: str, config_data: dict[str, Any]) -> BaseModel:
    """
    Валидировать config_data по типу.

    Args:
        config_type: Тип конфигурации
        config_data: Данные конфигурации

    Returns:
        Валидированная Pydantic модель

    Raises:
        ValueError: Если тип неизвестен или данные невалидны
    """
    if config_type not in CONFIG_TYPE_SCHEMAS:
        raise ValueError(f"Unknown config type: {config_type}. Allowed: {list(CONFIG_TYPE_SCHEMAS.keys())}")

    schema_class = CONFIG_TYPE_SCHEMAS[config_type]
    return schema_class.model_validate(config_data)
