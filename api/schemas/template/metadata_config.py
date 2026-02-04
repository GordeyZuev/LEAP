"""Typed schemas for metadata_config"""

from pydantic import BaseModel, Field, field_validator

from api.schemas.common import BASE_MODEL_CONFIG

from .preset_metadata import TopicsDisplayConfig


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


class TemplateMetadataConfig(BaseModel):
    """
    Content-specific metadata for Recording Template.

    Thumbnail hierarchy:
    1. Platform-specific (vk.thumbnail_name / youtube.thumbnail_name)
    2. Common thumbnail_name
    3. Preset thumbnail

    Template variables: {display_name}, {themes}, {topic}, {topics}, {topics_list},
    {summary}, {record_time}, {publish_time}, {date}, {duration}
    """

    model_config = BASE_MODEL_CONFIG

    vk: VKMetadataConfig | None = Field(None, description="VK-specific settings")
    youtube: YouTubeMetadataConfig | None = Field(None, description="YouTube-specific settings")

    title_template: str | None = Field(
        None,
        max_length=500,
        description="Title template with variables",
        examples=[
            "AI Course | {themes} ({record_time:DD.MM.YY})",
            "{display_name} - {date}",
            "RL | {themes}",
        ],
    )

    description_template: str | None = Field(
        None,
        max_length=5000,
        description="Description template with variables",
        examples=[
            "Lecture\\n\\n{topics}\\n\\nRecorded: {record_time:DD.MM.YYYY}",
            "{summary}",
            "Topics: {topics_list}\\n\\nDuration: {duration}",
        ],
    )

    topics_display: TopicsDisplayConfig | None = Field(
        None,
        description="Topics display settings",
    )

    thumbnail_name: str | None = Field(
        None,
        description="Thumbnail filename for all platforms (if not platform-specific). API will find it in user directory.",
        examples=["applied_python.png", "ml_extra.png", "hse_ai.jpg"],
    )

    @field_validator("title_template")
    @classmethod
    def validate_title_template(cls, v: str | None) -> str | None:
        if v is not None:
            v = v.strip()
            if not v:
                return None
            valid_vars = ["{display_name}", "{themes}", "{topic}", "{date}", "{record_time}", "{duration}"]
            if not any(var in v for var in valid_vars):
                raise ValueError(f"title_template must contain at least one variable from: {', '.join(valid_vars)}")
        return v
