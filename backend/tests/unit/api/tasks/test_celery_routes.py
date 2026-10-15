"""Producer task names resolve to queues consumed by the configured workers."""

import pytest

from api.celery_app import celery_app


@pytest.mark.unit
@pytest.mark.parametrize(
    ("task_name", "queue"),
    [
        ("api.tasks.processing.download_recording", "downloads"),
        ("api.tasks.processing.trim_video", "processing_cpu"),
        ("api.tasks.processing.enqueue_video_previews", "async_operations"),
        ("api.tasks.processing.generate_video_previews", "previews"),
        ("api.tasks.processing.generate_poster", "previews"),
        ("api.tasks.processing.transcribe_recording", "async_operations"),
        ("api.tasks.processing.extract_topics", "async_operations"),
        ("api.tasks.processing.generate_subtitles", "async_operations"),
        ("api.tasks.processing.finalize_pipeline", "async_operations"),
        ("maintenance.requeue_stale_video_previews", "maintenance"),
        ("maintenance.reconcile_upload_dispatches", "maintenance"),
    ],
)
def test_celery_route(task_name: str, queue: str):
    assert task_name in celery_app.tasks
    assert celery_app.amqp.router.route({}, task_name, args=())["queue"].name == queue
