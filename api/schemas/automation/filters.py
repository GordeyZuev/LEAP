"""Automation filters schemas."""

from pydantic import BaseModel, ConfigDict, Field


class AutomationFilters(BaseModel):
    """Filters for automation to select recordings for processing."""

    status: list[str] = Field(
        default=["INITIALIZED"],
        description="Statuses to process (default: INITIALIZED only)",
    )
    exclude_blank: bool = Field(
        default=True,
        description="Exclude blank records (too short/small)",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": ["INITIALIZED"],
                "exclude_blank": True,
            }
        }
    )
