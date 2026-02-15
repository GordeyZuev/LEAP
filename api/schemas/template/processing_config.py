"""Typed schemas for processing_config"""

from typing import Literal

from pydantic import BaseModel, Field

from api.schemas.common import BASE_MODEL_CONFIG


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
    granularity: Literal["short", "medium", "long"] = Field(
        "long", description="Topics granularity: short, medium, or long"
    )

    vocabulary: list[str] | None = Field(
        None,
        description="Key terms for transcriber to improve recognition (e.g. ML terms, names)",
    )

    enable_subtitles: bool = Field(True, description="Enable subtitles generation")


TemplateProcessingConfig.model_rebuild()
