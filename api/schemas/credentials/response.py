"""Response schemas for credentials endpoints."""

from pydantic import BaseModel, Field


class CredentialResponse(BaseModel):
    """Response with information about credentials."""

    id: int = Field(..., description="ID of credentials")
    platform: str = Field(..., description="Platform")
    account_name: str | None = Field(None, description="Account name")
    is_active: bool = Field(..., description="Are credentials active")
    last_used_at: str | None = Field(None, description="Time of last usage")
    credentials: dict | None = Field(None, description="Credentials (only when include_data flag is set)")


class CredentialStatusResponse(BaseModel):
    """Status of credentials of user."""

    user_id: str
    available_platforms: list[str]
    credentials_status: dict[str, bool]


class CredentialDeleteResponse(BaseModel):
    """Confirmation of deletion."""

    message: str
