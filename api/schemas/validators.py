"""API validators and parsers"""

from datetime import date, datetime, timedelta
from typing import Any

from pydantic import field_validator


class DateRangeMixin:
    """Mixin for working with date ranges."""

    @field_validator("from_date", "to_date", mode="before")
    @classmethod
    def parse_date_field(cls, v: Any) -> date | None:
        """
        Parses date from different formats.

        Supported formats:
        - ISO: 2025-12-01, 2025-12-01T10:00:00
        - European: 01/12/2025, 01-12-2025
        - Short year: 01/12/25, 01-12-25
        """
        if v is None or v == "":
            return None

        if isinstance(v, date):
            return v

        if isinstance(v, datetime):
            return v.date()

        if isinstance(v, str):
            v = v.strip()

            # Try standard formats
            formats = [
                "%Y-%m-%d",  # 2025-12-01
                "%d/%m/%Y",  # 01/12/2025
                "%d-%m-%Y",  # 01-12-2025
                "%d.%m.%Y",  # 01.12.2025
                "%d/%m/%y",  # 01/12/25
                "%d-%m-%y",  # 01-12-25
                "%d.%m.%y",  # 01.12.25
            ]

            for fmt in formats:
                try:
                    return datetime.strptime(v, fmt).date()
                except ValueError:
                    continue

        raise ValueError(f"Invalid date format: {v}. Use: YYYY-MM-DD, DD/MM/YYYY, DD-MM-YYYY or DD.MM.YYYY")

    @staticmethod
    def resolve_date_range(
        from_date: date | None,
        to_date: date | None,
        last_days: int | None,
    ) -> tuple[date, date | None]:
        """
        Calculates the final date range with priority.

        Logic:
        1. If last_days is specified - it is used (priority)
        2. Otherwise from_date/to_date is used
        3. Default: last 14 days
        """
        if last_days is not None:
            if last_days == 0:
                today = date.today()
                return today, today

            to_date = date.today()
            from_date = to_date - timedelta(days=last_days)
            return from_date, to_date

        if from_date is None:
            from_date = date.today() - timedelta(days=14)

        return from_date, to_date
