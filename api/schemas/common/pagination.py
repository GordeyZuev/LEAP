"""Pagination schemas and helpers."""

from typing import Literal

from pydantic import BaseModel, Field


class PaginationParams(BaseModel):
    """Parameters of pagination."""

    page: int = Field(1, ge=1, description="Page number")
    per_page: int = Field(20, ge=1, le=100, description="Number of records per page")


class PaginatedResponse(BaseModel):
    """Response with pagination."""

    page: int
    per_page: int
    total: int
    total_pages: int

    @property
    def has_next(self) -> bool:
        """Is there a next page."""
        return self.page < self.total_pages

    @property
    def has_prev(self) -> bool:
        """Is there a previous page."""
        return self.page > 1


def _sort_key(item: object, field: str):
    """Extract a sort key that handles None values safely.

    For nullable fields (e.g. last_sync_at, next_run_at), we need
    to ensure None values sort consistently without causing TypeError
    from mixed-type comparisons (datetime vs str).
    """
    value = getattr(item, field, None)
    if value is None:
        # (0, ...) sorts before (1, value), pushing None to the start
        return (0, "")
    return (1, value)


def paginate_list(
    items: list,
    page: int,
    per_page: int,
    sort_by: str = "created_at",
    sort_order: Literal["asc", "desc"] = "desc",
    allowed_sort_fields: set[str] | None = None,
) -> tuple[list, int, int]:
    """Sort and paginate a list in-memory.

    Returns:
        (paginated_items, total, total_pages)
    """
    # Validate and apply sorting
    if allowed_sort_fields and sort_by not in allowed_sort_fields:
        sort_by = "created_at"

    items.sort(
        key=lambda item: _sort_key(item, sort_by),
        reverse=(sort_order == "desc"),
    )

    total = len(items)
    total_pages = max(1, (total + per_page - 1) // per_page)
    start = (page - 1) * per_page
    end = start + per_page

    return items[start:end], total, total_pages
