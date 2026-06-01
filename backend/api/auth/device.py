"""Helpers for tagging refresh tokens with device / client metadata.

We never persist a raw client IP — only ``sha256(ip || jwt_secret_key)`` so
two sessions from the same device can be visually grouped without storing PII.
"""

import hashlib

from fastapi import Request

from config.settings import get_settings

settings = get_settings()

_BROWSER_KEYWORDS = (
    ("Edg/", "Edge"),
    ("OPR/", "Opera"),
    ("Firefox/", "Firefox"),
    ("Chrome/", "Chrome"),
    ("Safari/", "Safari"),
)

_OS_KEYWORDS = (
    # Mobile first: iPhone/iPad UAs also contain "Mac OS X" for legacy reasons,
    # and Android UAs contain "Linux" — match the more specific token.
    ("iPhone", "iOS"),
    ("iPad", "iPadOS"),
    ("Android", "Android"),
    ("Windows NT", "Windows"),
    ("Mac OS X", "macOS"),
    ("Macintosh", "macOS"),
    ("Linux", "Linux"),
)


def parse_device_label(user_agent: str | None) -> str:
    """Render a short human label like ``Chrome · macOS`` from a UA string.

    The keyword order matters: Chromium-based browsers all advertise ``Safari/``,
    so we check for the more specific tokens (Edge, Opera, Chrome) first.
    """
    if not user_agent:
        return "Unknown device"

    browser = next((label for token, label in _BROWSER_KEYWORDS if token in user_agent), None)
    os_name = next((label for token, label in _OS_KEYWORDS if token in user_agent), None)

    if browser and os_name:
        return f"{browser} · {os_name}"
    return browser or os_name or "Unknown device"


def extract_client_ip(request: Request) -> str | None:
    """Return the originating client IP, preferring ``X-Forwarded-For`` set by nginx."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",", 1)[0].strip() or None
    return request.client.host if request.client else None


def hash_ip(ip: str | None) -> str | None:
    """Hash a client IP with the JWT secret as a pepper.

    sha256 alone is brute-forceable for the IPv4 space; pepper makes the hash
    useless to anyone without our signing key.
    """
    if not ip:
        return None
    pepper = settings.security.jwt_secret_key.encode("utf-8")
    return hashlib.sha256(pepper + ip.encode("utf-8")).hexdigest()
