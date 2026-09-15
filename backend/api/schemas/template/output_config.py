"""Typed schemas for output_config"""

from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from api.schemas.common import BASE_MODEL_CONFIG


def normalize_output_config(raw: dict[str, Any] | None) -> dict[str, Any]:
    """Ensure JSONB output_config matches ``TemplateOutputConfig`` (legacy rows may omit lists)."""
    if not raw:
        return {
            "preset_ids": [],
            "playlist_ids": [],
            "channel_ids": [],
            "auto_upload": False,
            "upload_captions": True,
            "publish_leap": True,
        }
    out = dict(raw)
    preset_ids = out.get("preset_ids")
    if preset_ids is None or not isinstance(preset_ids, list):
        out["preset_ids"] = []
    playlist_ids = out.get("playlist_ids")
    if playlist_ids is None or not isinstance(playlist_ids, list):
        out["playlist_ids"] = []
    channel_ids = out.get("channel_ids")
    if channel_ids is None or not isinstance(channel_ids, list):
        out["channel_ids"] = []
    return out


class TemplateOutputConfig(BaseModel):
    """
    Output configuration for template.

    Fields:
    - preset_ids: list of presets for auto-upload (empty = manual upload only)
    - playlist_ids: LEAP course playlists (applied on LEAP publish after processing; not a YouTube playlist)
    - auto_upload: automatic copy upload after processing (YouTube / Yandex Disk)
    - publish_leap: run LEAP publish after processing when a leap preset, playlists, or share is configured
    - upload_captions: upload subtitles with video (if platform supports)
    """

    model_config = BASE_MODEL_CONFIG

    preset_ids: list[int] = Field(
        default_factory=list,
        description="List of preset IDs for auto-upload (empty when upload is manual only)",
        examples=[[], [1], [1, 2, 3]],
    )

    playlist_ids: list[int] = Field(
        default_factory=list,
        description="LEAP playlist IDs applied when LEAP publish runs after processing",
        examples=[[], [1], [1, 2]],
    )

    channel_ids: list[int] = Field(
        default_factory=list,
        description="LEAP channel IDs: recording is appended to Videos after processing",
        examples=[[], [1], [1, 2]],
    )

    auto_upload: bool = Field(
        False,
        description="Auto-upload after processing (if False - manual upload only)",
    )

    publish_leap: bool = Field(
        True,
        description="Publish to LEAP after processing (look preset, playlist_ids, or auto_share)",
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

    @field_validator("playlist_ids", mode="before")
    @classmethod
    def coerce_playlist_ids(cls, v: Any) -> list[int]:
        if v is None:
            return []
        if not isinstance(v, list):
            return []
        return v

    @field_validator("playlist_ids")
    @classmethod
    def validate_playlist_ids(cls, v: list[int]) -> list[int]:
        if not v:
            return v
        if len(v) > 10:
            raise ValueError("Maximum 10 playlists per template")
        if any(pid <= 0 for pid in v):
            raise ValueError("playlist_ids must be positive numbers")
        if len(v) != len(set(v)):
            raise ValueError("playlist_ids must be unique")
        return v

    @field_validator("channel_ids", mode="before")
    @classmethod
    def coerce_channel_ids(cls, v: Any) -> list[int]:
        if v is None:
            return []
        if not isinstance(v, list):
            return []
        return v

    @field_validator("channel_ids")
    @classmethod
    def validate_channel_ids(cls, v: list[int]) -> list[int]:
        if not v:
            return v
        if len(v) > 10:
            raise ValueError("Maximum 10 channels per template")
        if any(pid <= 0 for pid in v):
            raise ValueError("channel_ids must be positive numbers")
        if len(v) != len(set(v)):
            raise ValueError("channel_ids must be unique")
        return v

    @model_validator(mode="after")
    def auto_upload_requires_presets(self) -> "TemplateOutputConfig":
        if self.auto_upload and not self.preset_ids:
            raise ValueError("auto_upload=True requires at least one copy preset (not leap-only)")
        return self
