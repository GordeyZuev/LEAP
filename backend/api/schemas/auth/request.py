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
    """Request for refreshing token.

    Browser flow leaves this empty (token comes from the refresh cookie).
    CLI clients pass the token in the body.
    """

    refresh_token: str | None = Field(default=None, description="Refresh token (browser clients omit — uses cookie).")


class ForgotPasswordRequest(BaseModel):
    """Request to initiate password reset (sends email)."""

    email: EmailStr = Field(..., description="Registered email address")


class ResetPasswordRequest(BaseModel):
    """Request to set a new password using a reset token."""

    token: str = Field(..., min_length=1, max_length=128, description="Reset token from email")
    new_password: str = Field(..., min_length=8, max_length=100, description="New password")

    @field_validator("new_password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        """Password validation (same rules as registration)."""
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long")
        if not any(char.isdigit() for char in v):
            raise ValueError("Password must contain at least one digit")
        if not any(char.isupper() for char in v):
            raise ValueError("Password must contain at least one uppercase letter")
        return v


class VerifyEmailRequest(BaseModel):
    """Request to verify email using a verification token."""

    token: str = Field(..., min_length=1, max_length=128, description="Verification token from email")


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
