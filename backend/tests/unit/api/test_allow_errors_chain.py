"""allow_errors skips a stage inside the task and keeps the chain moving."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from celery.exceptions import SoftTimeLimitExceeded

from api.helpers.failure_handler import handle_transcribe_failure, stage_error_may_skip
from api.services.quota_service import QuotaExceededError
from api.tasks.base import ProcessingTask
from api.tasks.processing import _continue_after_stage_error
from models.recording import ProcessingStageStatus, ProcessingStageType, ProcessingStatus
from tests.fixtures.factories import create_mock_recording


def _recording(*stage_types: ProcessingStageType):
    stages = [
        SimpleNamespace(
            stage_type=stage_type,
            status=ProcessingStageStatus.IN_PROGRESS,
            failed=False,
            stage_meta=None,
        )
        for stage_type in stage_types
    ]
    recording = create_mock_recording(status=ProcessingStatus.PROCESSING, failed=False)
    recording.processing_stages = stages

    def _get_or_create_stage(stage_type):
        for stage in recording.processing_stages:
            if stage.stage_type == stage_type:
                return stage
        created = SimpleNamespace(
            stage_type=stage_type,
            status=ProcessingStageStatus.PENDING,
            failed=False,
            stage_meta=None,
        )
        recording.processing_stages.append(created)
        return created

    recording._get_or_create_stage = _get_or_create_stage
    return recording


def _status(recording, stage_type):
    return next(stage.status for stage in recording.processing_stages if stage.stage_type == stage_type)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_allow_errors_skips_transcription_without_failed_flag(mocker):
    mocker.patch("api.helpers.status_manager.update_aggregate_status")
    recording = _recording(
        ProcessingStageType.TRANSCRIBE,
        ProcessingStageType.EXTRACT_TOPICS,
        ProcessingStageType.GENERATE_SUBTITLES,
    )
    await handle_transcribe_failure(recording, ProcessingStageType.TRANSCRIBE, "asr down", True)

    assert _status(recording, ProcessingStageType.TRANSCRIBE) == ProcessingStageStatus.SKIPPED
    assert _status(recording, ProcessingStageType.EXTRACT_TOPICS) == ProcessingStageStatus.SKIPPED
    assert _status(recording, ProcessingStageType.GENERATE_SUBTITLES) == ProcessingStageStatus.SKIPPED
    assert recording.failed is False
    assert recording.failed_reason is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_allow_errors_does_not_invent_missing_stages(mocker):
    mocker.patch("api.helpers.status_manager.update_aggregate_status")
    recording = _recording(ProcessingStageType.TRANSCRIBE)
    await handle_transcribe_failure(recording, ProcessingStageType.TRANSCRIBE, "asr down", True)

    assert [stage.stage_type for stage in recording.processing_stages] == [ProcessingStageType.TRANSCRIBE]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_allow_errors_topics_does_not_skip_subtitles(mocker):
    mocker.patch("api.helpers.status_manager.update_aggregate_status")
    recording = _recording(ProcessingStageType.EXTRACT_TOPICS, ProcessingStageType.GENERATE_SUBTITLES)
    await handle_transcribe_failure(recording, ProcessingStageType.EXTRACT_TOPICS, "deepseek", True)

    assert _status(recording, ProcessingStageType.EXTRACT_TOPICS) == ProcessingStageStatus.SKIPPED
    assert _status(recording, ProcessingStageType.GENERATE_SUBTITLES) == ProcessingStageStatus.IN_PROGRESS
    assert recording.failed is False


@pytest.mark.unit
def test_allowed_error_returns_success_instead_of_retry():
    task = MagicMock()

    def _run_async(coro):
        coro.close()
        return True

    task.run_async.side_effect = _run_async
    task.build_result.return_value = {"status": "skipped"}

    result = _continue_after_stage_error(task, 1, "user", ProcessingStageType.TRANSCRIBE, RuntimeError("boom"))

    assert result == {"status": "skipped"}
    task.retry.assert_not_called()


@pytest.mark.unit
def test_quota_and_time_limit_are_not_skipped():
    assert stage_error_may_skip(SoftTimeLimitExceeded()) is False
    assert stage_error_may_skip(QuotaExceededError("full")) is False
    wrapped = RuntimeError("retries")
    wrapped.__cause__ = SoftTimeLimitExceeded()
    assert stage_error_may_skip(wrapped) is False
    assert stage_error_may_skip(RuntimeError("asr")) is True


@pytest.mark.unit
def test_run_recording_failure_clears_on_air(mocker):
    task = MagicMock()
    task.name = "api.tasks.processing.run_recording"
    ran = mocker.patch("api.tasks.base.asyncio.run")

    ProcessingTask.on_failure(task, RuntimeError("boom"), "task-id", [7, "user"], {}, None)

    task._clear_on_air_async.assert_called_once_with(7, "user")
    ran.assert_called_once()
