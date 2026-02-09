"""OAuth response schemas."""

from pydantic import BaseModel, Field

from api.schemas.common import BASE_MODEL_CONFIG


class OAuthAuthorizeResponse(BaseModel):
    """Response for OAuth authorization URL generation."""

    model_config = BASE_MODEL_CONFIG

    authorization_url: str = Field(..., description="URL to redirect user to for authorization")
    state: str = Field(..., description="CSRF state token")
    expires_in: int = Field(..., description="State token TTL in seconds")
    platform: str = Field(..., description="OAuth platform identifier")


class OAuthImplicitFlowResponse(BaseModel):
    """Response for OAuth Implicit Flow authorization."""

    method: str = Field(..., description="OAuth method type (e.g., 'implicit_flow')")
    app_id: str = Field(..., description="OAuth application ID")
    redirect_uri: str | None = Field(
        None,
        description="Full authorization URL to redirect user to (includes all query params)",
    )
    scope: str | None = Field(
        None,
        description="Requested permissions (e.g., 'video,groups,wall')",
    )
    response_type: str | None = Field(
        None,
        description="OAuth response type (e.g., 'token' for implicit flow)",
    )
    blank_redirect_uri: str | None = Field(
        None,
        description="Final redirect URI where token will appear in URL hash fragment (e.g., 'https://oauth.vk.com/blank.html')",
    )
