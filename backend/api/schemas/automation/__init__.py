"""Schemas for automation jobs."""

from .filters import DEFAULT_AUTOMATION_STATUS_FILTER, AutomationFilters, sanitize_automation_status_filter
from .job import (
    AffectedRecording,
    AutomationJobCreate,
    AutomationJobListItem,
    AutomationJobResponse,
    AutomationJobUpdate,
    DryRunResult,
    JobListResponse,
    JobRunItem,
    JobRunListResponse,
    SyncConfig,
)
from .operations import TriggerJobResponse
from .schedule import (
    CronSchedule,
    HoursSchedule,
    Schedule,
    ScheduleType,
    TimeOfDaySchedule,
    WeekdaysSchedule,
)

__all__ = [
    "DEFAULT_AUTOMATION_STATUS_FILTER",
    "AffectedRecording",
    "AutomationFilters",
    "AutomationJobCreate",
    "AutomationJobListItem",
    "AutomationJobResponse",
    "AutomationJobUpdate",
    "CronSchedule",
    "DryRunResult",
    "HoursSchedule",
    "JobListResponse",
    "JobRunItem",
    "JobRunListResponse",
    "Schedule",
    "ScheduleType",
    "SyncConfig",
    "TimeOfDaySchedule",
    "TriggerJobResponse",
    "WeekdaysSchedule",
    "sanitize_automation_status_filter",
]
