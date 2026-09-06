"""Automation filters schemas."""

from pydantic import BaseModel, ConfigDict, Field

# INITIALIZED plus MTS wait states so jobs keep pinging until MP4 is ready.
DEFAULT_AUTOMATION_STATUS_FILTER = ["INITIALIZED", "PENDING_CONVERSION", "PENDING_SOURCE"]


class AutomationFilters(BaseModel):
    """Filters for automation to select recordings for processing."""

    status: list[str] = Field(
        default_factory=lambda: list(DEFAULT_AUTOMATION_STATUS_FILTER),
        description=(
            "Statuses to process. Default includes INITIALIZED plus MTS wait states "
            "(PENDING_CONVERSION, PENDING_SOURCE). Empty list = all statuses."
        ),
    )
    exclude_blank: bool = Field(
        default=True,
        description="Exclude blank records (too short/small)",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": ["INITIALIZED", "PENDING_CONVERSION", "PENDING_SOURCE"],
                "exclude_blank": True,
            }
        }
    )
