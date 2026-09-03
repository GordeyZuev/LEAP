"""Response schemas for credentials endpoints."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from api.schemas.common.pagination import PaginatedResponse


class CredentialListItem(BaseModel):
    """Lightweight credential for list views (excludes secret data)."""

    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., description="ID of credentials")
    platform: str = Field(..., description="Platform")
    account_name: str | None = Field(None, description="Account name")
    is_active: bool = Field(..., description="Are credentials active")
    needs_reauth: bool = Field(False, description="Whether re-authentication is needed")
    last_used_at: datetime | None = Field(None, description="Time of last usage")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")


class CredentialResponse(BaseModel):
    """Full credential detail (may include decrypted credentials)."""

    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., description="ID of credentials")
    platform: str = Field(..., description="Platform")
    account_name: str | None = Field(None, description="Account name")
    is_active: bool = Field(..., description="Are credentials active")
    needs_reauth: bool = Field(False, description="Whether re-authentication is needed")
    last_used_at: datetime | None = Field(None, description="Time of last usage")
    credentials: dict | None = Field(None, description="Credentials (only when include_data flag is set)")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")


class CredentialListResponse(PaginatedResponse):
    """Paginated list of credentials."""

    items: list[CredentialListItem]


class CredentialCheckResponse(BaseModel):
    """Result of an on-demand connection check against the platform."""

    status: Literal["ok", "auth_failed", "unavailable", "unsupported"] = Field(
        ...,
        description=(
            "ok — platform accepted the credentials; auth_failed — rejected, re-auth required; "
            "unavailable — could not be checked (network or provider error); "
            "unsupported — no check implemented for this platform"
        ),
    )
    detail: str = Field(..., description="Human-readable outcome")
    needs_reauth: bool = Field(..., description="Flag value stored on the credential after the check")
    checked_at: datetime = Field(..., description="When the check ran")


class CredentialStatusResponse(BaseModel):
    """Status of credentials of user."""

    user_id: str
    available_platforms: list[str]
    credentials_status: dict[str, bool]
