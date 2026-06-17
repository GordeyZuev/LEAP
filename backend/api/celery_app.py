"""Celery configuration for async task processing"""

import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Shim: celery-sqlalchemy-scheduler 0.3.0 reads tz.zone (pytz-only attr);
# Celery 5.x uses zoneinfo.ZoneInfo which has tz.key. Patch from_schedule
# to be tz-agnostic — otherwise beat_schedule entries fail to register.
import time  # noqa: E402

import celery_sqlalchemy_scheduler.models as _csm_models  # noqa: E402
from celery import Celery  # noqa: E402
from celery.signals import (  # noqa: E402
    after_setup_logger,
    before_task_publish,
    task_failure,
    task_postrun,
    task_prerun,
    task_retry,
    worker_process_init,
)


def _tz_name(tz) -> str:
    """Return the IANA name regardless of whether tz is pytz or zoneinfo."""
    return getattr(tz, "zone", None) or getattr(tz, "key", None) or str(tz)


@classmethod  # type: ignore[misc]
def _patched_crontab_from_schedule(cls, session, schedule):
    # str() cast: celery 5.6+ keeps _orig_* as int when crontab(hour=3, minute=0)
    # is called with int literals; DB columns are VARCHAR so the implicit
    # `WHERE minute = 0` raises "operator does not exist: varchar = integer".
    spec = {
        "minute": str(schedule._orig_minute),
        "hour": str(schedule._orig_hour),
        "day_of_week": str(schedule._orig_day_of_week),
        "day_of_month": str(schedule._orig_day_of_month),
        "month_of_year": str(schedule._orig_month_of_year),
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


# Shim 2: celery-sqlalchemy-scheduler 0.3.0 uses pre-SQLAlchemy-2.0 syntax in
# PeriodicTaskChanged — `select([Model])` (list arg) and `Query.get()` — both
# rejected by SQLAlchemy 2.x. We replace the two offending classmethods with
# 2.x-style equivalents.
import datetime as _dt  # noqa: E402

from sqlalchemy import insert as _sa_insert, select as _sa_select, update as _sa_update  # noqa: E402


@classmethod  # type: ignore[misc]
def _patched_update_changed(_cls, _mapper, connection, _target):
    stmt = _sa_select(_csm_models.PeriodicTaskChanged).where(_csm_models.PeriodicTaskChanged.id == 1).limit(1)
    row = connection.execute(stmt).first()
    now = _dt.datetime.now()
    if row is None:
        connection.execute(_sa_insert(_csm_models.PeriodicTaskChanged).values(id=1, last_update=now))
    else:
        connection.execute(
            _sa_update(_csm_models.PeriodicTaskChanged)
            .where(_csm_models.PeriodicTaskChanged.id == 1)
            .values(last_update=now)
        )


@classmethod  # type: ignore[misc]
def _patched_last_change(_cls, session):
    row = session.get(_csm_models.PeriodicTaskChanged, 1)
    return row.last_update if row else None


_csm_models.PeriodicTaskChanged.update_changed = _patched_update_changed
_csm_models.PeriodicTaskChanged.last_change = _patched_last_change


from contextlib import ExitStack  # noqa: E402

from config.settings import get_settings  # noqa: E402
from logger import get_logger, setup_logger, short_task_id, short_user_id  # noqa: E402

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
    worker_send_task_events=True,
    task_send_sent_event=True,
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
    "api.tasks.processing.run_recording": {"queue": "async_operations"},
    "api.tasks.processing.launch_uploads": {"queue": "async_operations"},
    "api.tasks.template.*": {"queue": "async_operations"},
    "api.tasks.sync.*": {"queue": "async_operations"},
    "automation.*": {"queue": "async_operations"},
    "maintenance.*": {"queue": "maintenance"},
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
    "reset-stale-active-recordings": {
        # Clears on_air=True recordings whose pipeline_started_at is older than 2h.
        # Protects against worker crashes that leave on_air stuck forever.
        "task": "maintenance.reset_stale_active_recordings",
        "schedule": crontab(minute="*/30"),  # Every 30 minutes
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
# Task signals — structured lifecycle events for Loki / Grafana
# ---------------------------------------------------------------------------


def _task_queue(task) -> str:
    delivery_info = getattr(task.request, "delivery_info", None) or {}
    return delivery_info.get("routing_key") or delivery_info.get("exchange") or "celery"


def _short_name(name: str | None) -> str:
    return name.rsplit(".", 1)[-1] if name else "unknown"


# Per-process map of task_id → (start time, contextualize stack); cleared on
# postrun. The ExitStack holds the loguru contextualize CM so every log
# emitted *inside* the task body inherits task_id/recording_id/user_id without
# the task code having to bind them manually.
_TASK_STATE: dict[str, tuple[float, ExitStack]] = {}


def _extract_known_context(task) -> dict[str, object]:
    """Pull recording_id / user_id from a task's args or kwargs.

    Convention across LEAP tasks: ``recording_id`` and ``user_id`` are always
    the first two positional arguments (after ``self`` for bound tasks).
    Kwargs override positional matches.
    """
    kwargs = getattr(task.request, "kwargs", None) or {}
    args = getattr(task.request, "args", None) or []

    recording_id = kwargs.get("recording_id")
    user_id = kwargs.get("user_id")

    if recording_id is None and len(args) >= 1 and isinstance(args[0], int):
        recording_id = args[0]
    if user_id is None and len(args) >= 2 and isinstance(args[1], str):
        user_id = args[1]

    ctx: dict[str, object] = {}
    if recording_id is not None:
        ctx["recording_id"] = recording_id
    if user_id is not None:
        ctx["user_id"] = short_user_id(user_id)
    return ctx


@task_prerun.connect
def task_prerun_handler(task_id, task, *_args, **_kwargs):
    extra_context = _extract_known_context(task)

    stack = ExitStack()
    stack.enter_context(
        logger.contextualize(
            task_id=short_task_id(task_id),
            task_name=task.name,
            queue=_task_queue(task),
            **extra_context,
        )
    )

    _TASK_STATE[task_id] = (time.perf_counter(), stack)
    logger.bind(task_state="STARTED").debug(
        "Task started | task={} • id={}",
        _short_name(task.name),
        short_task_id(task_id),
    )


@task_postrun.connect
def task_postrun_handler(task_id, task, *, state, **_kwargs):
    entry = _TASK_STATE.pop(task_id, None)
    started, stack = entry if entry is not None else (None, None)
    duration_ms = round((time.perf_counter() - started) * 1000, 2) if started is not None else None
    # FAILURE is logged at ERROR by task_failure; keep postrun at INFO so
    # dashboards don't double-count failures.
    level = "INFO" if state == "SUCCESS" else "WARNING"
    logger.bind(task_state=state, duration_ms=duration_ms).log(
        level,
        "Task {} | task={} • id={} • {}ms",
        state.lower(),
        _short_name(task.name),
        short_task_id(task_id),
        f"{duration_ms:.1f}" if duration_ms is not None else "?",
    )

    if stack is not None:
        stack.close()


@task_failure.connect
def task_failure_handler(task_id, exception, _traceback, einfo, *, sender, **_kwargs):
    ctx = _extract_known_context(sender) if sender is not None and hasattr(sender, "request") else {}
    logger.bind(
        task_id=short_task_id(task_id),
        task_name=getattr(sender, "name", None),
        queue=_task_queue(sender) if sender is not None else None,
        task_state="FAILURE",
        exception_class=type(exception).__name__,
        **ctx,
    ).opt(exception=einfo.exception if einfo else exception).error(
        "Task failed | task={} • id={} • {}: {}",
        _short_name(getattr(sender, "name", None)),
        short_task_id(task_id),
        type(exception).__name__,
        exception,
    )


@task_retry.connect
def task_retry_handler(request, reason, *, sender, **_kwargs):
    logger.bind(
        task_id=short_task_id(request.id),
        task_name=getattr(sender, "name", None),
        queue=_task_queue(sender) if sender is not None else None,
        task_state="RETRY",
    ).warning(
        "Task retry | task={} • id={} • reason={}",
        _short_name(getattr(sender, "name", None)),
        short_task_id(request.id),
        reason,
    )


# ---------------------------------------------------------------------------
# Queue age tracking — sorted-set of enqueue timestamps per queue, exposed as
# `leap_queue_oldest_task_age_seconds` by a lazy collector in
# api.observability.metrics. ZADD on publish, ZREM on prerun.
# ---------------------------------------------------------------------------
import redis  # noqa: E402

from api.observability.metrics import ENQUEUE_KEY_PREFIX  # noqa: E402

_publish_redis_client: redis.Redis | None = None


def _publish_redis() -> redis.Redis:
    global _publish_redis_client
    if _publish_redis_client is None:
        _publish_redis_client = redis.Redis.from_url(settings.celery.broker_url, decode_responses=True)
    return _publish_redis_client


@before_task_publish.connect
def _record_enqueue_time(_sender=None, headers=None, properties=None, routing_key=None, **_kw):
    task_id = (headers or {}).get("id") or (properties or {}).get("correlation_id")
    if not task_id:
        return
    queue = routing_key or "celery"
    try:
        _publish_redis().zadd(f"{ENQUEUE_KEY_PREFIX}{queue}", {task_id: time.time()})
    except Exception as exc:
        logger.debug("Failed to record enqueue time for {}: {}", task_id, exc)


@task_prerun.connect
def _clear_enqueue_time(task_id, task, *_args, **_kwargs):
    try:
        _publish_redis().zrem(f"{ENQUEUE_KEY_PREFIX}{_task_queue(task)}", task_id)
    except Exception as exc:
        logger.debug("Failed to clear enqueue time for {}: {}", task_id, exc)
