"""Schemas for auth operations."""

from pydantic import BaseModel


class LogoutResponse(BaseModel):
    """Result of logout."""

    message: str


class LogoutAllResponse(BaseModel):
    """Result of logout from all devices."""

    message: str
    revoked_tokens: int
