"""Date utilities"""

from datetime import UTC, datetime


class InvalidDateFormatError(ValueError):
    """Exception raised when date format is invalid"""


class InvalidPeriodError(ValueError):
    """Exception raised when period format is invalid"""


def parse_date(date_str: str) -> str:
    """
    Parse date in different formats and return in format YYYY-MM-DD.

    Поддерживаемые форматы:
    - YYYY-MM-DD (стандартный)
    - DD-MM-YYYY (европейский)
    - DD/MM/YYYY (с слэшами)
    - DD-MM-YY (короткий год)
    - DD/MM/YY (короткий год)

    Raises:
        InvalidDateFormatError: If date string doesn't match any supported format
    """
    if not date_str:
        return date_str

    date_str = date_str.strip()

    formats = [
        "%Y-%m-%d",  # YYYY-MM-DD
        "%d-%m-%Y",  # DD-MM-YYYY
        "%d/%m/%Y",  # DD/MM/YYYY
        "%d-%m-%y",  # DD-MM-YY
        "%d/%m/%y",  # DD/MM/YY
    ]

    for fmt in formats:
        try:
            parsed_date = datetime.strptime(date_str, fmt)
            return parsed_date.strftime("%Y-%m-%d")
        except ValueError:
            continue

    # Если ни один формат не подошел, выбрасываем исключение
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

    Used for 'to_date' filters (<=).

    Args:
        date_str: Date string in any supported format (YYYY-MM-DD, DD-MM-YYYY, etc.)

    Returns:
        datetime object at 23:59:59 UTC

    Example:
        >>> parse_to_date_to_datetime("2024-12-31")
        datetime(2024, 12, 31, 23, 59, 59, tzinfo=UTC)
    """
    parsed = parse_date(date_str)
    dt = datetime.strptime(parsed, "%Y-%m-%d").replace(tzinfo=UTC)
    # End of day
    return dt.replace(hour=23, minute=59, second=59)


def validate_period(period: int) -> int:
    """
    Validate period in YYYYMM format.

    Args:
        period: Period as integer (e.g., 202601 for January 2026)

    Returns:
        int: Validated period

    Raises:
        InvalidPeriodError: If period format is invalid

    Examples:
        >>> validate_period(202601)
        202601
        >>> validate_period(202613)  # doctest: +SKIP
        InvalidPeriodError: Invalid month: 13 in period 202613
    """
    if period < 190001 or period > 299912:
        raise InvalidPeriodError(f"Invalid period: {period}. Expected format YYYYMM (e.g., 202601)")

    month = period % 100

    if month < 1 or month > 12:
        raise InvalidPeriodError(f"Invalid month: {month} in period {period}. Month must be 01-12")

    return period
