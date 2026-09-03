"""MTS Link authentication credentials models."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class MtsLinkApiKeyCredentials(BaseModel):
    """Organization UserAPI key (x-auth-token)."""

    model_config = ConfigDict(frozen=True)

    auth_type: Literal["api_key"] = "api_key"
    api_token: str = Field(..., min_length=8, description="UserAPI key from LK Business → API/Webhooks")
    account: str | None = Field(default=None, description="Optional label for this org key")
    base_url: str = Field(
        default="https://userapi.mts-link.ru/v3",
        description="UserAPI base URL (override for on-prem)",
    )


MtsLinkCredentials = Annotated[MtsLinkApiKeyCredentials, Field()]


def create_mts_link_credentials(creds_dict: dict) -> MtsLinkApiKeyCredentials:
    """Build credentials from decrypted user_credentials blob."""
    auth_type = creds_dict.get("auth_type", "api_key")
    if auth_type != "api_key":
        raise ValueError(f"Unsupported MTS Link auth_type: {auth_type}")

    token = creds_dict.get("api_token") or creds_dict.get("x_auth_token")
    if not token or not str(token).strip():
        raise ValueError("MTS Link credentials require api_token")

    return MtsLinkApiKeyCredentials(
        auth_type="api_key",
        api_token=str(token).strip(),
        account=creds_dict.get("account"),
        base_url=creds_dict.get("base_url") or "https://userapi.mts-link.ru/v3",
    )


def create_mts_link_client(creds: MtsLinkApiKeyCredentials):
    """Factory for :class:`api.mts_link_api.MtsLinkAPI`."""
    from api.mts_link_api import MtsLinkAPI

    return MtsLinkAPI(api_token=creds.api_token, base_url=creds.base_url)
