"""Request schemas for credentials endpoints."""

from pydantic import BaseModel, Field


class CredentialCreateRequest(BaseModel):
    """Request to create credentials."""

    platform: str = Field(..., description="Platform (zoom, youtube, vk)")
    account_name: str | None = Field(None, description="Account name (for multiple accounts)")
    credentials: dict = Field(..., description="Credentials of platform")


class CredentialUpdateRequest(BaseModel):
    """Request to update credentials."""

    credentials: dict = Field(..., description="Updated credentials")
