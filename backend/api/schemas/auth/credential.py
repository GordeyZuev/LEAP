"""Pydantic schemas for user credentials."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class UserCredentialBase(BaseModel):
    """Base schema for user credentials."""

    platform: str = Field(..., max_length=50, description="Platform (zoom, youtube, gdrive)")
    account_name: str | None = Field(None, max_length=255, description="Account name (for multiple accounts)")


class UserCredentialCreate(UserCredentialBase):
    """Schema for creating user credentials."""

    user_id: str
    encrypted_data: str = Field(..., description="Encrypted data")


class UserCredentialUpdate(BaseModel):
    """Schema for updating user credentials."""

    encrypted_data: str | None = None
    is_active: bool | None = None


class UserCredentialInDB(UserCredentialBase):
    """Schema of user credentials in DB."""

    id: int
    user_id: str
    encrypted_data: str
    is_active: bool = True
    created_at: datetime
    updated_at: datetime
    last_used_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class UserCredentialResponse(BaseModel):
    """Schema of response with user credentials (without encrypted data)."""

    id: int
    platform: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
    last_used_at: datetime | None

    model_config = ConfigDict(from_attributes=True)
