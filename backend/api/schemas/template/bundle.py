"""Template JSON bundle import/export schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from api.schemas.common import BASE_MODEL_CONFIG, strip_and_validate_name
from api.schemas.template.matching_rules import MatchingRules
from api.schemas.template.metadata_config import TemplateMetadataConfig
from api.schemas.template.output_config import TemplateOutputConfig, normalize_output_config
from api.schemas.template.processing_config import TemplateProcessingConfig
from api.schemas.template.validation import collect_template_warnings, validate_template_state


class BundleReferencePreset(BaseModel):
    model_config = BASE_MODEL_CONFIG

    id: int
    name: str | None = None
    platform: str | None = None
    missing: bool = False


class BundleReferenceSource(BaseModel):
    model_config = BASE_MODEL_CONFIG

    id: int
    name: str | None = None
    missing: bool = False


class BundleReferencePlaylist(BaseModel):
    model_config = BASE_MODEL_CONFIG

    id: int
    name: str | None = None
    missing: bool = False


class BundleReferenceChannel(BaseModel):
    model_config = BASE_MODEL_CONFIG

    id: int
    name: str | None = None
    slug: str | None = None
    missing: bool = False


class BundleReference(BaseModel):
    model_config = BASE_MODEL_CONFIG

    presets: list[BundleReferencePreset] = Field(default_factory=list)
    sources: list[BundleReferenceSource] = Field(default_factory=list)
    playlists: list[BundleReferencePlaylist] = Field(default_factory=list)
    channels: list[BundleReferenceChannel] = Field(default_factory=list)


class TemplateBundleExportItem(BaseModel):
    """One template in an export bundle (includes read-only flags for round-trip hints)."""

    model_config = BASE_MODEL_CONFIG

    id: int
    name: str
    description: str | None = None
    is_draft: bool
    is_active: bool
    is_default: bool = False
    matching_rules: MatchingRules | None = None
    processing_config: TemplateProcessingConfig | None = None
    metadata_config: TemplateMetadataConfig | None = None
    output_config: TemplateOutputConfig | None = None


class TemplateBundleExport(BaseModel):
    model_config = BASE_MODEL_CONFIG

    leap_template_bundle: Literal[1] = 1
    exported_at: datetime
    reference: BundleReference
    templates: list[TemplateBundleExportItem]


class TemplateBundleImportItem(BaseModel):
    """One template in import; optional id means update existing."""

    model_config = ConfigDict(extra="forbid")

    id: int | None = None
    name: str = Field(..., min_length=3, max_length=255)
    description: str | None = Field(None, max_length=1000)
    is_draft: bool = False
    is_active: bool = True
    matching_rules: MatchingRules | None = None
    processing_config: TemplateProcessingConfig | None = None
    metadata_config: TemplateMetadataConfig | None = None
    output_config: TemplateOutputConfig | None = None

    @field_validator("name", mode="before")
    @classmethod
    def strip_name(cls, v: str) -> str:
        return strip_and_validate_name(v)

    @field_validator("output_config", mode="before")
    @classmethod
    def normalize_output_config_field(cls, v: object) -> object:
        if isinstance(v, dict):
            return normalize_output_config(v)
        return v


class TemplateBundleImport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    leap_template_bundle: Literal[1] = 1
    exported_at: datetime | None = None
    reference: BundleReference | None = None
    templates: list[TemplateBundleImportItem] = Field(..., min_length=1)


class RecordingTemplateReplace(BaseModel):
    """Full document replace (PUT); all config sections must be sent explicitly (null clears JSONB)."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=3, max_length=255)
    description: str | None = Field(None, max_length=1000)
    is_draft: bool
    is_active: bool
    matching_rules: MatchingRules | None
    processing_config: TemplateProcessingConfig | None
    metadata_config: TemplateMetadataConfig | None
    output_config: TemplateOutputConfig | None

    @field_validator("name", mode="before")
    @classmethod
    def strip_name(cls, v: str) -> str:
        return strip_and_validate_name(v)

    @field_validator("output_config", mode="before")
    @classmethod
    def normalize_output_config_field(cls, v: object) -> object:
        if isinstance(v, dict):
            return normalize_output_config(v)
        return v

    def validate_business_rules(self, *, is_default: bool) -> None:
        validate_template_state(
            is_default=is_default,
            matching_rules=self.matching_rules,
            processing_config=self.processing_config,
            metadata_config=self.metadata_config,
            output_config=self.output_config,
        )

    def warnings(self, *, is_default: bool = False) -> list[tuple[str, str]]:
        return collect_template_warnings(
            self.matching_rules,
            is_draft=self.is_draft,
            is_default=is_default,
        )


class TemplateImportErrorItem(BaseModel):
    model_config = BASE_MODEL_CONFIG

    index: int
    name: str | None = None
    loc: list[str | int] = Field(default_factory=list)
    msg: str


class TemplateImportWarningItem(BaseModel):
    model_config = BASE_MODEL_CONFIG

    index: int
    code: str
    msg: str


class TemplateImportResultItem(BaseModel):
    model_config = BASE_MODEL_CONFIG

    id: int
    name: str


class TemplateImportResult(BaseModel):
    model_config = BASE_MODEL_CONFIG

    ok: bool
    dry_run: bool
    created: list[TemplateImportResultItem] = Field(default_factory=list)
    updated: list[TemplateImportResultItem] = Field(default_factory=list)
    errors: list[TemplateImportErrorItem] = Field(default_factory=list)
    warnings: list[TemplateImportWarningItem] = Field(default_factory=list)


class ValidateReplaceResponse(BaseModel):
    model_config = BASE_MODEL_CONFIG

    ok: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[TemplateImportWarningItem] = Field(default_factory=list)
