"""Request schema for creating template from recording."""

from pydantic import BaseModel, Field, field_validator

from api.schemas.common import BASE_MODEL_CONFIG, strip_and_validate_name


class TemplateFromRecordingRequest(BaseModel):
    """Request body for POST /templates/from-recording/{recording_id}."""

    model_config = BASE_MODEL_CONFIG

    name: str = Field(..., min_length=3, max_length=255, description="Template name")

    @field_validator("name", mode="before")
    @classmethod
    def strip_name(cls, v: str) -> str:
        return strip_and_validate_name(v)

    description: str | None = Field(None, max_length=1000, description="Template description")
    match_pattern: str | None = Field(
        None,
        description="Custom regex pattern for matching (if not set, uses exact match by display_name)",
    )
    match_source_id: bool = Field(
        False,
        description="Include recording's input_source_id in matching rules",
    )
