"""Schedule conversion and validation helpers"""

from datetime import datetime

import pytz
from croniter import croniter

from api.schemas.automation.schedule import CronSchedule, HoursSchedule, TimeOfDaySchedule, WeekdaysSchedule


def validate_min_interval(cron_expression: str, min_hours: int = 1) -> bool:
    """Validate that cron interval is >= min_hours."""
    try:
        cron = croniter(cron_expression, datetime.now())
        next_run = cron.get_next(datetime)
        following_run = cron.get_next(datetime)
        interval_hours = (following_run - next_run).total_seconds() / 3600
        return interval_hours >= min_hours
    except (ValueError, KeyError):
        return False


def get_next_run_time(cron_expression: str, timezone_str: str) -> datetime:
    """Calculate next run time for cron expression in UTC."""
    tz = pytz.timezone(timezone_str)
    cron = croniter(cron_expression, datetime.now(tz))
    next_run = cron.get_next(datetime)
    return next_run.astimezone(pytz.UTC) if next_run.tzinfo else pytz.UTC.localize(next_run)


def schedule_to_cron(schedule: dict) -> tuple[str, str]:
    """Convert schedule dict to (cron_expression, human_readable)."""
    schedule_type = schedule.get("type")
    schedule_map = {
        "time_of_day": TimeOfDaySchedule,
        "hours": HoursSchedule,
        "weekdays": WeekdaysSchedule,
        "cron": CronSchedule,
    }

    if schedule_type not in schedule_map:
        raise ValueError(f"Unknown schedule type: {schedule_type}")

    obj = schedule_map[schedule_type](**schedule)
    return obj.to_cron(), obj.human_readable()
