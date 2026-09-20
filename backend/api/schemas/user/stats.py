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


class HomeSummary(BaseModel):
    """Current visible catalog counts, independent of the analytics period."""

    total: int
    published: int = Field(
        description="Visible recordings published by direct LEAP link or playable in a public playlist"
    )
    in_progress: int
    waiting_source: int
    paused: int
    error: int
