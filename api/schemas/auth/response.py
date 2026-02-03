"""Authentication response schemas."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class TokenResponse(BaseModel):
    """Response with tokens."""

    access_token: str = Field(..., description="Access token")
    refresh_token: str = Field(..., description="Refresh token")
    token_type: str = Field(default="bearer", description="Token type")
    expires_in: int = Field(..., description="Lifetime of access token in seconds")


class UserResponse(BaseModel):
    """Response with information about user."""

    id: str = Field(..., description="User ID")
    email: EmailStr = Field(..., description="Email")
    full_name: str | None = Field(None, description="Full name")
    is_active: bool = Field(..., description="Is account active")
    is_verified: bool = Field(..., description="Is email verified")
    is_superuser: bool = Field(..., description="Is superuser")
    created_at: datetime = Field(..., description="Creation date")
    last_login_at: datetime | None = Field(None, description="Last login")

    model_config = ConfigDict(from_attributes=True)


class UserMeResponse(BaseModel):
    """Response with basic information about current user."""

    id: str = Field(..., description="User ID")
    email: EmailStr = Field(..., description="Email")
    full_name: str | None = Field(None, description="Full name")
    timezone: str = Field(..., description="Timezone")
    role: str = Field(..., description="User role")
    is_active: bool = Field(..., description="Is account active")
    is_verified: bool = Field(..., description="Is email verified")
    created_at: datetime = Field(..., description="Creation date")
    last_login_at: datetime | None = Field(None, description="Last login")

    model_config = ConfigDict(from_attributes=True)
