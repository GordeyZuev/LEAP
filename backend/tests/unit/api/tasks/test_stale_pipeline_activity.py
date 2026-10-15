"""Long pipelines are not reset while later stages still make progress."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from api.tasks.maintenance import (
    _has_recent_pipeline_activity,
    _reconcile_upload_dispatches,
    _requeue_stale_video_previews,
    _stale_active_recordings_query,
    reset_stale_active_recordings_task,
)
from models.recording import TargetStatus


@pytest.mark.unit
def test_recent_stage_activity_protects_a_long_pipeline():
    now = datetime.now(UTC)
    threshold = now - timedelta(hours=2)
    recording = SimpleNamespace(
        updated_at=now - timedelta(hours=3),
        processing_stages=[SimpleNamespace(updated_at=now - timedelta(minutes=20))],
    )

    assert _has_recent_pipeline_activity(recording, threshold)


@pytest.mark.unit
def test_pipeline_without_recent_activity_can_be_reset():
    now = datetime.now(UTC)
    threshold = now - timedelta(hours=2)
    recording = SimpleNamespace(
        updated_at=now - timedelta(hours=3),
        processing_stages=[SimpleNamespace(updated_at=now - timedelta(hours=3))],
    )

    assert not _has_recent_pipeline_activity(recording, threshold)


@pytest.mark.unit
def test_stale_cleanup_filters_live_stages_before_batch_limit():
    query = _stale_active_recordings_query(datetime.now(UTC) - timedelta(hours=2))
    sql = str(query.compile()).upper()

    assert "NOT (EXISTS" in sql
    assert "PROCESSING_STAGES.UPDATED_AT >=" in sql
    assert "LIMIT" in sql


@pytest.mark.unit
def test_stale_pipeline_cleanup_retries_database_failure(mocker):
    failure = RuntimeError("database unavailable")

    def fail_and_close(coroutine):
        coroutine.close()
        raise failure

    mocker.patch("api.tasks.maintenance.asyncio.run", side_effect=fail_and_close)
    retry = mocker.patch.object(reset_stale_active_recordings_task, "retry", side_effect=failure)

    with pytest.raises(RuntimeError, match="database unavailable"):
        reset_stale_active_recordings_task.run()

    retry.assert_called_once_with(exc=failure)


@pytest.mark.unit
def test_stale_pipeline_cleanup_waits_for_broker_backlog(mocker):
    redis = MagicMock(llen=AsyncMock(return_value=1))
    redis_context = MagicMock()
    redis_context.__aenter__ = AsyncMock(return_value=redis)
    redis_context.__aexit__ = AsyncMock(return_value=None)
    mocker.patch("redis.asyncio.from_url", return_value=redis_context)
    session_factory = mocker.patch("api.tasks.maintenance.get_async_session_maker")

    assert reset_stale_active_recordings_task.run() == {"status": "success", "reset": 0}
    redis.llen.assert_awaited_once_with("downloads")
    session_factory.return_value.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_stale_preview_recovery_is_bounded_and_uses_old_claim(mocker):
    session = MagicMock()
    session.execute = AsyncMock(
        return_value=MagicMock(
            all=lambda: [(8, "owner", "old-8", "IN_PROGRESS", 1), (9, "owner", "old-9", "FAILED", 2)]
        )
    )
    session_factory = mocker.patch("api.tasks.maintenance.get_async_session_maker")
    session_factory.return_value.return_value.__aenter__ = AsyncMock(return_value=session)
    session_factory.return_value.return_value.__aexit__ = AsyncMock(return_value=None)
    redis = MagicMock()
    redis.llen = AsyncMock(return_value=0)
    redis_context = MagicMock()
    redis_context.__aenter__ = AsyncMock(return_value=redis)
    redis_context.__aexit__ = AsyncMock(return_value=None)
    mocker.patch("redis.asyncio.from_url", return_value=redis_context)
    enqueue = mocker.patch(
        "api.services.video_previews.enqueue_video_previews", new=AsyncMock(side_effect=[True, False])
    )
    release = mocker.patch("api.services.video_previews.release_preview_queue_lock", new=AsyncMock())

    result = await _requeue_stale_video_previews()

    assert result == {"status": "success", "checked": 2, "queued": 1}
    assert [args.args[1:] for args in release.await_args_list] == [(8, "old-8"), (9, "old-9")]
    assert enqueue.await_args_list[0].kwargs == {
        "force": True,
        "expected_run_token": "old-8",
        "expected_status": "IN_PROGRESS",
    }
    assert enqueue.await_args_list[1].kwargs == {
        "force": True,
        "expected_run_token": "old-9",
        "expected_status": "FAILED",
    }
    assert "LIMIT" in str(session.execute.await_args.args[0].compile()).upper()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_stale_pending_preview_waits_for_broker_queue_to_drain(mocker):
    session = MagicMock()
    session.execute = AsyncMock(return_value=MagicMock(all=list))
    session_factory = mocker.patch("api.tasks.maintenance.get_async_session_maker")
    session_factory.return_value.return_value.__aenter__ = AsyncMock(return_value=session)
    session_factory.return_value.return_value.__aexit__ = AsyncMock(return_value=None)
    redis = MagicMock()
    redis.llen = AsyncMock(return_value=3)
    redis_context = MagicMock()
    redis_context.__aenter__ = AsyncMock(return_value=redis)
    redis_context.__aexit__ = AsyncMock(return_value=None)
    mocker.patch("redis.asyncio.from_url", return_value=redis_context)

    assert await _requeue_stale_video_previews() == {"status": "success", "checked": 0, "queued": 0}
    query = str(session.execute.await_args.args[0].compile())
    assert "preview_maker_stages.queued_at" not in query


@pytest.mark.unit
@pytest.mark.asyncio
async def test_reconcile_marks_old_started_upload_uncertain_without_republishing(mocker):
    target = SimpleNamespace(
        id=12, recording_id=8, status=TargetStatus.UPLOADING, failed=False, failed_at=None, dispatch_finished_at=None
    )
    recording = SimpleNamespace(id=8)
    session = MagicMock()
    session.execute = AsyncMock(
        side_effect=[MagicMock(scalars=lambda: [target]), MagicMock(scalars=lambda: [recording]), MagicMock(all=list)]
    )
    session.commit = AsyncMock()
    session_factory = mocker.patch("api.tasks.maintenance.get_async_session_maker")
    session_factory.return_value.return_value.__aenter__ = AsyncMock(return_value=session)
    session_factory.return_value.return_value.__aexit__ = AsyncMock(return_value=None)
    redis = MagicMock(llen=AsyncMock(return_value=0))
    redis_context = MagicMock()
    redis_context.__aenter__ = AsyncMock(return_value=redis)
    redis_context.__aexit__ = AsyncMock(return_value=None)
    mocker.patch("redis.asyncio.from_url", return_value=redis_context)
    publish = mocker.patch("api.services.upload_dispatch.publish_upload_dispatch", new=AsyncMock())
    aggregate = mocker.patch("api.helpers.status_manager.update_aggregate_status")

    assert await _reconcile_upload_dispatches() == {
        "status": "success",
        "checked": 0,
        "published": 0,
        "uncertain": 1,
    }
    assert target.status == TargetStatus.FAILED
    assert target.failed is True
    assert "verify the platform" in target.failed_reason
    session.commit.assert_awaited_once()
    publish.assert_not_awaited()
    aggregate.assert_called_once_with(recording)
