"""Pydantic schemas for tokens."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class RefreshTokenBase(BaseModel):
    """Base schema for refresh token."""

    token: str


class RefreshTokenCreate(RefreshTokenBase):
    """Schema for creating refresh token."""

    user_id: str
    expires_at: datetime


class RefreshTokenInDB(RefreshTokenBase):
    """Schema of refresh token in DB."""

    id: int
    user_id: str
    expires_at: datetime
    is_revoked: bool = False
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TokenPair(BaseModel):
    """Pair of tokens (access + refresh)."""

    access_token: str = Field(..., description="Access token")
    refresh_token: str = Field(..., description="Refresh token")
    token_type: str = Field(default="bearer", description="Token type")
    expires_in: int = Field(..., description="Lifetime of access token in seconds")
