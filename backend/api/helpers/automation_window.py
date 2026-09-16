"""Inclusive calendar windows for automation sync and matching.

Days are counted in the job timezone (schedule.timezone, else Europe/Moscow).
Last N days includes today: N=1 is today only. API date strings and DB bounds
are derived from the same local calendar dates.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DEFAULT_AUTOMATION_TIMEZONE = "Europe/Moscow"
PROVIDER_SYNC_MAX_DAYS = 30
MATCH_QUERY_LIMIT = 1000
UNBOUNDED_MATCH_QUERY_LIMIT = 5000


@dataclass(frozen=True)
class JobTimeWindow:
    """Inclusive local-calendar range plus UTC instants for SQL."""

    from_date: str | None
    to_date: str
    from_datetime: datetime | None
    to_datetime: datetime


def resolve_job_timezone(schedule: dict | None) -> str:
    tz = (schedule or {}).get("timezone")
    if isinstance(tz, str) and tz.strip():
        return tz.strip()
    return DEFAULT_AUTOMATION_TIMEZONE


def _zone(tz_name: str) -> ZoneInfo:
    try:
        return ZoneInfo(tz_name)
    except ZoneInfoNotFoundError:
        return ZoneInfo(DEFAULT_AUTOMATION_TIMEZONE)


def _local_now(tz_name: str, now: datetime | None) -> datetime:
    tz = _zone(tz_name)
    if now is None:
        return datetime.now(tz)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    return now.astimezone(tz)


def last_n_calendar_days(
    n: int,
    *,
    tz_name: str,
    now: datetime | None = None,
) -> JobTimeWindow:
    """Inclusive last N local calendar days ending today. N is clamped to >= 1."""
    days = max(1, n)
    now_local = _local_now(tz_name, now)
    tz = now_local.tzinfo
    today = now_local.date()
    from_date = today - timedelta(days=days - 1)
    start = datetime.combine(from_date, time.min, tzinfo=tz)
    end = datetime.combine(today, time(23, 59, 59, 999999), tzinfo=tz)
    return JobTimeWindow(
        from_date=from_date.isoformat(),
        to_date=today.isoformat(),
        from_datetime=start.astimezone(UTC),
        to_datetime=end.astimezone(UTC),
    )


def resolve_job_window(
    sync_days: int | None,
    *,
    tz_name: str,
    now: datetime | None = None,
    for_api_sync: bool = False,
) -> JobTimeWindow:
    """Match window from job sync_days; API sync uses last 30 days when unbounded."""
    if sync_days is None:
        if for_api_sync:
            return last_n_calendar_days(PROVIDER_SYNC_MAX_DAYS, tz_name=tz_name, now=now)
        today_window = last_n_calendar_days(1, tz_name=tz_name, now=now)
        return JobTimeWindow(
            from_date=None,
            to_date=today_window.to_date,
            from_datetime=None,
            to_datetime=today_window.to_datetime,
        )
    return last_n_calendar_days(sync_days, tz_name=tz_name, now=now)
