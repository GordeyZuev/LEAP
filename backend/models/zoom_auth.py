"""Zoom authentication credentials models"""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field


class ZoomServerToServerCredentials(BaseModel):
    """Server-to-Server OAuth credentials for Zoom API"""

    model_config = ConfigDict(frozen=True)

    auth_type: Literal["server_to_server"] = "server_to_server"
    account: str = Field(..., description="Account email")
    account_id: str = Field(..., min_length=1, description="Zoom account ID")
    client_id: str = Field(..., min_length=1, description="OAuth client ID")
    client_secret: str = Field(..., min_length=1, description="OAuth client secret")


class ZoomOAuthCredentials(BaseModel):
    """User OAuth 2.0 credentials for Zoom API"""

    model_config = ConfigDict(frozen=True)

    auth_type: Literal["oauth"] = "oauth"
    client_id: str = Field(..., min_length=1, description="OAuth client ID")
    client_secret: str = Field(..., min_length=1, description="OAuth client secret")
    access_token: str = Field(..., min_length=1, description="OAuth access token")
    refresh_token: str = Field(..., min_length=1, description="OAuth refresh token")
    token_type: str = Field(default="bearer", description="Token type")
    scope: str | None = Field(default=None, description="OAuth scopes")
    expires_in: int | None = Field(default=None, description="Token expiration time in seconds")
    expiry: datetime | None = Field(default=None, description="Token expiration datetime")

    @computed_field
    @property
    def is_expired(self) -> bool:
        """Check if access token is expired"""
        return bool(self.expiry and datetime.now(self.expiry.tzinfo) >= self.expiry)


# Union type with discriminator for automatic type detection
ZoomCredentials = Annotated[
    ZoomServerToServerCredentials | ZoomOAuthCredentials,
    Field(discriminator="auth_type"),
]


def create_zoom_credentials(creds_dict: dict) -> ZoomServerToServerCredentials | ZoomOAuthCredentials:
    """
    Create Zoom credentials object from dictionary.

    Auto-detects type based on access_token or account_id presence.

    Args:
        creds_dict: Credentials dictionary from database

    Returns:
        ZoomServerToServerCredentials or ZoomOAuthCredentials

    Raises:
        ValueError: If credentials are invalid
    """
    if "access_token" in creds_dict:
        return ZoomOAuthCredentials(
            auth_type="oauth",
            client_id=creds_dict["client_id"],
            client_secret=creds_dict["client_secret"],
            access_token=creds_dict["access_token"],
            refresh_token=creds_dict["refresh_token"],
            token_type=creds_dict.get("token_type", "bearer"),
            scope=creds_dict.get("scope"),
            expires_in=creds_dict.get("expires_in"),
            expiry=creds_dict.get("expiry"),
        )
    if "account_id" in creds_dict:
        return ZoomServerToServerCredentials(
            auth_type="server_to_server",
            account=creds_dict.get("account", ""),
            account_id=creds_dict["account_id"],
            client_id=creds_dict["client_id"],
            client_secret=creds_dict["client_secret"],
        )
    raise ValueError("Invalid Zoom credentials: missing access_token or account_id")
