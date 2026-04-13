"""Typed schemas for processing_config"""

from pydantic import BaseModel, Field

from api.schemas.common import BASE_MODEL_CONFIG
from api.shared.enums import Granularity


class TemplateProcessingConfig(BaseModel):
    """Processing configuration for template. All settings in transcription object (historical structure)."""

    model_config = BASE_MODEL_CONFIG

    transcription: "TranscriptionProcessingConfig" = Field(
        ...,
        description="Processing settings: transcription, topics, subtitles",
    )

    transcription_vocabulary: list[str] | None = Field(
        None,
        description="Special terms for transcriber (terms, names, abbreviations). Separate template field.",
    )


class TranscriptionProcessingConfig(BaseModel):
    """
    Combined processing settings (flat structure).

    Contains settings for:
    - Transcription (enable_transcription, prompt, language)
    - Topics extraction (enable_topics, granularity)
    - Subtitles (enable_subtitles)
    """

    model_config = BASE_MODEL_CONFIG

    enable_transcription: bool = Field(True, description="Enable transcription")
    prompt: str | None = Field(None, description="Prompt to improve transcription quality")
    language: str | None = Field(None, description="Audio language (ru, en, ...)", examples=["ru", "en"])
    allow_errors: bool = Field(
        False,
        description="Allow processing to continue on transcription error. "
        "If True - dependent stages will be skipped (topics, subtitles). "
        "If False - processing will stop and status will rollback to DOWNLOADED.",
    )

    enable_topics: bool = Field(True, description="Enable topics extraction")
    granularity: Granularity = Field(Granularity.LONG, description="Topics granularity: short, medium, or long")
    questions_count: int = Field(3, ge=1, le=10, description="Number of self-check questions to generate")

    vocabulary: list[str] | None = Field(
        None,
        description="Key terms for transcriber to improve recognition (e.g. ML terms, names)",
    )

    enable_subtitles: bool = Field(True, description="Enable subtitles generation")


TemplateProcessingConfig.model_rebuild()
