"""Pydantic schemas for users."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class UserBase(BaseModel):
    """Base schema for user."""

    email: EmailStr = Field(..., description="User email")
    full_name: str | None = Field(None, max_length=255, description="Full name")


class UserCreate(UserBase):
    """Schema for creating user."""

    password: str = Field(..., min_length=8, max_length=100, description="Password")

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


class UserUpdate(BaseModel):
    """Schema for updating user."""

    # --- Core info ---
    email: EmailStr | None = None
    full_name: str | None = None
    timezone: str | None = None
    is_active: bool | None = None
    is_verified: bool | None = None
    role: str | None = None

    # --- Permissions ---
    can_transcribe: bool | None = None
    can_process_video: bool | None = None
    can_upload: bool | None = None
    can_create_templates: bool | None = None
    can_delete_recordings: bool | None = None
    can_update_uploaded_videos: bool | None = None
    can_manage_credentials: bool | None = None
    can_export_data: bool | None = None

    # --- Timestamps ---
    last_login_at: datetime | None = None


class UserInDB(UserBase):
    """Schema of user in DB."""

    # --- Identity ---
    id: str
    user_slug: int
    hashed_password: str

    # --- Core info ---
    timezone: str = "UTC"
    is_active: bool = True
    is_verified: bool = False
    role: str = "user"

    # --- Permissions ---
    can_transcribe: bool = True
    can_process_video: bool = True
    can_upload: bool = True
    can_create_templates: bool = True
    can_delete_recordings: bool = True
    can_update_uploaded_videos: bool = True
    can_manage_credentials: bool = True
    can_export_data: bool = True

    # --- Timestamps ---
    created_at: datetime
    updated_at: datetime
    last_login_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class UserResponse(BaseModel):
    """Schema of response with user."""

    # --- Identity ---
    id: str
    email: EmailStr
    full_name: str | None

    # --- Core info ---
    timezone: str
    is_active: bool
    is_verified: bool
    role: str

    # --- Permissions ---
    can_transcribe: bool
    can_process_video: bool
    can_upload: bool
    can_create_templates: bool
    can_delete_recordings: bool
    can_update_uploaded_videos: bool
    can_manage_credentials: bool
    can_export_data: bool

    # --- Timestamps ---
    created_at: datetime
    updated_at: datetime
    last_login_at: datetime | None

    model_config = ConfigDict(from_attributes=True)
