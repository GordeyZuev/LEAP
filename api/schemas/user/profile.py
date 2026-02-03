"""User profile management schemas"""

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class UserProfileUpdate(BaseModel):
    """Schema for updating user profile.

    User can only update their name and email.
    Other fields (permissions, role) can only be changed by admins.
    """

    full_name: str | None = Field(None, max_length=255, description="Full name of user")
    email: EmailStr | None = Field(None, description="Email of user")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "full_name": "John Doe",
                "email": "ivan.petrov@example.com",
            }
        }
    )


class ChangePasswordRequest(BaseModel):
    """Schema for changing password."""

    current_password: str = Field(..., min_length=1, description="Current password")
    new_password: str = Field(..., min_length=8, max_length=100, description="New password")

    @field_validator("new_password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        """Validation of new password."""
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        if not any(char.isdigit() for char in v):
            raise ValueError("Password must contain at least one digit")
        if not any(char.isupper() for char in v):
            raise ValueError("Password must contain at least one uppercase letter")
        return v

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "current_password": "OldPassword123",
                "new_password": "NewSecurePassword123",
            }
        }
    )


class DeleteAccountRequest(BaseModel):
    """Schema for confirmation of account deletion."""

    password: str = Field(..., description="Password for confirmation")
    confirmation: str = Field(
        ...,
        description="User must enter 'DELETE' for confirmation",
    )

    @field_validator("confirmation")
    @classmethod
    def validate_confirmation(cls, v: str) -> str:
        """Check that user really wants to delete account."""
        if v != "DELETE":
            raise ValueError("For confirmation of deletion enter 'DELETE'")
        return v

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "password": "MyPassword123",
                "confirmation": "DELETE",
            }
        }
    )
