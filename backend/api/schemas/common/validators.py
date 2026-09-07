"""Common Pydantic schema validators

Contains only specific validators that cannot be implemented through Field constraints.
For basic checks, use built-in Pydantic capabilities:
- Field(min_length=X, max_length=Y) for string length
- Field(gt=0, le=100) for number ranges
- Field(pattern=r"regex") for regex validation of string format
- @field_validator with mode="before" for transformations (strip, lower, etc)
"""

import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from api.helpers.text import collapse_whitespace


def validate_regex_pattern(v: str | None, field_name: str = "pattern") -> str | None:
    """
    Validation of regex pattern.

    Args:
        v: Regex pattern for validation
        field_name: Field name (for error message)

    Returns:
        Validated pattern or None

    Raises:
        ValueError: If regex pattern is invalid
    """
    if v is not None:
        try:
            re.compile(v)
        except re.error as e:
            raise ValueError(f"Invalid regex pattern '{field_name}': {e}")
    return v


def validate_regex_patterns(v: list[str] | None, field_name: str = "patterns") -> list[str] | None:
    """
    Validation of list of regex patterns.

    Args:
        v: List of regex patterns
        field_name: Field name (for error message)

    Returns:
        Validated list or None

    Raises:
        ValueError: If any regex pattern is invalid
    """
    if v is not None:
        for pattern in v:
            try:
                re.compile(pattern)
            except re.error as e:
                raise ValueError(f"Invalid regex pattern in '{field_name}': {e}")
    return v


def collapse_optional_display_name(v: str | None, *, allow_empty: bool = False) -> str | None:
    """Collapse whitespace in an optional recording title. None stays None."""
    if v is None:
        return None
    collapsed = collapse_whitespace(v)
    if collapsed:
        return collapsed
    if allow_empty:
        return None
    raise ValueError("Name cannot be empty")


def strip_and_validate_name(v: str) -> str:
    """Strip whitespace from name and validate it's not empty."""
    if isinstance(v, str):
        v = v.strip()
        if not v:
            raise ValueError("Name cannot be empty")
    return v


def clean_and_deduplicate_strings(v: list[str] | None) -> list[str] | None:
    """
    Clean and deduplicate list of strings.

    - Collapses internal whitespace (newlines, tabs) and strips ends
    - Removes empty strings
    - Removes duplicates (preserving order)
    - Returns None if list is empty after cleaning

    Usage example:
    ```python
    keywords: list[str] | None = Field(None)

    @field_validator("keywords", mode="before")
    @classmethod
    def clean_keywords(cls, v: list[str] | None) -> list[str] | None:
        return clean_and_deduplicate_strings(v)
    ```

    Args:
        v: List of strings

    Returns:
        Cleaned list without duplicates or None
    """
    if v is None:
        return None

    cleaned: list[str] = []
    for s in v:
        if not isinstance(s, str):
            continue
        collapsed = collapse_whitespace(s)
        if collapsed:
            cleaned.append(collapsed)

    if not cleaned:
        return None

    # Deduplicate preserving order
    seen = set()
    deduplicated = []
    for item in cleaned:
        if item not in seen:
            seen.add(item)
            deduplicated.append(item)

    return deduplicated


def validate_iana_timezone(v: str | None) -> str | None:
    """
    Validate an IANA timezone name (for ``users.timezone``).

    Args:
        v: Timezone string or None if the field was omitted.

    Returns:
        Stripped IANA id, or None.

    Raises:
        ValueError: If empty after strip or not a known IANA zone.
    """
    if v is None:
        return None
    if not isinstance(v, str):
        raise ValueError("Timezone must be a string")
    v = v.strip()
    if not v:
        raise ValueError("Timezone cannot be empty")
    try:
        ZoneInfo(v)
    except (ZoneInfoNotFoundError, ValueError, OSError, TypeError) as e:
        raise ValueError(f"Unknown IANA timezone: {v!r}") from e
    return v
