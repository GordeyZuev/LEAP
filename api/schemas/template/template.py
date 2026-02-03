"""Recording template schemas (fully typed)"""

from datetime import datetime

from pydantic import BaseModel, Field, field_validator, model_validator

from api.schemas.common import BASE_MODEL_CONFIG, ORM_MODEL_CONFIG, strip_and_validate_name

from .matching_rules import MatchingRules
from .metadata_config import TemplateMetadataConfig
from .output_config import TemplateOutputConfig
from .processing_config import TemplateProcessingConfig


class RecordingTemplateBase(BaseModel):
    model_config = BASE_MODEL_CONFIG

    name: str = Field(..., min_length=3, max_length=255, description="Template name")
    description: str | None = Field(None, max_length=1000, description="Template description")

    matching_rules: MatchingRules | None = Field(
        None,
        description="Recording matching rules",
    )
    processing_config: TemplateProcessingConfig | None = Field(
        None,
        description="Processing settings: transcription, topics, subtitles",
    )
    metadata_config: TemplateMetadataConfig | None = Field(
        None,
        description="Content metadata: title_template, playlist_id",
    )
    output_config: TemplateOutputConfig | None = Field(
        None,
        description="Output settings: preset_ids, auto_upload",
    )

    @field_validator("name", mode="before")
    @classmethod
    def strip_name(cls, v: str) -> str:
        return strip_and_validate_name(v)


class RecordingTemplateCreate(RecordingTemplateBase):
    is_draft: bool = Field(False, description="Draft (not applied automatically)")

    @model_validator(mode="after")
    def validate_template(self) -> "RecordingTemplateCreate":
        if not self.is_draft:
            if not self.matching_rules:
                raise ValueError("Non-draft template requires matching_rules")

            rules = self.matching_rules
            has_rule = (
                (rules.exact_matches and len(rules.exact_matches) > 0)
                or (rules.keywords and len(rules.keywords) > 0)
                or (rules.patterns and len(rules.patterns) > 0)
                or (rules.source_ids and len(rules.source_ids) > 0)
            )

            if not has_rule:
                raise ValueError(
                    "matching_rules must contain at least one rule (exact_matches, keywords, patterns or source_ids)"
                )

        if self.output_config and self.output_config.auto_upload:
            if not self.processing_config:
                raise ValueError("auto_upload=True requires processing_config")

        if self.metadata_config and self.metadata_config.title_template:
            if not self.output_config:
                raise ValueError("title_template requires output_config with preset_ids")

        return self


class RecordingTemplateUpdate(BaseModel):
    name: str | None = Field(None, min_length=3, max_length=255)
    description: str | None = Field(None, max_length=1000)
    matching_rules: MatchingRules | None = None
    processing_config: TemplateProcessingConfig | None = None
    metadata_config: TemplateMetadataConfig | None = None
    output_config: TemplateOutputConfig | None = None
    is_draft: bool | None = None
    is_active: bool | None = None


class RecordingTemplateResponse(RecordingTemplateBase):
    model_config = ORM_MODEL_CONFIG

    id: int
    user_id: str
    is_draft: bool
    is_active: bool
    used_count: int
    last_used_at: datetime | None
    created_at: datetime
    updated_at: datetime


class RecordingTemplateListResponse(BaseModel):
    model_config = ORM_MODEL_CONFIG

    id: int
    name: str
    description: str | None
    is_draft: bool
    is_active: bool
    used_count: int
    created_at: datetime
    updated_at: datetime
