"""Global unique channel slug validation."""

from __future__ import annotations

import re
import unicodedata

from fastapi import HTTPException, status

SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:[-_][a-z0-9]+)*$")
SLUG_MIN = 5
SLUG_MAX = 64
RESERVED_SLUGS = frozenset(
    {
        "share",
        "api",
        "admin",
        "c",
        "p",
        "login",
        "docs",
        "static",
        "playlists",
        "channels",
        "recordings",
        "templates",
        "presets",
        "sources",
        "credentials",
        "automation",
        "settings",
        "auth",
        "health",
        "new",
    }
)


def suggest_slug(name: str) -> str:
    """ASCII slug from a display name (may be shorter than SLUG_MIN)."""
    normalized = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    cleaned = re.sub(r"[^a-z0-9_]+", "-", normalized.lower()).strip("-_")
    return cleaned[:SLUG_MAX]


def validate_channel_slug(raw: str) -> str:
    slug = (raw or "").strip().lower()
    if len(slug) < SLUG_MIN or len(slug) > SLUG_MAX:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Slug must be {SLUG_MIN}–{SLUG_MAX} characters.",
        )
    if not SLUG_PATTERN.fullmatch(slug) or slug in RESERVED_SLUGS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Slug must be lowercase letters, digits, hyphens or underscores, and cannot be reserved.",
        )
    return slug
