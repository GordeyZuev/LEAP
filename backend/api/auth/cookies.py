"""HttpOnly cookie helpers for the browser session flow."""

from __future__ import annotations

import secrets

from fastapi import Response

from config.settings import get_settings

settings = get_settings()

ACCESS_COOKIE_NAME = "access_token"
REFRESH_COOKIE_NAME = "refresh_token"

ACCESS_COOKIE_PATH = "/"
REFRESH_COOKIE_PATH = "/api/v1/auth"
"""Refresh cookie is scoped to /auth so a CSRF on any other route can't trigger a refresh."""

PERSISTENT_COOKIE_NAME = "leap_persistent"
"""Marks the session as "remember me".

Readable by the client on purpose and carries no secret: it only records the
choice made at login so ``/auth/refresh`` can re-issue cookies with the same
lifetime instead of silently upgrading a browser-session login to a lasting one.
"""


def _cookie_kwargs(*, max_age: int | None, path: str, http_only: bool) -> dict:
    """Build shared kwargs for ``response.set_cookie``.

    ``max_age=None`` produces a session cookie, which the browser drops on exit.
    """
    kwargs: dict = {
        "max_age": max_age,
        "path": path,
        "secure": settings.security.cookie_secure,
        "samesite": settings.security.cookie_samesite,
        "httponly": http_only,
    }
    if settings.security.cookie_domain:
        kwargs["domain"] = settings.security.cookie_domain
    return kwargs


def generate_csrf_token() -> str:
    """Cryptographically strong URL-safe CSRF token (~32 bytes of entropy)."""
    return secrets.token_urlsafe(32)


def set_auth_cookies(
    response: Response,
    *,
    access_token: str,
    refresh_token: str,
    csrf_token: str,
    persistent: bool = True,
) -> None:
    """Write the session cookies on the response.

    CSRF cookie outlives the access cookie so the frontend can still attach it
    to ``/auth/refresh`` once the access token has expired.

    When ``persistent`` is false every cookie becomes a session cookie: the user
    asked not to be remembered, so closing the browser must end the session.
    """
    access_max_age = settings.security.jwt_access_token_expire_minutes * 60 if persistent else None
    refresh_max_age = settings.security.jwt_refresh_token_expire_days * 24 * 60 * 60 if persistent else None

    response.set_cookie(
        ACCESS_COOKIE_NAME,
        access_token,
        **_cookie_kwargs(max_age=access_max_age, path=ACCESS_COOKIE_PATH, http_only=True),
    )
    response.set_cookie(
        REFRESH_COOKIE_NAME,
        refresh_token,
        **_cookie_kwargs(max_age=refresh_max_age, path=REFRESH_COOKIE_PATH, http_only=True),
    )
    response.set_cookie(
        settings.security.csrf_cookie_name,
        csrf_token,
        **_cookie_kwargs(max_age=refresh_max_age, path=ACCESS_COOKIE_PATH, http_only=False),
    )
    response.set_cookie(
        PERSISTENT_COOKIE_NAME,
        "1" if persistent else "0",
        **_cookie_kwargs(max_age=refresh_max_age, path=ACCESS_COOKIE_PATH, http_only=False),
    )


def clear_auth_cookies(response: Response) -> None:
    """Expire every session cookie (logout)."""
    domain = settings.security.cookie_domain
    response.delete_cookie(ACCESS_COOKIE_NAME, path=ACCESS_COOKIE_PATH, domain=domain)
    response.delete_cookie(REFRESH_COOKIE_NAME, path=REFRESH_COOKIE_PATH, domain=domain)
    response.delete_cookie(settings.security.csrf_cookie_name, path=ACCESS_COOKIE_PATH, domain=domain)
    response.delete_cookie(PERSISTENT_COOKIE_NAME, path=ACCESS_COOKIE_PATH, domain=domain)
