"""Date utilities"""

from datetime import UTC, datetime


class InvalidDateFormatError(ValueError):
    """Exception raised when date format is invalid"""


class InvalidPeriodError(ValueError):
    """Exception raised when period format is invalid"""


def parse_date(date_str: str) -> str:
    """
    Parse date in various formats and normalize to YYYY-MM-DD.

    Supported formats: YYYY-MM-DD, DD-MM-YYYY, DD/MM/YYYY, DD-MM-YY, DD/MM/YY

    Raises:
        InvalidDateFormatError: If date string doesn't match any supported format
    """
    if not date_str:
        return date_str

    date_str = date_str.strip()

    formats = [
        "%Y-%m-%d",
        "%d-%m-%Y",
        "%d/%m/%Y",
        "%d-%m-%y",
        "%d/%m/%y",
    ]

    for fmt in formats:
        try:
            parsed_date = datetime.strptime(date_str, fmt)
            return parsed_date.strftime("%Y-%m-%d")
        except ValueError:
            continue

    raise InvalidDateFormatError(
        f"Invalid date format: '{date_str}'. "
        f"Supported formats: YYYY-MM-DD, DD-MM-YYYY, DD/MM/YYYY, DD-MM-YY, DD/MM/YY"
    )


def parse_from_date_to_datetime(date_str: str) -> datetime:
    """
    Parse date string to datetime at start of day (00:00:00) with UTC timezone.

    Used for 'from_date' filters (>=).

    Args:
        date_str: Date string in any supported format (YYYY-MM-DD, DD-MM-YYYY, etc.)

    Returns:
        datetime object at 00:00:00 UTC

    Example:
        >>> parse_from_date_to_datetime("2024-12-01")
        datetime(2024, 12, 1, 0, 0, 0, tzinfo=UTC)
    """
    parsed = parse_date(date_str)
    return datetime.strptime(parsed, "%Y-%m-%d").replace(tzinfo=UTC)


def parse_to_date_to_datetime(date_str: str) -> datetime:
    """
    Parse date string to datetime at end of day (23:59:59) with UTC timezone.
    """
    parsed = parse_date(date_str)
    dt = datetime.strptime(parsed, "%Y-%m-%d").replace(tzinfo=UTC)
    return dt.replace(hour=23, minute=59, second=59)


def validate_period(period: int) -> int:
    """
    Validate period in YYYYMM format.
    """
    if period < 190001 or period > 299912:
        raise InvalidPeriodError(f"Invalid period: {period}. Expected format YYYYMM (e.g., 202601)")

    month = period % 100

    if month < 1 or month > 12:
        raise InvalidPeriodError(f"Invalid month: {month} in period {period}. Month must be 01-12")

    return period
