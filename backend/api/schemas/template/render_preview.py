"""Request/response for Jinja metadata render preview (no persistence)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class TemplateRenderPreviewRequest(BaseModel):
    """Preview rendered strings for template metadata; optional recording for real context."""

    model_config = ConfigDict(extra="forbid")

    title_template: str | None = Field(None, max_length=500)
    description_template: str | None = Field(None, max_length=5000)
    folder_path_template: str | None = Field(None, max_length=500)
    filename_template: str | None = Field(None, max_length=500)
    recording_id: int | None = Field(None, description="Use this recording's context (access-checked)")
    template_id: int | None = Field(None, description="Merge non-null body fields over saved template metadata")
    topics_display: dict[str, Any] | None = Field(
        None, description="Override topics_display for context (same shape as preset)"
    )
    questions_display: dict[str, Any] | None = Field(None, description="Override questions_display for context")


class PresetRenderPreviewRequest(BaseModel):
    """Preview upload metadata strings as for an output preset."""

    model_config = ConfigDict(extra="forbid")

    title_template: str | None = Field(None, max_length=500)
    description_template: str | None = Field(None, max_length=5000)
    folder_path_template: str | None = Field(None, max_length=500)
    filename_template: str | None = Field(None, max_length=500)
    recording_id: int | None = Field(None)
    topics_display: dict[str, Any] | None = None
    questions_display: dict[str, Any] | None = None


class MetadataRenderPreviewResponse(BaseModel):
    """Result of a dry-run render (always 200; inspect valid and errors)."""

    model_config = ConfigDict(extra="forbid")

    valid: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    rendered_title: str | None = None
    rendered_description: str | None = None
    rendered_folder_path: str | None = None
    rendered_filename: str | None = None
