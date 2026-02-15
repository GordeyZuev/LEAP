"""DeepSeek API configuration"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, ValidationError, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from logger import get_logger

logger = get_logger()


class DeepSeekConfig(BaseSettings):
    """DeepSeek API configuration (direct or via Fireworks)"""

    model_config = SettingsConfigDict(
        env_file=None,
        extra="ignore",
        case_sensitive=False,
    )

    api_key: str = Field(..., description="DeepSeek API key")
    model: str = Field(
        default="deepseek-chat",
        description="DeepSeek model to use",
    )
    base_url: str = Field(
        default="https://api.deepseek.com/v1",
        description="Base URL for API (DeepSeek or Fireworks endpoint)",
    )

    temperature: float = Field(
        default=0.0,
        ge=0.0,
        le=2.0,
        description="Sampling temperature (0.0-2.0)",
    )
    max_tokens: int = Field(
        default=8000,
        ge=100,
        le=8192,
        description="Max tokens (DeepSeek limit: 8192, default 8000)",
    )

    top_p: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Top-p sampling (0.0-1.0)",
    )
    top_k: int | None = Field(
        default=None,
        ge=1,
        description="Top-k sampling (Fireworks-specific)",
    )
    presence_penalty: float | None = Field(
        default=None,
        ge=-2.0,
        le=2.0,
        description="Presence penalty (-2.0 to 2.0)",
    )
    frequency_penalty: float | None = Field(
        default=None,
        ge=-2.0,
        le=2.0,
        description="Frequency penalty (-2.0 to 2.0)",
    )
    reasoning_effort: Literal["low", "medium", "high", "none"] | None = Field(
        default=None,
        description="Reasoning effort level (Fireworks-specific)",
    )
    seed: int | None = Field(
        default=None,
        description="Seed for deterministic responses",
    )

    timeout: float = Field(
        default=120.0,
        ge=1.0,
        description="Request timeout in seconds",
    )

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, v: str) -> str:
        """Ensure base_url starts with http:// or https:// and has no trailing slash."""
        if not v.startswith(("http://", "https://")):
            raise ValueError("base_url must start with http:// or https://")
        return v.rstrip("/")

    @model_validator(mode="after")
    def validate_config(self) -> DeepSeekConfig:
        """Warn when Fireworks-specific params are set without Fireworks endpoint."""
        if (
            self.top_k is not None or self.reasoning_effort is not None
        ) and "fireworks.ai" not in self.base_url.lower():
            logger.warning("Fireworks-specific parameters set without Fireworks endpoint. May not work.")
        return self

    @classmethod
    def from_file(cls, config_file: str = "config/deepseek_creds.json") -> DeepSeekConfig:
        """
        Load DeepSeek config from JSON file.

        Args:
            config_file: Path to config file

        Returns:
            Validated DeepSeekConfig instance

        Raises:
            FileNotFoundError: Config file not found
            ValueError: API key missing or invalid
            ValidationError: Config field validation failed
        """
        config_path = Path(config_file)
        if not config_path.exists():
            raise FileNotFoundError(
                f'DeepSeek config file not found: {config_file}\nCreate file with: {{"api_key": "your-api-key-here"}}'
            )

        with config_path.open(encoding="utf-8") as f:
            data = json.load(f)

        api_key = data.get("api_key", "")
        if not api_key:
            raise ValueError("DeepSeek API key not specified in config")

        try:
            return cls(api_key=api_key, **{k: v for k, v in data.items() if k != "api_key"})
        except ValidationError as e:
            logger.error("DeepSeek config validation failed: {}", e)
            raise

    def to_request_params(self, use_fireworks_extras: bool = False) -> dict[str, Any]:
        """
        Build params dict for chat.completions.create().

        Supports DeepSeek and Fireworks DeepSeek (OpenAI-compatible API).
        use_fireworks_extras=False by default since standard OpenAI client
        does not support top_k, reasoning_effort.

        Args:
            use_fireworks_extras: If True, include top_k and reasoning_effort

        Returns:
            Params for API request
        """
        params: dict[str, Any] = {
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }

        if self.top_p is not None:
            params["top_p"] = self.top_p
        if self.presence_penalty is not None:
            params["presence_penalty"] = self.presence_penalty
        if self.frequency_penalty is not None:
            params["frequency_penalty"] = self.frequency_penalty

        # Fireworks-specific parameters (not supported by standard OpenAI client)
        if use_fireworks_extras:
            if self.top_k is not None:
                params["top_k"] = self.top_k
            if self.reasoning_effort is not None:
                params["reasoning_effort"] = self.reasoning_effort

        if self.seed is not None:
            params["seed"] = self.seed

        return params
