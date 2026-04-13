"""Authentication request schemas"""

from pydantic import BaseModel, EmailStr, Field, field_validator


class RegisterRequest(BaseModel):
    """Request for registration."""

    email: EmailStr = Field(..., description="User email")
    password: str = Field(..., min_length=8, max_length=100, description="Password")
    full_name: str | None = Field(None, max_length=255, description="Full name")

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        """Password validation."""
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long")
        if not any(char.isdigit() for char in v):
            raise ValueError("Password must contain at least one digit")
        if not any(char.isupper() for char in v):
            raise ValueError("Password must contain at least one uppercase letter")
        return v


class LoginRequest(BaseModel):
    """Request for login."""

    email: EmailStr = Field(..., description="User email")
    password: str = Field(..., description="Password")


class RefreshTokenRequest(BaseModel):
    """Request for refreshing token."""

    refresh_token: str = Field(..., description="Refresh token")


class ChangePasswordRequest(BaseModel):
    """Request for changing password."""

    old_password: str = Field(..., description="Old password")
    new_password: str = Field(..., min_length=8, max_length=100, description="New password")

    @field_validator("new_password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        """Password validation."""
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long")
        if not any(char.isdigit() for char in v):
            raise ValueError("Password must contain at least one digit")
        if not any(char.isupper() for char in v):
            raise ValueError("Password must contain at least one uppercase letter")
        return v
