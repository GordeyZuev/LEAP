"""Typed schemas for output_config"""

from pydantic import BaseModel, Field, field_validator

from api.schemas.common import BASE_MODEL_CONFIG


class TemplateOutputConfig(BaseModel):
    """
    Output configuration for template.

    Fields:
    - preset_ids: list of presets for auto-upload
    - auto_upload: automatic upload after processing
    - upload_captions: upload subtitles with video (if platform supports)
    """

    model_config = BASE_MODEL_CONFIG

    preset_ids: list[int] = Field(
        ...,
        description="List of preset IDs for auto-upload",
        min_length=1,
        examples=[[1], [1, 2, 3]],
    )

    auto_upload: bool = Field(
        False,
        description="Auto-upload after processing (if False - manual upload only)",
    )

    upload_captions: bool = Field(
        True,
        description="Upload captions with video (if platform supports)",
    )

    @field_validator("preset_ids")
    @classmethod
    def validate_preset_ids(cls, v: list[int]) -> list[int]:
        if not v:
            raise ValueError("preset_ids cannot be empty")
        if len(v) > 10:
            raise ValueError("Maximum 10 presets per template")
        if any(pid <= 0 for pid in v):
            raise ValueError("preset_ids must be positive numbers")
        if len(v) != len(set(v)):
            raise ValueError("preset_ids must be unique")
        return v
