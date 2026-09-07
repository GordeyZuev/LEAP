"""Small string helpers used by persistence and matching (no schema/ORM deps)."""

import re


def collapse_whitespace(s: str) -> str:
    """Collapse any whitespace (newlines, tabs, NBSP, runs of spaces) to a single space."""
    return re.sub(r"\s+", " ", s).strip()
