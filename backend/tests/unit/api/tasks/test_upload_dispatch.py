"""Auto-upload publication survives launcher retries without changing task identity."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from api.helpers.failure_handler import handle_upload_failure
from api.services.upload_dispatch import (
    UploadDispatchIntent,
    finish_upload_dispatch,
    prepare_upload_dispatch,
    publish_upload_dispatch,
)
from api.tasks.base import UploadTask
from api.tasks.processing import _launch_uploads_task
from api.tasks.upload import _supersede_saved_dispatch, batch_upload_recordings, upload_enqueue_skip_reason
from models.recording import TargetStatus


def _session_factory(mocker, session):
    factory = mocker.patch("api.services.upload_dispatch.get_async_session_maker")
    factory.return_value.return_value.__aenter__ = AsyncMock(return_value=session)
    factory.return_value.return_value.__aexit__ = AsyncMock(return_value=None)
    return factory


@pytest.mark.unit
def test_uploaded_target_without_remote_id_does_not_upload_again():
    target = SimpleNamespace(status=TargetStatus.UPLOADED, target_meta={})
    assert "review" in upload_enqueue_skip_reason(target)


@pytest.mark.unit
def test_explicit_upload_invalidates_old_automatic_message():
    target = SimpleNamespace(dispatch_task_id="old-id", dispatch_finished_at=None)
    _supersede_saved_dispatch(target, None)
    assert target.dispatch_task_id is None
    assert target.dispatch_finished_at is not None


@pytest.mark.unit
def test_automatic_upload_keeps_its_own_dispatch_token():
    target = SimpleNamespace(dispatch_task_id="saved-id", dispatch_finished_at=None)
    _supersede_saved_dispatch(target, "saved-id")
    assert target.dispatch_task_id == "saved-id"
    assert target.dispatch_finished_at is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_prepare_upload_dispatch_reuses_pending_task_id(mocker):
    target = SimpleNamespace(
        id=12,
        status=TargetStatus.NOT_UPLOADED,
        failed=False,
        dispatch_task_id="saved-id",
        dispatch_finished_at=None,
        dispatch_published_at=None,
    )
    session = MagicMock(refresh=AsyncMock(), commit=AsyncMock())
    _session_factory(mocker, session)
    repo = mocker.patch("api.services.upload_dispatch.RecordingRepository").return_value
    repo.get_by_id = AsyncMock(return_value=SimpleNamespace(id=8))
    repo.get_or_create_output_target = AsyncMock(return_value=target)

    intent = await prepare_upload_dispatch(8, "owner", "youtube", 2, {"title": "Lecture"})

    assert intent == UploadDispatchIntent(12, "saved-id")
    session.refresh.assert_awaited_once_with(target, with_for_update=True)
    session.commit.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_published_intent_keeps_one_task_id(mocker):
    target = SimpleNamespace(
        id=12,
        status=TargetStatus.NOT_UPLOADED,
        failed=False,
        dispatch_task_id="saved-id",
        dispatch_finished_at=None,
        dispatch_published_at=datetime.now(UTC),
    )
    session = MagicMock(refresh=AsyncMock(), commit=AsyncMock())
    _session_factory(mocker, session)
    repo = mocker.patch("api.services.upload_dispatch.RecordingRepository").return_value
    repo.get_by_id = AsyncMock(return_value=SimpleNamespace(id=8))
    repo.get_or_create_output_target = AsyncMock(return_value=target)

    assert await prepare_upload_dispatch(8, "owner", "youtube", 2, None) == UploadDispatchIntent(
        12, "saved-id", "Already queued"
    )
    session.commit.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize("status", [TargetStatus.UPLOADING, TargetStatus.FAILED])
async def test_auto_dispatch_never_replays_uncertain_or_failed_upload(mocker, status):
    target = SimpleNamespace(
        id=12,
        status=status,
        failed=status == TargetStatus.FAILED,
        dispatch_task_id="old-id",
    )
    session = MagicMock(refresh=AsyncMock(), commit=AsyncMock())
    _session_factory(mocker, session)
    repo = mocker.patch("api.services.upload_dispatch.RecordingRepository").return_value
    repo.get_by_id = AsyncMock(return_value=SimpleNamespace(id=8))
    repo.get_or_create_output_target = AsyncMock(return_value=target)

    intent = await prepare_upload_dispatch(8, "owner", "youtube", 2, None)

    assert intent.reason is not None
    assert intent.task_id == "old-id"
    session.commit.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_publish_upload_marks_only_matching_intent(mocker):
    target = SimpleNamespace(
        id=12,
        recording_id=8,
        user_id=None,
        status=TargetStatus.NOT_UPLOADED,
        dispatch_task_id="saved-id",
        dispatch_finished_at=None,
        dispatch_platform="youtube",
        preset_id=2,
        dispatch_metadata_override={"title": "Lecture"},
    )
    session = MagicMock(get=AsyncMock(return_value=target), scalar=AsyncMock(return_value="owner"), commit=AsyncMock())
    _session_factory(mocker, session)
    task = mocker.patch("api.tasks.upload.upload_recording_to_platform.apply_async")

    assert await publish_upload_dispatch(12, "saved-id")

    task.assert_called_once_with(
        args=(8, "owner", "youtube", 2, None, {"title": "Lecture"}, "saved-id"), task_id="saved-id"
    )
    assert target.dispatch_published_at is not None
    assert target.dispatch_requested_at == target.dispatch_published_at
    session.commit.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_failed_upload_result_closes_dispatch(mocker):
    target = SimpleNamespace(dispatch_task_id="saved-id", status=TargetStatus.NOT_UPLOADED)
    recording = SimpleNamespace(id=8)
    session = MagicMock(scalar=AsyncMock(side_effect=[target, recording]), commit=AsyncMock())
    _session_factory(mocker, session)
    aggregate = mocker.patch("api.helpers.status_manager.update_aggregate_status")

    await finish_upload_dispatch(8, "owner", "youtube", "saved-id", {"status": "failed", "reason": "auth"})

    assert target.status == TargetStatus.FAILED
    assert target.failed is True
    assert target.failed_reason == "auth"
    assert target.dispatch_finished_at is not None
    aggregate.assert_called_once_with(recording)
    session.commit.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_old_upload_failure_cannot_fail_newer_dispatch(mocker):
    target = SimpleNamespace(dispatch_task_id="new-task", status=TargetStatus.NOT_UPLOADED)
    session = MagicMock(scalar=AsyncMock(return_value=target), refresh=AsyncMock(), commit=AsyncMock())
    factory = mocker.patch("api.dependencies.get_async_session_maker")
    factory.return_value.return_value.__aenter__ = AsyncMock(return_value=session)
    factory.return_value.return_value.__aexit__ = AsyncMock(return_value=None)
    repo = mocker.patch("api.repositories.recording_repos.RecordingRepository").return_value
    repo.get_by_id = AsyncMock(return_value=SimpleNamespace(id=8))
    handle = mocker.patch("api.helpers.failure_handler.handle_upload_failure", new=AsyncMock())

    await UploadTask()._handle_upload_failure_async(8, "owner", "youtube", RuntimeError("old failure"), "old-task")

    handle.assert_not_awaited()
    session.commit.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_vk_video_failure_updates_vk_target(mocker):
    output = SimpleNamespace(target_type="VK", status=TargetStatus.UPLOADING, failed=False, failed_reason=None)
    recording = SimpleNamespace(id=8, outputs=[output], failed=False)
    mocker.patch("api.helpers.status_manager.update_aggregate_status")

    await handle_upload_failure(recording, "vk_video", "remote error")

    assert output.status == TargetStatus.FAILED
    assert output.failed_reason == "remote error"


@pytest.mark.unit
def test_upload_launcher_retries_partial_publish_failure(mocker):
    intents = {
        "youtube": UploadDispatchIntent(11, "youtube-task"),
        "vk": UploadDispatchIntent(12, "vk-task"),
    }
    published = []

    def run_async(coroutine):
        name = coroutine.cr_code.co_name
        values = dict(coroutine.cr_frame.f_locals)
        coroutine.close()
        if name == "_check_pause":
            return False
        if name == "prepare_upload_dispatch":
            return intents[values["platform"]]
        if name == "publish_upload_dispatch":
            published.append(values["target_id"])
            if values["target_id"] == 12:
                raise RuntimeError("broker unavailable")
            return True
        raise AssertionError(name)

    mocker.patch.object(_launch_uploads_task, "run_async", side_effect=run_async)
    retry = mocker.patch.object(_launch_uploads_task, "retry", side_effect=RuntimeError("retry scheduled"))

    with pytest.raises(RuntimeError, match="retry scheduled"):
        _launch_uploads_task.run(8, "owner", ["youtube", "vk"], {}, None)

    assert published == [11, 12]
    assert "vk" in str(retry.call_args.kwargs["exc"])


@pytest.mark.unit
def test_batch_upload_retries_partial_publish_failure(mocker):
    def run_async(coroutine):
        name = coroutine.cr_code.co_name
        values = dict(coroutine.cr_frame.f_locals)
        coroutine.close()
        if name == "prepare_upload_dispatch":
            return UploadDispatchIntent(values["recording_id"], f"task-{values['recording_id']}")
        if name == "publish_upload_dispatch":
            if values["target_id"] == 9:
                raise RuntimeError("broker unavailable")
            return True
        raise AssertionError(name)

    mocker.patch.object(batch_upload_recordings, "run_async", side_effect=run_async)
    retry = mocker.patch.object(batch_upload_recordings, "retry", side_effect=RuntimeError("retry scheduled"))

    with pytest.raises(RuntimeError, match="retry scheduled"):
        batch_upload_recordings.run([8, 9], "owner", ["youtube"])

    assert "9:youtube" in str(retry.call_args.kwargs["exc"])
