"""The orchestrator keeps preview work independent of transcription output."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from api.tasks.processing import run_recording_task


@pytest.mark.unit
def test_full_pipeline_routes_preview_after_trim_and_parallelizes_text_steps(mocker):
    recording = SimpleNamespace(source=None, blank_record=False)
    full_config = {
        "trimming": {"enable_trimming": True},
        "transcription": {
            "enable_transcription": True,
            "enable_topics": True,
            "enable_subtitles": True,
        },
    }
    answers = {
        "_check_pause_before_pipeline": False,
        "_resolve_pipeline_config": (full_config, {"auto_upload": False}, recording, []),
        "_mts_prepare_or_exit": None,
        "_check_processing_quota": (True, None),
    }

    def run_async(coroutine):
        name = coroutine.cr_code.co_name
        coroutine.close()
        return answers.get(name)

    mocker.patch.object(run_recording_task, "run_async", side_effect=run_async)
    mocker.patch("api.tasks.processing.should_enqueue_leap_publish", return_value=False)
    mocker.patch("api.tasks.processing.bind_task_owner")
    chain_result = MagicMock(id="chain-id")
    chain_builder = mocker.patch("api.tasks.processing.chain")
    chain_builder.return_value.apply_async.return_value = chain_result

    result = run_recording_task.run(8, "owner")

    signatures = chain_builder.call_args.args
    assert [signature.task for signature in signatures[:4]] == [
        "api.tasks.processing.download_recording",
        "api.tasks.processing.trim_video",
        "api.tasks.processing.enqueue_video_previews",
        "api.tasks.processing.transcribe_recording",
    ]
    assert [signature.task for signature in signatures[4].tasks] == [
        "api.tasks.processing.extract_topics",
        "api.tasks.processing.generate_subtitles",
    ]
    assert signatures[5].task == "api.tasks.processing.finalize_pipeline"
    chain_builder.return_value.freeze.assert_called_once()
    assert result["status"] == "launched"


@pytest.mark.unit
def test_redelivered_orchestrator_does_not_publish_second_chain(mocker):
    def run_async(coroutine):
        name = coroutine.cr_code.co_name
        coroutine.close()
        return "already-reserved-chain" if name == "_claim_orchestration" else False

    mocker.patch.object(run_recording_task, "run_async", side_effect=run_async)
    chain_builder = mocker.patch("api.tasks.processing.chain")

    result = run_recording_task.run(8, "owner")

    assert result["status"] == "launched"
    assert result["result"]["chain_id"] == "already-reserved-chain"
    chain_builder.assert_not_called()
