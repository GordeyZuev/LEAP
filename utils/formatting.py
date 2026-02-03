def normalize_datetime_string(date_string: str) -> str:
    """Normalize datetime string by removing timezone suffixes for consistent parsing."""
    if not date_string:
        return date_string

    time_str = date_string
    if time_str.endswith("Z"):
        time_str = time_str[:-1]
    if time_str.endswith("+00:00"):
        time_str = time_str[:-6]

    return time_str
