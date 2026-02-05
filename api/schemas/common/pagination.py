"""Pagination schemas."""

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
