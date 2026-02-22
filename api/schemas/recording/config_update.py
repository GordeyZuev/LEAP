"""Typed schemas for recording config partial update (PUT /recordings/{id}/config)."""

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from api.schemas.common import BASE_MODEL_CONFIG


class TranscriptionProcessingConfigUpdate(BaseModel):
    """Partial processing config update. All fields optional for merge."""

    model_config = BASE_MODEL_CONFIG

    enable_transcription: bool | None = Field(None, description="Enable transcription")
    prompt: str | None = Field(None, description="Prompt to improve transcription quality")
    language: str | None = Field(None, description="Audio language (ru, en, ...)")
    allow_errors: bool | None = Field(
        None,
        description="Allow processing to continue on transcription error",
    )
    enable_topics: bool | None = Field(None, description="Enable topics extraction")
    granularity: Literal["short", "medium", "long"] | None = Field(
        None,
        description="Topics granularity: short, medium, or long",
    )
    vocabulary: list[str] | None = Field(None, description="Key terms for transcriber")
    enable_subtitles: bool | None = Field(None, description="Enable subtitles generation")


class ProcessingConfigUpdate(BaseModel):
    """Partial processing config update for recording. Merged with existing config."""

    model_config = BASE_MODEL_CONFIG

    transcription: TranscriptionProcessingConfigUpdate | None = Field(
        None,
        description="Transcription and topics settings",
    )
    transcription_vocabulary: list[str] | None = Field(
        None,
        description="Special terms for transcriber",
    )


class OutputConfigUpdate(BaseModel):
    """Partial output config update for recording. Merged with existing config."""

    model_config = BASE_MODEL_CONFIG

    preset_ids: list[int] | None = Field(
        None,
        description="Preset IDs for auto-upload (replaces existing when provided)",
    )
    auto_upload: bool | None = Field(None, description="Auto-upload after processing")
    upload_captions: bool | None = Field(None, description="Upload subtitles with video")

    @field_validator("preset_ids")
    @classmethod
    def validate_preset_ids(cls, v: list[int] | None) -> list[int] | None:
        if v is None:
            return None
        if len(v) > 10:
            raise ValueError("Maximum 10 presets per recording")
        if any(pid <= 0 for pid in v):
            raise ValueError("preset_ids must be positive numbers")
        if len(v) != len(set(v)):
            raise ValueError("preset_ids must be unique")
        return v


class RecordingConfigUpdateRequest(BaseModel):
    """Request body for PUT /recordings/{id}/config. Partial update, merged with existing."""

    model_config = BASE_MODEL_CONFIG

    processing_config: ProcessingConfigUpdate | None = Field(
        None,
        description="Override processing settings (transcription, topics, subtitles)",
    )
    output_config: OutputConfigUpdate | None = Field(
        None,
        description="Override output settings (preset_ids, auto_upload)",
    )
