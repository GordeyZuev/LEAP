"""Typed schemas for output_config"""

from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from api.schemas.common import BASE_MODEL_CONFIG


def normalize_output_config(raw: dict[str, Any] | None) -> dict[str, Any]:
    """Ensure JSONB output_config matches ``TemplateOutputConfig`` (legacy rows may omit preset_ids)."""
    if not raw:
        return {"preset_ids": [], "auto_upload": False, "upload_captions": True}
    out = dict(raw)
    preset_ids = out.get("preset_ids")
    if preset_ids is None or not isinstance(preset_ids, list):
        out["preset_ids"] = []
    return out


class TemplateOutputConfig(BaseModel):
    """
    Output configuration for template.

    Fields:
    - preset_ids: list of presets for auto-upload (empty = manual upload only)
    - auto_upload: automatic upload after processing
    - upload_captions: upload subtitles with video (if platform supports)
    """

    model_config = BASE_MODEL_CONFIG

    preset_ids: list[int] = Field(
        default_factory=list,
        description="List of preset IDs for auto-upload (empty when upload is manual only)",
        examples=[[], [1], [1, 2, 3]],
    )

    auto_upload: bool = Field(
        False,
        description="Auto-upload after processing (if False - manual upload only)",
    )

    upload_captions: bool = Field(
        True,
        description="Upload captions with video (if platform supports)",
    )

    default_platforms: list[str] = Field(
        default_factory=list,
        description="Legacy upload.default_platforms carried through resolver merge",
    )

    @field_validator("preset_ids", mode="before")
    @classmethod
    def coerce_preset_ids(cls, v: Any) -> list[int]:
        if v is None:
            return []
        if not isinstance(v, list):
            return []
        return v

    @field_validator("preset_ids")
    @classmethod
    def validate_preset_ids(cls, v: list[int]) -> list[int]:
        if not v:
            return v
        if len(v) > 10:
            raise ValueError("Maximum 10 presets per template")
        if any(pid <= 0 for pid in v):
            raise ValueError("preset_ids must be positive numbers")
        if len(v) != len(set(v)):
            raise ValueError("preset_ids must be unique")
        return v

    @model_validator(mode="after")
    def auto_upload_requires_presets(self) -> "TemplateOutputConfig":
        if self.auto_upload and not self.preset_ids:
            raise ValueError("auto_upload=True requires at least one preset_id")
        return self
