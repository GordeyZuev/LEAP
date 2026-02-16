"""Fireworks Audio Inference API configuration"""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from logger import get_logger

logger = get_logger()


class FireworksConfig(BaseSettings):
    """Fireworks Audio API configuration. Docs: https://docs.fireworks.ai/api-reference/audio-transcriptions"""

    model_config = SettingsConfigDict(
        env_file=None,
        extra="ignore",
        case_sensitive=False,
    )

    api_key: str = Field(..., description="Fireworks API ключ")
    model: Literal["whisper-v3", "whisper-v3-turbo"] = Field(
        default="whisper-v3-turbo",
        description="ASR model for transcription",
    )
    base_url: str = Field(
        default="https://audio-turbo.api.fireworks.ai",
        description="Base URL for API (depends on model)",
    )
    account_id: str | None = Field(
        default=None,
        description="Account ID for Batch API (from Fireworks dashboard)",
    )
    batch_base_url: str = Field(
        default="https://audio-batch.api.fireworks.ai",
        description="Base URL for Batch API",
    )

    language: str | None = Field(
        default="ru",
        description="Language for transcription (ISO 639-1 code)",
    )
    response_format: Literal["json", "text", "srt", "verbose_json", "vtt"] = Field(
        default="verbose_json",
        description="Response format from API",
    )
    timestamp_granularities: list[Literal["word", "segment"]] | None = Field(
        default=None,
        description="Timestamp granularities (required for verbose_json)",
    )
    alignment_model: Literal["mms_fa", "tdnn_ffn", "gentle"] | None = Field(
        default=None,
        description="Alignment model (mms_fa for multilingual, tdnn_ffn/gentle for English)",
    )
    diarize: bool = Field(
        default=False,
        description="Enable speaker diarization (requires verbose_json and word in timestamp_granularities)",
    )
    vad_model: Literal["silero", "whisperx-pyannet"] | None = Field(
        default=None,
        description="VAD model (Voice Activity Detection)",
    )
    temperature: float | list[float] | None = Field(
        default=0.0,
        description="Sampling temperature (0.0-1.0) or list for fallback decoding",
    )
    prompt: str | None = Field(
        default=None,
        description="Prompt for improving transcription quality",
    )
    preprocessing: Literal["none", "dynamic", "soft_dynamic", "bass_dynamic"] | None = Field(
        default=None,
        description="Audio preprocessing mode",
    )

    min_speakers: int | None = Field(
        default=None,
        ge=1,
        description="Minimum number of speakers (requires diarize=true)",
    )
    max_speakers: int | None = Field(
        default=None,
        ge=1,
        description="Maximum number of speakers (requires diarize=true)",
    )

    max_file_size_mb: int = Field(
        default=1024,
        ge=1,
        description="Maximum file size in MB",
    )
    audio_bitrate: str = Field(
        default="64k",
        description="Audio bitrate for processing",
    )
    audio_sample_rate: int = Field(
        default=16000,
        ge=8000,
        le=48000,
        description="Audio sample rate (Hz)",
    )
    retry_attempts: int = Field(
        default=3,
        ge=1,
        description="Number of retry attempts on error",
    )
    retry_delay: float = Field(
        default=2.0,
        ge=0.0,
        description="Base delay for exponential backoff (seconds)",
    )

    @field_validator("timestamp_granularities", mode="before")
    @classmethod
    def validate_timestamp_granularities(cls, v: Any) -> list[str] | None:
        """Parse and validate timestamp granularities from string or list."""
        if v is None:
            return None
        if isinstance(v, str):
            return [g.strip() for g in v.split(",") if g.strip()]
        if isinstance(v, list):
            valid = {"word", "segment"}
            return [g for g in v if g in valid]
        return None

    @field_validator("base_url", mode="after")
    @classmethod
    def validate_base_url(cls, _v: str, info: Any) -> str:
        """Set base_url based on model (turbo vs prod)."""
        model = info.data.get("model", "whisper-v3-turbo")
        return (
            "https://audio-turbo.api.fireworks.ai"
            if model == "whisper-v3-turbo"
            else "https://audio-prod.api.fireworks.ai"
        )

    @model_validator(mode="after")
    def validate_config(self) -> FireworksConfig:
        """Validate field dependencies per Fireworks API requirements."""
        if self.response_format == "verbose_json" and not self.timestamp_granularities:
            logger.warning("verbose_json requires timestamp_granularities, setting default: ['segment']")
            self.timestamp_granularities = ["segment"]

        if self.diarize:
            if self.response_format != "verbose_json":
                raise ValueError(f"diarize requires response_format='verbose_json', got '{self.response_format}'")
            if not self.timestamp_granularities or "word" not in self.timestamp_granularities:
                raise ValueError(
                    f"diarize requires 'word' in timestamp_granularities, got {self.timestamp_granularities}"
                )

        if (self.min_speakers or self.max_speakers) and not self.diarize:
            logger.warning("min_speakers/max_speakers ignored without diarize=true")

        if self.min_speakers and self.max_speakers and self.max_speakers < self.min_speakers:
            raise ValueError(f"max_speakers ({self.max_speakers}) < min_speakers ({self.min_speakers})")

        return self

    @classmethod
    def from_file(cls, config_file: str = "config/fireworks_creds.json") -> FireworksConfig:
        """Load Fireworks config from JSON file."""
        from pathlib import Path

        config_path = Path(config_file)
        if not config_path.exists():
            raise FileNotFoundError(
                f'Config not found: {config_file}\nCreate with: {{"api_key": "your-fireworks-api-key"}}'
            )

        with config_path.open(encoding="utf-8") as fp:
            data = json.load(fp)

        api_key = data.pop("api_key", "")
        if not api_key:
            raise ValueError("api_key missing in config")

        try:
            return cls(api_key=api_key, **data)
        except Exception as e:
            logger.error(f"Config validation failed: {e}")
            raise

    def to_request_params(self) -> dict[str, Any]:
        """Convert config to Fireworks API request parameters."""
        params: dict[str, Any] = {
            "language": self.language,
            "response_format": self.response_format,
            "diarize": "true" if self.diarize else "false",
        }

        optional_fields = {
            "timestamp_granularities": self.timestamp_granularities,
            "alignment_model": self.alignment_model,
            "vad_model": self.vad_model,
            "prompt": self.prompt,
            "preprocessing": self.preprocessing,
        }
        params.update({k: v for k, v in optional_fields.items() if v})

        if self.temperature is not None:
            params["temperature"] = self.temperature

        if self.diarize:
            if self.min_speakers is not None:
                params["min_speakers"] = self.min_speakers
            if self.max_speakers is not None:
                params["max_speakers"] = self.max_speakers

        return params
