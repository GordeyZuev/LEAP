"""Typed schemas for preset_metadata"""

from enum import Enum, StrEnum

from pydantic import BaseModel, Field, field_validator

from api.schemas.common import BASE_MODEL_CONFIG


class TopicsDisplayFormat(StrEnum):
    NUMBERED_LIST = "numbered_list"
    BULLET_LIST = "bullet_list"
    DASH_LIST = "dash_list"
    COMMA_SEPARATED = "comma_separated"
    INLINE = "inline"


class TopicsDisplayConfig(BaseModel):
    model_config = BASE_MODEL_CONFIG

    enabled: bool = Field(True, description="Включить отображение тем")
    format: TopicsDisplayFormat = Field(TopicsDisplayFormat.NUMBERED_LIST, description="Формат списка")
    max_count: int | None = Field(
        None, ge=1, le=999, description="Максимальное количество тем (None = default из base config)"
    )
    min_length: int | None = Field(
        None, ge=0, le=500, description="Минимальная длина темы в символах (0 = без фильтрации)"
    )
    max_length: int | None = Field(None, ge=10, le=1000, description="Максимальная длина темы в символах")
    prefix: str | None = Field(None, max_length=200, description="Префикс перед списком тем")
    separator: str = Field("\n", max_length=10, description="Разделитель между темами")
    show_timestamps: bool = Field(False, description="Показывать временные метки для тем")

    @field_validator("prefix")
    @classmethod
    def validate_prefix(cls, v: str | None) -> str | None:
        if v is not None:
            v = v.strip()
            return v if v else None
        return v


class YouTubePrivacy(StrEnum):
    PUBLIC = "public"
    PRIVATE = "private"
    UNLISTED = "unlisted"


class YouTubeLicense(StrEnum):
    YOUTUBE = "youtube"
    CREATIVE_COMMON = "creativeCommon"


class YouTubePresetMetadata(BaseModel):
    model_config = BASE_MODEL_CONFIG

    title_template: str | None = Field(
        None,
        max_length=500,
        description="Title template with variables (e.g. '{display_name} | {themes}')",
    )
    description_template: str | None = Field(
        None,
        max_length=5000,
        description="Description template with variables (e.g. '{summary}\\n\\n{topics}')",
    )

    privacy: YouTubePrivacy = Field(YouTubePrivacy.UNLISTED, description="Privacy status")
    made_for_kids: bool = Field(False, description="Content for kids (COPPA)")
    embeddable: bool = Field(True, description="Allow embedding on other sites")

    category_id: str = Field("27", description="YouTube category (27 = Education)")
    license: YouTubeLicense = Field(YouTubeLicense.YOUTUBE, description="License type")
    default_language: str | None = Field(None, description="Default language", examples=["ru", "en"])

    playlist_id: str | None = Field(None, description="YouTube playlist ID for auto-upload")
    tags: list[str] | None = Field(None, max_length=500, description="Video tags (max 500)")
    thumbnail_name: str | None = Field(
        None,
        description="Thumbnail filename (e.g. 'python_base.png'). API will find it in user directory.",
        examples=["python_base.png", "ml_extra.png", "hse_ai.jpg"],
    )

    publish_at: str | None = Field(None, description="ISO 8601 publish date/time (for scheduled publishing)")

    topics_display: TopicsDisplayConfig | None = Field(None, description="Topics display settings")

    disable_comments: bool = Field(False, description="Disable comments")
    rating_disabled: bool = Field(False, description="Disable like/dislike ratings")

    notify_subscribers: bool = Field(True, description="Notify subscribers about publication")

    @field_validator("category_id")
    @classmethod
    def validate_category_id(cls, v: str) -> str:
        try:
            cat_int = int(v)
            if cat_int < 1:
                raise ValueError("category_id must be positive")
        except ValueError:
            raise ValueError("category_id must be a number")
        return v


class VKPrivacyLevel(int, Enum):
    ALL = 0
    FRIENDS = 1
    FRIENDS_OF_FRIENDS = 2
    ONLY_ME = 3


class VKPresetMetadata(BaseModel):
    model_config = BASE_MODEL_CONFIG

    title_template: str | None = Field(
        None,
        max_length=500,
        description="Title template with variables (e.g. '{display_name}')",
    )
    description_template: str | None = Field(
        None,
        max_length=5000,
        description="Description template with variables (e.g. '{summary}\\n\\n{topics}')",
    )

    privacy_view: VKPrivacyLevel = Field(
        VKPrivacyLevel.ALL,
        description="Who can view video (0=all, 1=friends, 2=friends of friends, 3=only me)",
    )
    privacy_comment: VKPrivacyLevel = Field(
        VKPrivacyLevel.ALL,
        description="Who can comment (0=all, 1=friends, 2=friends of friends, 3=only me)",
    )

    group_id: int | None = Field(None, gt=0, description="VK group ID (can be set in template metadata_config)")
    album_id: str | None = Field(None, description="VK album ID")
    thumbnail_name: str | None = Field(
        None,
        description="Thumbnail filename (e.g. 'applied_python.png'). API will find it in user directory.",
        examples=["applied_python.png", "ml_extra.png", "hse_ai.jpg"],
    )

    topics_display: TopicsDisplayConfig | None = Field(None, description="Topics display settings")

    disable_comments: bool = Field(False, description="Disable comments completely")
    repeat: bool = Field(False, description="Loop playback")
    compression: bool = Field(False, description="VK-side video compression")
    wallpost: bool = Field(False, description="Post to wall on upload")

    @field_validator("group_id")
    @classmethod
    def validate_group_id(cls, v: int | None) -> int | None:
        if v is not None and v <= 0:
            raise ValueError("group_id must be positive")
        return v


class YandexDiskPresetMetadata(BaseModel):
    """Preset metadata for Yandex Disk output target."""

    model_config = BASE_MODEL_CONFIG

    folder_path_template: str = Field(
        ...,
        description="Path template on Disk with variables (e.g. '/Video/{course_name}/{date}')",
        examples=["/Video/Processed", "/Video/{display_name}/{record_time:YYYY-MM-DD}"],
    )
    filename_template: str | None = Field(
        None,
        max_length=500,
        description="Custom filename template (default: video.mp4)",
        examples=["{display_name}.mp4", "{record_time:YYYY-MM-DD}_{display_name}.mp4"],
    )
    overwrite: bool = Field(False, description="Overwrite existing files on Disk")


PresetMetadata = YouTubePresetMetadata | VKPresetMetadata | YandexDiskPresetMetadata
