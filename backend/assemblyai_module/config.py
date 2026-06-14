"""AssemblyAI transcription configuration."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from logger import get_logger

logger = get_logger()

ASSEMBLYAI_BASE_URL = "https://api.assemblyai.com"


class AssemblyAISettings(BaseSettings):
    """AssemblyAI operational settings. API key stays in config/assemblyai_creds.json."""

    model_config = SettingsConfigDict(
        env_prefix="ASSEMBLYAI_",
        case_sensitive=False,
        extra="ignore",
    )

    speech_models: list[str] = Field(
        default_factory=lambda: ["universal-3-pro", "universal-2"],
        description="Speech models in priority order (first available wins)",
    )
    language_code: str | None = Field(
        default="ru",
        description="Language code for transcription (e.g. 'ru', 'en'). None = language_detection.",
    )
    language_detection: bool = Field(
        default=False,
        description="Enable automatic language detection (overrides language_code if True)",
    )
    poll_interval: float = Field(
        default=3.0,
        ge=1.0,
        description="Polling interval in seconds",
    )
    max_wait_seconds: float = Field(
        default=3600.0,
        ge=60.0,
        description="Maximum wait time for transcription (seconds). 90-min lecture + queue buffer.",
    )


class AssemblyAIConfig:
    """AssemblyAI credentials + operational settings."""

    def __init__(self, api_key: str, settings: AssemblyAISettings) -> None:
        if not api_key:
            raise ValueError("api_key is required")
        self.api_key = api_key
        self.settings = settings
        self.base_url = ASSEMBLYAI_BASE_URL

    @classmethod
    def from_file(cls, config_file: str = "config/assemblyai_creds.json") -> AssemblyAIConfig:
        """Load API key from JSON file; operational settings from env ASSEMBLYAI_*."""
        config_path = Path(config_file)
        if not config_path.exists():
            raise FileNotFoundError(f'Config not found: {config_file}\nCreate with: {{"api_key": "aai_..."}}')

        with config_path.open(encoding="utf-8") as fp:
            data = json.load(fp)

        api_key = data.get("api_key", "")
        if not api_key:
            raise ValueError("api_key missing in config")

        from config.settings import get_settings

        settings = get_settings().assemblyai
        return cls(api_key=api_key, settings=settings)
