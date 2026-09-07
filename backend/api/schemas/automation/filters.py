"""Automation filters schemas."""

from pydantic import BaseModel, ConfigDict, Field, field_validator

from models.recording import ProcessingStatus

# INITIALIZED plus MTS wait states so jobs keep pinging until MP4 is ready.
DEFAULT_AUTOMATION_STATUS_FILTER = ["INITIALIZED", "PENDING_CONVERSION", "PENDING_SOURCE"]
_VALID_STATUS_VALUES = {item.value for item in ProcessingStatus}


def sanitize_automation_status_filter(raw: object) -> list[str] | None:
    """Return statuses for SQL IN, None for every status, or the MTS-aware default.

    Missing/invalid shapes → default. Empty list → all statuses. Unknown names
    (legacy FAILED / TRANSCRIBED) are dropped so Postgres enum IN (...) cannot
    abort a job.
    """
    if raw is None:
        return list(DEFAULT_AUTOMATION_STATUS_FILTER)
    if not isinstance(raw, list):
        return list(DEFAULT_AUTOMATION_STATUS_FILTER)
    if not raw:
        return None
    kept = [s for s in raw if isinstance(s, str) and s in _VALID_STATUS_VALUES]
    if not kept:
        return list(DEFAULT_AUTOMATION_STATUS_FILTER)
    return kept


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

    @field_validator("status", mode="before")
    @classmethod
    def _drop_unknown_statuses(cls, value: object) -> object:
        if value is None:
            return list(DEFAULT_AUTOMATION_STATUS_FILTER)
        if not isinstance(value, list):
            return list(DEFAULT_AUTOMATION_STATUS_FILTER)
        if not value:
            return []
        kept = [s for s in value if isinstance(s, str) and s in _VALID_STATUS_VALUES]
        return kept if kept else list(DEFAULT_AUTOMATION_STATUS_FILTER)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": ["INITIALIZED", "PENDING_CONVERSION", "PENDING_SOURCE"],
                "exclude_blank": True,
            }
        }
    )
