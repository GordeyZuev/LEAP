"""Pagination schemas and helpers."""

from collections.abc import Callable
from typing import Any, Literal

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
    """Plain attribute key; None is partitioned out by paginate_list."""
    return getattr(item, field, None)


def filter_by_search(items: list, query: str | None, fields: tuple[str, ...]) -> list:
    """Case-insensitive substring filter over the given attributes.

    Used by list endpoints that already paginate in memory (`paginate_list`), so
    the search runs over the full result set rather than a single page.
    Attributes that are missing or None are skipped.
    """
    if not query:
        return items
    needle = query.strip().lower()
    if not needle:
        return items
    return [item for item in items if any(needle in str(getattr(item, field, None) or "").lower() for field in fields)]


def paginate_list(
    items: list,
    page: int,
    per_page: int,
    sort_by: str = "created_at",
    sort_order: Literal["asc", "desc"] = "desc",
    allowed_sort_fields: set[str] | None = None,
    sort_keys: dict[str, Callable[[Any], Any]] | None = None,
) -> tuple[list, int, int]:
    """Sort and paginate a list in-memory.

    ``sort_keys`` supplies key functions for sort fields that are not plain attributes
    (e.g. a credential's status, which is derived from two columns).

    Returns:
        (paginated_items, total, total_pages)
    """
    # Validate and apply sorting
    if allowed_sort_fields and sort_by not in allowed_sort_fields:
        sort_by = "created_at"

    derived_key = (sort_keys or {}).get(sort_by)

    def raw(item: Any) -> Any:
        return derived_key(item) if derived_key else _sort_key(item, sort_by)

    filled = [item for item in items if raw(item) is not None]
    empty = [item for item in items if raw(item) is None]
    filled.sort(key=raw, reverse=(sort_order == "desc"))
    items[:] = filled + empty

    total = len(items)
    total_pages = max(1, (total + per_page - 1) // per_page)
    start = (page - 1) * per_page
    end = start + per_page

    return items[start:end], total, total_pages
