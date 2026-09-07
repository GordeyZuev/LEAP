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
