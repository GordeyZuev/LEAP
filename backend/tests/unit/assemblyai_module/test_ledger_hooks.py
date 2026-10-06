"""AssemblyAI ledger hooks: billed seconds survive an empty transcript, retries do not resubmit."""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from assemblyai_module.service import (
    AssemblyAIJobError,
    AssemblyAITranscriptionService,
    EmptyTranscriptError,
)
from tests.unit.assemblyai_module.test_service import _make_config


@pytest.mark.unit
@pytest.mark.asyncio
async def test_empty_transcript_records_audio_seconds_before_error():
    svc = AssemblyAITranscriptionService(_make_config())
    svc._resolve_audio_url = AsyncMock(return_value="https://example.test/audio.mp3")
    svc._submit = AsyncMock(return_value="job-1")
    svc._poll = AsyncMock(return_value={"status": "completed", "audio_duration": 42.5, "text": "", "words": []})
    svc._fetch_sentences = AsyncMock(return_value=[])
    hooks = AsyncMock()

    with pytest.raises(EmptyTranscriptError) as exc:
        await svc.transcribe_audio("audio.mp3", "ru", [], hooks=hooks)

    hooks.submitted.assert_awaited_once_with("job-1")
    hooks.completed.assert_awaited_once()
    assert hooks.completed.await_args.args[:2] == ("job-1", 42.5)
    assert exc.value.transcript_id == "job-1"
    assert exc.value.audio_seconds == 42.5


@pytest.mark.unit
@pytest.mark.asyncio
async def test_resume_does_not_submit_again():
    svc = AssemblyAITranscriptionService(_make_config())
    svc._submit = AsyncMock(return_value="new-job")
    svc._poll = AsyncMock(return_value={"status": "completed", "audio_duration": 10, "text": "hi", "words": [{}]})
    svc._fetch_sentences = AsyncMock(return_value=[])
    svc._normalize = MagicMock(return_value={"text": "hi", "words": [], "segments": [], "language": "ru"})
    hooks = AsyncMock()

    result = await svc.transcribe_audio(
        "audio.mp3",
        "ru",
        [],
        hooks=hooks,
        resume_transcript_id="job-existing",
    )

    svc._submit.assert_not_called()
    hooks.submitted.assert_not_called()
    svc._poll.assert_awaited_once_with("job-existing")
    hooks.completed.assert_awaited_once()
    assert hooks.completed.await_args.args[:2] == ("job-existing", 10.0)
    assert result["text"] == "hi"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_provider_error_is_failed_and_not_completed():
    svc = AssemblyAITranscriptionService(_make_config())
    svc._resolve_audio_url = AsyncMock(return_value="https://example.test/audio.mp3")
    svc._submit = AsyncMock(return_value="job-err")
    svc._poll = AsyncMock(side_effect=AssemblyAIJobError("AssemblyAI transcription failed: boom", "job-err"))
    hooks = AsyncMock()

    with pytest.raises(AssemblyAIJobError):
        await svc.transcribe_audio("audio.mp3", "ru", [], hooks=hooks)

    hooks.failed.assert_awaited_once_with("job-err")
    hooks.completed.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_submit_timeout_recovers_the_transcript_instead_of_losing_it():
    svc = AssemblyAITranscriptionService(_make_config())
    svc._resolve_audio_url = AsyncMock(return_value="https://cdn.example/audio.mp3?sig=1")
    svc._submit = AsyncMock(side_effect=httpx.TimeoutException("timed out"))
    svc.find_transcript_id_by_audio_url = AsyncMock(return_value="job-recovered")
    svc._poll = AsyncMock(
        return_value={
            "status": "completed",
            "audio_duration": 15,
            "speech_model_used": "universal-2",
            "text": "hi",
            "words": [{}],
        }
    )
    svc._fetch_sentences = AsyncMock(return_value=[])
    svc._normalize = MagicMock(return_value={"text": "hi", "words": [], "segments": [], "language": "ru"})
    hooks = AsyncMock()

    result = await svc.transcribe_audio("audio.mp3", "ru", [], hooks=hooks)

    hooks.preparing.assert_awaited_once_with("https://cdn.example/audio.mp3?sig=1")
    hooks.submitted.assert_awaited_once_with("job-recovered")
    assert hooks.completed.await_args.args[:2] == ("job-recovered", 15.0)
    assert result["text"] == "hi"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_completed_without_duration_is_not_closed():
    svc = AssemblyAITranscriptionService(_make_config())
    svc._resolve_audio_url = AsyncMock(return_value="https://cdn.example/audio.mp3")
    svc._submit = AsyncMock(return_value="job-noduration")
    svc._poll = AsyncMock(return_value={"status": "completed", "text": "hi", "words": [{}]})
    svc.fetch_transcript = AsyncMock(return_value={"status": "completed", "text": "hi"})
    svc._fetch_sentences = AsyncMock(return_value=[])
    svc._normalize = MagicMock(return_value={"text": "hi", "words": [], "segments": [], "language": "ru"})
    hooks = AsyncMock()

    await svc.transcribe_audio("audio.mp3", "ru", [], hooks=hooks)

    hooks.submitted.assert_awaited_once_with("job-noduration")
    hooks.completed.assert_not_called()
