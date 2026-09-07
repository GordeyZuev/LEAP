"""Typed schemas for preset_metadata"""

from __future__ import annotations

from collections.abc import Mapping
from enum import Enum, StrEnum
from typing import Any, Self

from pydantic import BaseModel, Field, field_validator, model_validator

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

    enabled: bool = Field(True, description="Kept for storage; Jinja {{ topics }} gates inclusion")
    format: TopicsDisplayFormat = Field(TopicsDisplayFormat.NUMBERED_LIST, description="List format")
    max_count: int | None = Field(
        None, ge=1, le=999, description="Max timestamps count (None = default from base config)"
    )
    min_length: int | None = Field(None, ge=0, le=500, description="Min line length in chars (0 = no filtering)")
    max_length: int | None = Field(None, ge=10, le=1000, description="Max line length in chars")
    prefix: str | None = Field(None, max_length=200, description="Prefix before the timestamps list")
    separator: str = Field("\n", max_length=10, description="Separator between timestamp lines")
    show_timestamps: bool = Field(True, description="Prefix each {{ topics }} line with a timecode")

    @field_validator("prefix")
    @classmethod
    def validate_prefix(cls, v: str | None) -> str | None:
        if v is not None:
            v = v.strip()
            return v if v else None
        return v

    @model_validator(mode="after")
    def apply_effective_defaults(self) -> Self:
        """Null numeric fields mean «use render default» (same as TemplateRenderer._format_topics_list)."""
        if self.max_count is None:
            self.max_count = 999
        if self.min_length is None:
            self.min_length = 0
        if self.max_length is None:
            self.max_length = 999
        if self.prefix is None:
            self.prefix = ""
        return self


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

    @model_validator(mode="after")
    def apply_effective_defaults(self) -> Self:
        if self.max_count is None:
            self.max_count = 20
        if self.min_length is None:
            self.min_length = 0
        if self.max_length is None:
            self.max_length = 1000
        if self.prefix is None:
            self.prefix = ""
        return self


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
        description="Title template with variables (e.g. '{{ display_name }} | {{ themes }}')",
    )
    description_template: str | None = Field(
        None,
        max_length=5000,
        description="Description template with variables (e.g. '{{ summary }}\\n\\n{{ topics }}\\n\\n{{ questions }}')",
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

    topics_display: TopicsDisplayConfig | None = Field(
        None, description="Formatting for Jinja {{ topics }} (UI: Timestamps)"
    )
    questions_display: QuestionsDisplayConfig | None = Field(
        None, description="Formatting for Jinja {{ questions }} (UI: Questions)"
    )

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
        description="Title template with variables (e.g. '{{ display_name }}')",
    )
    description_template: str | None = Field(
        None,
        max_length=5000,
        description="Description template with variables (e.g. '{{ summary }}\\n\\n{{ topics }}\\n\\n{{ questions }}')",
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

    topics_display: TopicsDisplayConfig | None = Field(
        None, description="Formatting for Jinja {{ topics }} (UI: Timestamps)"
    )
    questions_display: QuestionsDisplayConfig | None = Field(
        None, description="Formatting for Jinja {{ questions }} (UI: Questions)"
    )

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


class LeapPresetMetadata(BaseModel):
    """Look profile for LEAP course/share titles — not an upload target."""

    model_config = BASE_MODEL_CONFIG

    title_template: str | None = Field(
        None,
        max_length=500,
        description="Publication title Jinja (course/share). Empty render falls back to display_name.",
    )
    description_template: str | None = Field(
        None,
        max_length=5000,
        description="Publication description Jinja for share Overview when this preset is resolved.",
    )
    thumbnail_name: str | None = Field(
        None,
        description="Cover filename only (e.g. 'python_base.png').",
        examples=["python_base.png", "ml_extra.png"],
    )

    @field_validator("title_template", mode="before")
    @classmethod
    def _leap_title_jinja(cls, v: str | None) -> str | None:
        return validate_optional_jinja_title(v)

    @field_validator("description_template", mode="before")
    @classmethod
    def _leap_desc_jinja(cls, v: str | None) -> str | None:
        return validate_optional_jinja(v)

    @field_validator("thumbnail_name")
    @classmethod
    def _thumbnail_filename_only(cls, v: str | None) -> str | None:
        if v is None:
            return None
        name = v.strip()
        if not name:
            return None
        if "/" in name or "\\" in name or name.startswith("."):
            raise ValueError("thumbnail_name must be a filename without path")
        return name


PresetMetadata = YouTubePresetMetadata | VKPresetMetadata | YandexDiskPresetMetadata | LeapPresetMetadata


def coerce_preset_metadata(platform: str, raw: Any) -> PresetMetadata:
    """Parse preset_metadata using ``platform`` so empty dicts are not YouTube by default."""
    payload: Mapping[str, Any]
    if isinstance(raw, BaseModel):
        payload = raw.model_dump()
    elif isinstance(raw, Mapping):
        payload = raw
    elif raw is None:
        payload = {}
    else:
        raise ValueError("preset_metadata must be an object")
    plat = (platform or "").lower()
    if plat == "leap":
        return LeapPresetMetadata.model_validate(payload)
    if plat == "youtube":
        return YouTubePresetMetadata.model_validate(payload)
    if plat == "vk":
        return VKPresetMetadata.model_validate(payload)
    if plat == "yandex_disk":
        return YandexDiskPresetMetadata.model_validate(payload)
    raise ValueError(f"Unknown platform {platform!r}")


_NUMERIC_BOUND_FIELDS = ("max_count", "min_length", "max_length")


def normalize_topics_display(raw: Mapping[str, Any] | None) -> dict[str, Any]:
    """Merge partial/null topics_display with effective render defaults."""
    return TopicsDisplayConfig.model_validate(dict(raw or {})).model_dump(mode="json")


def normalize_questions_display(raw: Mapping[str, Any] | None) -> dict[str, Any]:
    """Merge partial/null questions_display with effective render defaults."""
    return QuestionsDisplayConfig.model_validate(dict(raw or {})).model_dump(mode="json")


def _numeric_field_bounds(model: type[BaseModel]) -> dict[str, dict[str, int]]:
    bounds: dict[str, dict[str, int]] = {}
    for name in _NUMERIC_BOUND_FIELDS:
        ge, le = 0, 999999
        for item in model.model_fields[name].metadata:
            item_ge = getattr(item, "ge", None)
            item_le = getattr(item, "le", None)
            if item_ge is not None:
                ge = item_ge
            if item_le is not None:
                le = item_le
        bounds[name] = {"min": int(ge), "max": int(le)}
    return bounds


def display_config_defaults_payload() -> dict[str, Any]:
    """Payload for GET /api/v1/references/display-config-defaults."""
    return {
        "topics": normalize_topics_display(None),
        "questions": normalize_questions_display(None),
        "bounds": {
            "topics": _numeric_field_bounds(TopicsDisplayConfig),
            "questions": _numeric_field_bounds(QuestionsDisplayConfig),
        },
    }
