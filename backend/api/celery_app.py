"""Celery configuration for async task processing"""

import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Shim: celery-sqlalchemy-scheduler 0.3.0 reads tz.zone (pytz-only attr);
# Celery 5.x uses zoneinfo.ZoneInfo which has tz.key. Patch from_schedule
# to be tz-agnostic — otherwise beat_schedule entries fail to register.
import celery_sqlalchemy_scheduler.models as _csm_models  # noqa: E402
from celery import Celery  # noqa: E402
from celery.signals import after_setup_logger, task_prerun, worker_process_init  # noqa: E402


def _tz_name(tz) -> str:
    """Return the IANA name regardless of whether tz is pytz or zoneinfo."""
    return getattr(tz, "zone", None) or getattr(tz, "key", None) or str(tz)


@classmethod  # type: ignore[misc]
def _patched_crontab_from_schedule(cls, session, schedule):
    spec = {
        "minute": schedule._orig_minute,
        "hour": schedule._orig_hour,
        "day_of_week": schedule._orig_day_of_week,
        "day_of_month": schedule._orig_day_of_month,
        "month_of_year": schedule._orig_month_of_year,
    }
    if schedule.tz:
        spec["timezone"] = _tz_name(schedule.tz)
    model = session.query(_csm_models.CrontabSchedule).filter_by(**spec).first()
    if not model:
        model = cls(**spec)
        session.add(model)
        session.commit()
    return model


_csm_models.CrontabSchedule.from_schedule = _patched_crontab_from_schedule

from config.settings import get_settings  # noqa: E402
from logger import get_logger, setup_logger, short_task_id  # noqa: E402

settings = get_settings()
database_url = settings.database.sync_url
logger = get_logger(__name__)

celery_app = Celery(
    "zoom_publishing",
    broker=settings.celery.broker_url,
    backend=settings.celery.result_backend,
    include=[
        "api.tasks.processing",
        "api.tasks.upload",
        "api.tasks.automation",
        "api.tasks.maintenance",
        "api.tasks.sync_tasks",
        "api.tasks.template",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=settings.celery.task_time_limit,
    task_soft_time_limit=settings.celery.task_soft_time_limit,
    worker_prefetch_multiplier=settings.celery.worker_prefetch_multiplier,
    worker_max_tasks_per_child=settings.celery.worker_max_tasks_per_child,
    task_acks_late=settings.celery.task_acks_late,
    task_reject_on_worker_lost=settings.celery.task_reject_on_worker_lost,
    result_expires=settings.celery.result_expires,
    beat_dburi=database_url,  # Database URI for celery-sqlalchemy-scheduler
)

# Task routing: Separate by execution requirements
# Queues:
#   downloads      – network-bound download tasks (dedicated threads worker)
#   uploads        – network-bound upload tasks   (dedicated threads worker)
#   async_operations – fast I/O processing tasks  (threads worker)
#   processing_cpu – CPU-intensive FFmpeg tasks    (prefork worker)
#   maintenance    – periodic cleanup              (prefork worker)
celery_app.conf.task_routes = {
    # CPU-bound: Video trimming (prefork pool, low concurrency)
    "api.tasks.processing.trim_video": {"queue": "processing_cpu"},
    # Network-bound downloads: isolated to prevent bandwidth starvation
    "api.tasks.processing.download_recording": {"queue": "downloads"},
    # Network-bound uploads: isolated so they don't block processing
    "api.tasks.upload.*": {"queue": "uploads"},
    # I/O-bound processing: transcription, topics, subtitles, orchestration
    "api.tasks.processing.transcribe_recording": {"queue": "async_operations"},
    "api.tasks.processing.extract_topics": {"queue": "async_operations"},
    "api.tasks.processing.generate_subtitles": {"queue": "async_operations"},
    "api.tasks.processing.batch_transcribe_recording": {"queue": "async_operations"},
    "api.tasks.processing.run_recording": {"queue": "async_operations"},
    "api.tasks.processing.launch_uploads": {"queue": "async_operations"},
    "api.tasks.template.*": {"queue": "async_operations"},
    "api.tasks.sync.*": {"queue": "async_operations"},
    "automation.*": {"queue": "async_operations"},
    "maintenance.*": {"queue": "maintenance"},
}

# Queue priorities
celery_app.conf.broker_transport_options = {
    "priority_steps": list(range(10)),  # 0-9, where 9 is highest priority
    "sep": ":",
    "queue_order_strategy": "priority",
}

# Celery Beat schedule for periodic tasks
from celery.schedules import crontab  # noqa: E402

celery_app.conf.beat_schedule = {
    "cleanup-expired-tokens": {
        "task": "maintenance.cleanup_expired_tokens",
        "schedule": crontab(hour=3, minute=0),  # Every day at 3:00 UTC
    },
    "auto-expire-recordings": {
        "task": "maintenance.auto_expire_recordings",
        "schedule": crontab(hour=3, minute=30),  # Every day at 3:30 UTC (after tokens)
    },
    "cleanup-recording-files": {
        "task": "maintenance.cleanup_recording_files",
        "schedule": crontab(hour=4, minute=0),  # Every day at 4:00 UTC (Level 1)
    },
    "hard-delete-recordings": {
        "task": "maintenance.hard_delete_recordings",
        "schedule": crontab(hour=5, minute=0),  # Every day at 5:00 UTC (Level 2)
    },
    "cleanup-temp-files": {
        # Safety net for FFmpeg/ASR temp files orphaned by hard kills (OOM/SIGKILL).
        # Pipeline tasks already clean up in finally blocks; this is belt-and-braces.
        "task": "maintenance.cleanup_temp_files",
        "schedule": crontab(minute=15),  # Hourly at :15
    },
}


# ---------------------------------------------------------------------------
# Loguru re-initialization after Celery daemonization
# ---------------------------------------------------------------------------
# When celery runs with --detach, it forks and closes all file descriptors.
# Loguru handlers created at import time (before fork) become invalid.
# These signals fire AFTER daemonization, so new handlers get fresh FDs.


@after_setup_logger.connect
def _reinit_loguru_after_celery(**_kwargs):
    """Re-create loguru handlers after Celery daemonizes (main worker process)."""
    setup_logger()


@worker_process_init.connect
def _reinit_loguru_in_child(**_kwargs):
    """Re-create loguru handlers in each prefork child process."""
    setup_logger()


# ---------------------------------------------------------------------------
# Task signals
# ---------------------------------------------------------------------------


@task_prerun.connect
def task_prerun_handler(task_id, task, *_args, **_kwargs):
    """Log task dispatch (DEBUG — Celery already logs 'received' at INFO)."""
    task_short = task.name.rsplit(".", 1)[-1] if task.name else "unknown"
    logger.debug(f"Worker executing | task={task_short} • id={short_task_id(task_id)}")
