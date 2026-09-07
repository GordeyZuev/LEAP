"""Double-submit-cookie CSRF check for cookie-authenticated requests."""

from __future__ import annotations

import re
import secrets

from fastapi import HTTPException, Request, status

from api.auth.cookies import ACCESS_COOKIE_NAME, REFRESH_COOKIE_NAME
from config.settings import get_settings

settings = get_settings()

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}

# Public view beacons: ``navigator.sendBeacon`` cannot attach X-CSRF-Token, but
# the browser still sends session cookies on same-origin. A 403 here drops
# share analytics for logged-in viewers. The routes only increment counters.
_UUID = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
_PUBLIC_SHARE_BEACON = re.compile(
    rf"^/api/v1/share/(?:p/{_UUID}/items/\d+|{_UUID})/beacon/?$",
)


def enforce_csrf(request: Request) -> None:
    """Raise 403 if a cookie-authenticated mutating request lacks a matching CSRF token.

    Skipped for safe methods, Bearer-authenticated requests (CLI / server-to-
    server), public share view beacons, and requests without any session cookie.
    ``/auth/refresh`` is covered because we also gate on the refresh cookie,
    not just the access one.
    """
    if request.method in SAFE_METHODS:
        return

    if request.method == "POST" and _PUBLIC_SHARE_BEACON.match(request.url.path):
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
