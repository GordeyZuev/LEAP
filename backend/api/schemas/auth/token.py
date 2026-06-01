"""Pydantic schemas for tokens."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class RefreshTokenBase(BaseModel):
    """Base schema for refresh token."""

    token: str


class RefreshTokenCreate(RefreshTokenBase):
    """Schema for creating refresh token."""

    user_id: str
    expires_at: datetime
    user_agent: str | None = None
    ip_hash: str | None = None
    device_label: str | None = None


class RefreshTokenInDB(RefreshTokenBase):
    """Schema of refresh token in DB."""

    id: int
    user_id: str
    expires_at: datetime
    is_revoked: bool = False
    created_at: datetime
    last_used_at: datetime | None = None
    user_agent: str | None = None
    ip_hash: str | None = None
    device_label: str | None = None

    model_config = ConfigDict(from_attributes=True)


class SessionInfo(BaseModel):
    """One active refresh-token session for the ``/auth/sessions`` UI."""

    id: int
    device_label: str | None = None
    user_agent: str | None = None
    last_used_at: datetime | None = None
    created_at: datetime
    is_current: bool = Field(
        default=False,
        description="True for the session matching the refresh cookie on the current request.",
    )

    model_config = ConfigDict(from_attributes=True)


class SessionListResponse(BaseModel):
    """Response envelope for ``GET /auth/sessions``."""

    sessions: list[SessionInfo]


class TokenPair(BaseModel):
    """Pair of tokens (access + refresh).

    Kept for CLI / server-to-server clients that authenticate via the
    ``Authorization: Bearer`` header. Browser clients should rely on the
    cookies set on the same response and use :class:`SessionResponse`.
    """

    access_token: str = Field(..., description="Access token")
    refresh_token: str = Field(..., description="Refresh token")
    token_type: str = Field(default="bearer", description="Token type")
    expires_in: int = Field(..., description="Lifetime of access token in seconds")


class SessionResponse(BaseModel):
    """Response for cookie-based session bootstrap (login / refresh).

    The session itself lives in httpOnly cookies set on the same response;
    this body delivers the CSRF token (which the browser-side JS must echo
    on every state-changing request) plus a TokenPair for CLI clients.
    """

    csrf_token: str = Field(
        ..., description="Double-submit CSRF token. Echo via X-CSRF-Token header on POST/PUT/PATCH/DELETE."
    )
    access_token: str = Field(..., description="Bearer access token (CLI clients).")
    refresh_token: str = Field(..., description="Bearer refresh token (CLI clients).")
    token_type: str = Field(default="bearer", description="Token type")
    expires_in: int = Field(..., description="Lifetime of access token in seconds")
