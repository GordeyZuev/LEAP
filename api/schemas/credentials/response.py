"""Response schemas for credentials endpoints."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from api.schemas.common.pagination import PaginatedResponse


class CredentialListItem(BaseModel):
    """Lightweight credential for list views (excludes secret data)."""

    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., description="ID of credentials")
    platform: str = Field(..., description="Platform")
    account_name: str | None = Field(None, description="Account name")
    is_active: bool = Field(..., description="Are credentials active")
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
    last_used_at: datetime | None = Field(None, description="Time of last usage")
    credentials: dict | None = Field(None, description="Credentials (only when include_data flag is set)")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")


class CredentialListResponse(PaginatedResponse):
    """Paginated list of credentials."""

    items: list[CredentialListItem]


class CredentialStatusResponse(BaseModel):
    """Status of credentials of user."""

    user_id: str
    available_platforms: list[str]
    credentials_status: dict[str, bool]
