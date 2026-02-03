"""Recording filter schemas"""

from pydantic import BaseModel, ConfigDict, Field


class RecordingFilters(BaseModel):
    """
    Filters for bulk operations over recordings.

    Supports filtering by various criteria for automatic selection of records.
    """

    # Connections
    template_id: int | None = Field(None, description="Filter by template ID")
    source_id: int | None = Field(None, description="Filter by source ID")

    # Statuses (multiple selection)
    status: list[str] | None = Field(None, description="Filter by statuses (list)")

    # Flags
    is_mapped: bool | None = Field(None, description="Filter by presence of mapping to template")
    failed: bool | None = Field(None, description="Filter by presence of error")
    exclude_blank: bool = Field(True, description="Exclude blank records (too short/small)")
    include_deleted: bool = Field(False, description="Include deleted recordings (default: False - hides deleted)")

    search: str | None = Field(None, description="Search substring in display_name (case-insensitive)")

    # Dates (for backward compatibility)
    from_date: str | None = Field(None, description="Filter by start date (ISO 8601)")
    to_date: str | None = Field(None, description="Filter by end date (ISO 8601)")

    # Sorting
    order_by: str = Field("created_at", description="Field to sort by (created_at, updated_at, id)")
    order: str = Field("asc", description="Sorting direction (asc, desc)")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "template_id": 5,
                "source_id": 10,
                "status": ["INITIALIZED", "DOWNLOADED"],
                "is_mapped": True,
                "failed": False,
                "from_date": "2025-01-01",
                "to_date": "2025-12-31",
                "exclude_blank": True,
                "include_deleted": False,
                "search": "lecture",
                "order_by": "created_at",
                "order": "desc",
            }
        }
    )
