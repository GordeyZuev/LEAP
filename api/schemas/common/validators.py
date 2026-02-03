"""Common Pydantic schema validators

Contains only specific validators that cannot be implemented through Field constraints.
For basic checks, use built-in Pydantic capabilities:
- Field(min_length=X, max_length=Y) for string length
- Field(gt=0, le=100) for number ranges
- Field(pattern=r"regex") for regex validation of string format
- @field_validator with mode="before" for transformations (strip, lower, etc)
"""

import re


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

    - Strips leading/trailing whitespace
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

    # Clean and filter
    cleaned = [s.strip() for s in v if isinstance(s, str) and s.strip()]

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
