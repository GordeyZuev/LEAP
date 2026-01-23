"""Celery configuration for async task processing"""

import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from celery import Celery  # noqa: E402
from celery.signals import task_failure, task_postrun, task_prerun  # noqa: E402

from config.settings import get_settings  # noqa: E402

settings = get_settings()
database_url = settings.database.sync_url

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
celery_app.conf.task_routes = {
    # CPU-bound: Video processing (prefork pool, low concurrency)
    # Uses asyncio.run() for DB access, but main work is CPU-intensive
    "api.tasks.processing.trim_video": {"queue": "processing_cpu"},

    # I/O-bound: All other tasks (threads pool, safe for asyncio)
    # These tasks spend most time waiting for I/O (network, disk)
    "api.tasks.processing.download_recording": {"queue": "async_operations"},
    "api.tasks.processing.transcribe_recording": {"queue": "async_operations"},
    "api.tasks.processing.extract_topics": {"queue": "async_operations"},
    "api.tasks.processing.generate_subtitles": {"queue": "async_operations"},
    "api.tasks.processing.batch_transcribe_recording": {"queue": "async_operations"},
    "api.tasks.processing.process_recording": {"queue": "async_operations"},
    "api.tasks.processing.launch_uploads": {"queue": "async_operations"},
    "api.tasks.upload.*": {"queue": "async_operations"},
    "api.tasks.template.*": {"queue": "async_operations"},
    "api.tasks.sync.*": {"queue": "async_operations"},
    "automation.*": {"queue": "async_operations"},
    "maintenance.*": {"queue": "async_operations"},
}

# Приоритеты очередей
celery_app.conf.broker_transport_options = {
    "priority_steps": list(range(10)),  # 0-9, где 9 - наивысший приоритет
    "sep": ":",
    "queue_order_strategy": "priority",
}

# Celery Beat Schedule для периодических задач
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
}


@task_prerun.connect
def task_prerun_handler(task_id, task, *_args, **_kwargs):
    """Обработчик перед запуском задачи."""
    print(f"[CELERY] Starting task {task.name} [{task_id}]")


@task_postrun.connect
def task_postrun_handler(task_id, task, *_args, **_kwargs):
    """Обработчик после выполнения задачи."""
    print(f"[CELERY] Completed task {task.name} [{task_id}]")


@task_failure.connect
def task_failure_handler(task_id, exception, *_args, **_kwargs):
    """Обработчик при ошибке задачи."""
    print(f"[CELERY] Failed task [{task_id}]: {exception}")
