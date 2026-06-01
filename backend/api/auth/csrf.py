"""Double-submit-cookie CSRF check for cookie-authenticated requests."""

from __future__ import annotations

import secrets

from fastapi import HTTPException, Request, status

from api.auth.cookies import ACCESS_COOKIE_NAME, REFRESH_COOKIE_NAME
from config.settings import get_settings

settings = get_settings()

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def enforce_csrf(request: Request) -> None:
    """Raise 403 if a cookie-authenticated mutating request lacks a matching CSRF token.

    Skipped for safe methods, Bearer-authenticated requests (CLI / server-to-
    server), and requests without any session cookie. ``/auth/refresh`` is
    covered because we also gate on the refresh cookie, not just the access one.
    """
    if request.method in SAFE_METHODS:
        return

    if request.headers.get("authorization", "").lower().startswith("bearer "):
        return

    if not (request.cookies.get(ACCESS_COOKIE_NAME) or request.cookies.get(REFRESH_COOKIE_NAME)):
        return

    cookie_token = request.cookies.get(settings.security.csrf_cookie_name)
    header_token = request.headers.get(settings.security.csrf_header_name)

    if not cookie_token or not header_token or not secrets.compare_digest(cookie_token, header_token):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CSRF token missing or invalid",
        )
