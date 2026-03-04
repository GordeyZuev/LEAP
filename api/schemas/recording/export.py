"""Recording export schemas."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .filters import RecordingFilters


class ExportRecordingsRequest(BaseModel):
    """
    Request schema for recording export.

    Supports two modes: explicit recording_ids or filters-based selection.
    Only one mode can be used at a time.
    """

    recording_ids: list[int] | None = Field(None, description="Explicit list of recording IDs", min_length=1)
    filters: RecordingFilters | None = Field(None, description="Filters for automatic selection")
    limit: int = Field(2000, ge=1, le=2000, description="Maximum recordings when using filters")
    format: Literal["json", "csv", "xlsx"] = Field(
        "json",
        description="Export format: json, csv, or xlsx",
    )
    verbosity: Literal["short", "long"] = Field(
        "short",
        description="Short: core fields + platform URLs. Long: full details.",
    )

    @model_validator(mode="after")
    def validate_input(self):
        """Validate that either recording_ids or filters is specified."""
        if not self.recording_ids and not self.filters:
            raise ValueError("Specify recording_ids or filters")
        if self.recording_ids and self.filters:
            raise ValueError("Specify only recording_ids OR filters, not both")
        return self

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "recording_ids": [1, 2, 3],
                    "format": "csv",
                    "verbosity": "short",
                },
                {
                    "filters": {
                        "template_id": 5,
                        "status": ["READY"],
                        "from_date": "2025-01-01",
                        "to_date": "2025-12-31",
                    },
                    "limit": 500,
                    "format": "xlsx",
                    "verbosity": "long",
                },
            ]
        }
    )
