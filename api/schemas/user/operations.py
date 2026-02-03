"""Schemas for user operations."""

from pydantic import BaseModel


class PasswordChangeResponse(BaseModel):
    """Result of change of password."""

    message: str
    detail: str


class AccountDeleteResponse(BaseModel):
    """Result of deletion of account."""

    message: str
    detail: str
