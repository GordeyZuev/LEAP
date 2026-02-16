"""User statistics schemas."""

from datetime import date

from pydantic import BaseModel, Field


class StatsPeriod(BaseModel):
    """Date range for statistics."""

    from_date: date = Field(..., alias="from")
    to_date: date = Field(..., alias="to")

    model_config = {"populate_by_name": True}


class TemplateStats(BaseModel):
    """Recordings fully processed by a single template."""

    template_id: int
    template_name: str | None
    count: int


class UserStatsResponse(BaseModel):
    """User usage statistics for a given period."""

    period: StatsPeriod | None = Field(None, description="Date range; null = all time")

    recordings_total: int = Field(0, description="Total recordings (not deleted)")
    recordings_by_status: dict[str, int] = Field(default_factory=dict)
    recordings_ready_by_template: list[TemplateStats] = Field(default_factory=list)

    transcription_total_seconds: float = Field(
        0.0, description="Sum of final_duration (seconds) for transcribed recordings"
    )
    storage_bytes: int = Field(0, description="User folder size on disk")
    storage_gb: float = Field(0.0, description="User folder size in GB")
