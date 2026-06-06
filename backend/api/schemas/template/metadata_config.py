"""Typed schemas for metadata_config"""

from pydantic import BaseModel, Field, field_validator

from api.schemas.common import BASE_MODEL_CONFIG

from .jinja_field_validators import validate_optional_jinja, validate_optional_jinja_title
from .preset_metadata import QuestionsDisplayConfig, TopicsDisplayConfig


class VKMetadataConfig(BaseModel):
    model_config = BASE_MODEL_CONFIG

    album_id: str | None = Field(None, description="VK album ID")
    group_id: int | None = Field(None, gt=0, description="VK group ID for posting")
    thumbnail_name: str | None = Field(
        None,
        description="Thumbnail filename for VK (e.g., 'ml_extra.png'). API will find it in user directory.",
        examples=["ml_extra.png", "hse_ai.jpg", "custom_thumbnail.png"],
    )
    title_template: str | None = Field(None, max_length=500, description="VK-specific title template")
    description_template: str | None = Field(None, max_length=5000, description="VK-specific description template")

    # Overrides mirroring VKPresetMetadata (all optional: None = inherit from preset).
    privacy_view: int | None = Field(None, ge=0, le=3, description="Who can view (0=all,1=friends,2=fof,3=only me)")
    privacy_comment: int | None = Field(
        None, ge=0, le=3, description="Who can comment (0=all,1=friends,2=fof,3=only me)"
    )
    wallpost: bool | None = Field(None, description="Post to wall on upload")
    disable_comments: bool | None = Field(None, description="Disable comments completely")
    repeat: bool | None = Field(None, description="Loop playback")
    compression: bool | None = Field(None, description="VK-side video compression")

    @field_validator("title_template", mode="before")
    @classmethod
    def _vk_title_jinja(cls, v: str | None) -> str | None:
        return validate_optional_jinja_title(v)

    @field_validator("description_template", mode="before")
    @classmethod
    def _vk_desc_jinja(cls, v: str | None) -> str | None:
        return validate_optional_jinja(v)


class YouTubeMetadataConfig(BaseModel):
    model_config = BASE_MODEL_CONFIG

    privacy: str | None = Field(None, description="Privacy status (public, unlisted, private)")
    playlist_id: str | None = Field(None, description="YouTube playlist ID")
    thumbnail_name: str | None = Field(
        None,
        description="Thumbnail filename (e.g. 'python_base.png'). API will find it in user directory.",
        examples=["python_base.png", "hse_ai.jpg", "custom_thumbnail.png"],
    )
    title_template: str | None = Field(None, max_length=500, description="YouTube-specific title template")
    description_template: str | None = Field(None, max_length=5000, description="YouTube-specific description template")

    # Overrides mirroring YouTubePresetMetadata (all optional: None = inherit from preset/base).
    category_id: str | None = Field(None, description="YouTube category override (e.g. '27' = Education)")
    tags: list[str] | None = Field(None, max_length=500, description="Video tags override (max 500)")
    made_for_kids: bool | None = Field(None, description="Content for kids (COPPA)")
    embeddable: bool | None = Field(None, description="Allow embedding on other sites")
    license: str | None = Field(None, description="License type (youtube, creativeCommon)")
    default_language: str | None = Field(None, description="Default language", examples=["ru", "en"])
    publish_at: str | None = Field(None, description="ISO 8601 publish date/time (scheduled publishing)")
    disable_comments: bool | None = Field(None, description="Disable comments")
    rating_disabled: bool | None = Field(None, description="Disable like/dislike ratings")
    notify_subscribers: bool | None = Field(None, description="Notify subscribers about publication")

    @field_validator("category_id")
    @classmethod
    def validate_category_id(cls, v: str | None) -> str | None:
        if v is None:
            return v
        try:
            cat_int = int(v)
            if cat_int < 1:
                raise ValueError("category_id must be positive")
        except ValueError:
            raise ValueError("category_id must be a number")
        return str(cat_int)

    @field_validator("title_template", mode="before")
    @classmethod
    def _yt_title_jinja(cls, v: str | None) -> str | None:
        return validate_optional_jinja_title(v)

    @field_validator("description_template", mode="before")
    @classmethod
    def _yt_desc_jinja(cls, v: str | None) -> str | None:
        return validate_optional_jinja(v)


class YandexDiskMetadataConfig(BaseModel):
    """Yandex Disk metadata overrides at template level."""

    model_config = BASE_MODEL_CONFIG

    folder_path_template: str | None = Field(
        None,
        max_length=500,
        description="Override folder path template for this template",
        examples=["/Video/{{ display_name }}", "/Lectures/{{ record_date_iso }}"],
    )
    filename_template: str | None = Field(
        None,
        max_length=500,
        description="Override filename template",
    )
    overwrite: bool | None = Field(None, description="Override preset overwrite when set")
    publish: bool | None = Field(None, description="Override preset publish when set")

    @field_validator("folder_path_template", mode="before")
    @classmethod
    def _yd_folder_jinja(cls, v: str | None) -> str | None:
        return validate_optional_jinja(v)

    @field_validator("filename_template", mode="before")
    @classmethod
    def _yd_file_jinja(cls, v: str | None) -> str | None:
        return validate_optional_jinja(v)


class TemplateMetadataConfig(BaseModel):
    """
    Content-specific metadata for Recording Template.

    Thumbnail hierarchy:
    1. Platform-specific (vk.thumbnail_name / youtube.thumbnail_name)
    2. Common thumbnail_name
    3. Preset thumbnail

    Jinja variables: {{ display_name }}, {{ themes }}, {{ topics }}, {{ summary }}, {{ record_date_iso }}, {{ record_datetime }}, etc. (precomputed date strings in the recording owner's timezone).
    """

    model_config = BASE_MODEL_CONFIG

    vk: VKMetadataConfig | None = Field(None, description="VK-specific settings")
    youtube: YouTubeMetadataConfig | None = Field(None, description="YouTube-specific settings")
    yandex_disk: YandexDiskMetadataConfig | None = Field(None, description="Yandex Disk-specific settings")

    title_template: str | None = Field(
        None,
        max_length=500,
        description="Title template with variables",
        examples=[
            "AI Course | {{ themes }} ({{ record_date_short }})",
            "{{ display_name }} - {{ date }}",
            "RL | {{ themes }}",
        ],
    )

    description_template: str | None = Field(
        None,
        max_length=5000,
        description="Description template with variables",
        examples=[
            "Lecture\\n\\n{{ topics }}\\n\\n{{ questions }}\\n\\nRecorded: {{ record_date }}",
            "{{ summary }}",
            "Topics: {{ topics }}\\n\\nDuration: {{ duration }}",
        ],
    )

    topics_display: TopicsDisplayConfig | None = Field(
        None,
        description="Topics display settings",
    )
    questions_display: QuestionsDisplayConfig | None = Field(
        None,
        description="Questions display settings",
    )

    thumbnail_name: str | None = Field(
        None,
        description="Thumbnail filename for all platforms (if not platform-specific). API will find it in user directory.",
        examples=["applied_python.png", "ml_extra.png", "hse_ai.jpg"],
    )

    @field_validator("title_template", mode="before")
    @classmethod
    def validate_title_template(cls, v: str | None) -> str | None:
        return validate_optional_jinja_title(v)

    @field_validator("description_template", mode="before")
    @classmethod
    def validate_description_template(cls, v: str | None) -> str | None:
        return validate_optional_jinja(v)
