"""Celery async tasks"""

from .automation import run_automation_job_task
from .maintenance import (
    auto_expire_recordings_task,
    cleanup_expired_tokens_task,
    cleanup_recording_files_task,
    hard_delete_recordings_task,
)
from .processing import (
    download_recording_task,
    extract_topics_task,
    generate_subtitles_task,
    process_recording_task,
    transcribe_recording_task,
    trim_video_task,
)
from .sync_tasks import bulk_sync_sources_task, sync_single_source_task
from .upload import batch_upload_recordings, upload_recording_to_platform
