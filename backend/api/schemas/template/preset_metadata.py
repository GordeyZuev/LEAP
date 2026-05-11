"""Typed schemas for preset_metadata"""

from enum import Enum, StrEnum

from pydantic import BaseModel, Field, field_validator

from api.schemas.common import BASE_MODEL_CONFIG

from .jinja_field_validators import validate_optional_jinja, validate_optional_jinja_title, validate_required_jinja


class TopicsDisplayFormat(StrEnum):
    NUMBERED_LIST = "numbered_list"
    BULLET_LIST = "bullet_list"
    DASH_LIST = "dash_list"
    COMMA_SEPARATED = "comma_separated"
    INLINE = "inline"


class TopicsDisplayConfig(BaseModel):
    model_config = BASE_MODEL_CONFIG

    enabled: bool = Field(True, description="Enable topics display")
    format: TopicsDisplayFormat = Field(TopicsDisplayFormat.NUMBERED_LIST, description="List format")
    max_count: int | None = Field(None, ge=1, le=999, description="Max topics count (None = default from base config)")
    min_length: int | None = Field(None, ge=0, le=500, description="Min topic length in chars (0 = no filtering)")
    max_length: int | None = Field(None, ge=10, le=1000, description="Max topic length in chars")
    prefix: str | None = Field(None, max_length=200, description="Prefix before topics list")
    separator: str = Field("\n", max_length=10, description="Separator between topics")
    show_timestamps: bool = Field(False, description="Show timestamps for topics")

    @field_validator("prefix")
    @classmethod
    def validate_prefix(cls, v: str | None) -> str | None:
        if v is not None:
            v = v.strip()
            return v if v else None
        return v


class QuestionsDisplayConfig(BaseModel):
    """Display settings for self-check questions in description templates."""

    model_config = BASE_MODEL_CONFIG

    enabled: bool = Field(False, description="Enable questions display (opt-in for backward compatibility)")
    format: TopicsDisplayFormat = Field(
        TopicsDisplayFormat.NUMBERED_LIST,
        description="List format (numbered_list, bullet_list, dash_list, comma_separated, inline)",
    )
    max_count: int | None = Field(None, ge=1, le=20, description="Max questions count (None = all)")
    min_length: int | None = Field(None, ge=0, le=500, description="Min question length in chars (0 = no filtering)")
    max_length: int | None = Field(None, ge=10, le=1000, description="Max question length in chars")
    prefix: str | None = Field(None, max_length=200, description="Prefix before questions list")
    separator: str = Field("\n", max_length=10, description="Separator between questions")

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
    CREATIVE_COMMONS = "creativeCommon"


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
        description="Description template with variables (e.g. '{summary}\\n\\n{topics}\\n\\n{questions}')",
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
    questions_display: QuestionsDisplayConfig | None = Field(None, description="Questions display settings")

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
        return str(cat_int)

    @field_validator("title_template", mode="before")
    @classmethod
    def _youtube_title_jinja(cls, v: str | None) -> str | None:
        return validate_optional_jinja_title(v)

    @field_validator("description_template", mode="before")
    @classmethod
    def _youtube_desc_jinja(cls, v: str | None) -> str | None:
        return validate_optional_jinja(v)


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
        description="Description template with variables (e.g. '{summary}\\n\\n{topics}\\n\\n{questions}')",
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
    questions_display: QuestionsDisplayConfig | None = Field(None, description="Questions display settings")

    disable_comments: bool = Field(False, description="Disable comments completely")
    repeat: bool = Field(False, description="Loop playback")
    compression: bool = Field(False, description="VK-side video compression")
    wallpost: bool = Field(False, description="Post to wall on upload")

    @field_validator("title_template", mode="before")
    @classmethod
    def _vk_preset_title_jinja(cls, v: str | None) -> str | None:
        return validate_optional_jinja_title(v)

    @field_validator("description_template", mode="before")
    @classmethod
    def _vk_preset_desc_jinja(cls, v: str | None) -> str | None:
        return validate_optional_jinja(v)


class YandexDiskExtraFileConfig(BaseModel):
    """Optional sidecar file on Disk. Presence in preset JSON enables upload for that file."""

    model_config = BASE_MODEL_CONFIG

    filename_template: str | None = Field(
        None,
        max_length=500,
        description="Jinja filename (default: video base name + extension)",
    )
    folder_path_template: str | None = Field(
        None,
        max_length=500,
        description="Jinja folder path on Disk (default: same folder as video)",
    )

    @field_validator("filename_template", "folder_path_template", mode="before")
    @classmethod
    def _validate_path_jinja(cls, v: str | None) -> str | None:
        return validate_optional_jinja(v)


class YandexDiskDescriptionTxtConfig(YandexDiskExtraFileConfig):
    """description.txt sidecar: optional content_template overrides preset description_template."""

    content_template: str | None = Field(
        None,
        max_length=5000,
        description=(
            "Jinja for file body. When unset, use rendered description_template; "
            "when that is empty, upload an empty file."
        ),
    )

    @field_validator("content_template", mode="before")
    @classmethod
    def _validate_content_jinja(cls, v: str | None) -> str | None:
        return validate_optional_jinja(v)


class YandexDiskPresetMetadata(BaseModel):
    """Preset metadata for Yandex Disk output target."""

    model_config = BASE_MODEL_CONFIG

    folder_path_template: str = Field(
        ...,
        description="Path template on Disk with Jinja (e.g. '/Video/{{ display_name }}')",
        examples=["/Video/Processed", "/Video/{{ display_name }}/{{ record_date_iso }}"],
    )
    filename_template: str | None = Field(
        None,
        max_length=500,
        description="Custom filename template (default: video.mp4)",
        examples=["{{ display_name }}.mp4", "{{ record_date_iso }}_{{ display_name }}.mp4"],
    )
    title_template: str | None = Field(
        None,
        max_length=500,
        description="Title template (same role as YouTube/VK; used for upload title)",
    )
    description_template: str | None = Field(
        None,
        max_length=5000,
        description="Description template (used for description.txt when content_template is unset)",
    )
    overwrite: bool = Field(False, description="Overwrite existing files on Disk")
    publish: bool = Field(
        False,
        description="After upload, publish the file on Disk and store the public URL in upload result",
    )
    subtitles_srt: YandexDiskExtraFileConfig | None = Field(None, description="Upload .srt next to video")
    subtitles_vtt: YandexDiskExtraFileConfig | None = Field(None, description="Upload .vtt next to video")
    transcription: YandexDiskExtraFileConfig | None = Field(
        None, description="Upload segments-style transcription .txt"
    )
    description_txt: YandexDiskDescriptionTxtConfig | None = Field(None, description="Upload description as .txt")

    @field_validator("folder_path_template", mode="before")
    @classmethod
    def _yandex_folder_jinja(cls, v: str) -> str:
        return validate_required_jinja(v)

    @field_validator("filename_template", mode="before")
    @classmethod
    def _yandex_filename_jinja(cls, v: str | None) -> str | None:
        return validate_optional_jinja(v)

    @field_validator("title_template", mode="before")
    @classmethod
    def _yandex_title_jinja(cls, v: str | None) -> str | None:
        return validate_optional_jinja_title(v)

    @field_validator("description_template", mode="before")
    @classmethod
    def _yandex_desc_jinja(cls, v: str | None) -> str | None:
        return validate_optional_jinja(v)


PresetMetadata = YouTubePresetMetadata | VKPresetMetadata | YandexDiskPresetMetadata
