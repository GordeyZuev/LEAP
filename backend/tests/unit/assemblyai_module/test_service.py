"""Unit tests for assemblyai_module.service (no network calls)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from assemblyai_module.config import AssemblyAIConfig, AssemblyAISettings
from assemblyai_module.service import AssemblyAITranscriptionService


def _make_config() -> AssemblyAIConfig:
    settings = AssemblyAISettings(
        speech_models=["universal-2"],
        language_code="ru",
        poll_interval=1.0,
        max_wait_seconds=60.0,
    )
    return AssemblyAIConfig(api_key="aai_test", settings=settings)


@pytest.mark.unit
class TestAssemblyAIServiceNormalizeSentences:
    def test_normalize_sentences_basic(self):
        svc = AssemblyAITranscriptionService(_make_config())
        raw = [
            {"text": "Hello world.", "start": 0, "end": 1500},
            {"text": "How are you?", "start": 2000, "end": 3500},
        ]
        segs = svc._normalize_sentences(raw)
        assert len(segs) == 2
        assert segs[0] == {"id": 0, "start": pytest.approx(0.0), "end": pytest.approx(1.5), "text": "Hello world."}
        assert segs[1] == {"id": 1, "start": pytest.approx(2.0), "end": pytest.approx(3.5), "text": "How are you?"}

    def test_normalize_sentences_skips_empty_text(self):
        svc = AssemblyAITranscriptionService(_make_config())
        raw = [
            {"text": "", "start": 0, "end": 500},
            {"text": "Real sentence.", "start": 1000, "end": 2000},
            {"text": "  ", "start": 2500, "end": 3000},
        ]
        segs = svc._normalize_sentences(raw)
        assert len(segs) == 1
        assert segs[0]["id"] == 0
        assert segs[0]["text"] == "Real sentence."

    def test_normalize_sentences_ids_sequential_no_gaps(self):
        svc = AssemblyAITranscriptionService(_make_config())
        raw = [
            {"text": "", "start": 0, "end": 100},
            {"text": "A.", "start": 200, "end": 300},
            {"text": "", "start": 400, "end": 500},
            {"text": "B.", "start": 600, "end": 700},
        ]
        segs = svc._normalize_sentences(raw)
        assert [s["id"] for s in segs] == [0, 1]

    def test_normalize_sentences_end_clamped(self):
        svc = AssemblyAITranscriptionService(_make_config())
        raw = [{"text": "word", "start": 1000, "end": 1000}]
        segs = svc._normalize_sentences(raw)
        assert segs[0]["end"] > segs[0]["start"]

    def test_normalize_sentences_empty_input(self):
        svc = AssemblyAITranscriptionService(_make_config())
        assert svc._normalize_sentences([]) == []


@pytest.mark.unit
class TestAssemblyAIServiceFetchSentences:
    @pytest.mark.asyncio
    async def test_fetch_sentences_returns_list(self):
        svc = AssemblyAITranscriptionService(_make_config())
        mock_response = MagicMock()
        mock_response.json.return_value = {"sentences": [{"text": "Hi.", "start": 0, "end": 500}]}
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("assemblyai_module.service.httpx.AsyncClient", return_value=mock_client):
            result = await svc._fetch_sentences("tid_abc")

        assert result == [{"text": "Hi.", "start": 0, "end": 500}]

    @pytest.mark.asyncio
    async def test_fetch_sentences_missing_key_returns_empty(self):
        svc = AssemblyAITranscriptionService(_make_config())
        mock_response = MagicMock()
        mock_response.json.return_value = {}
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("assemblyai_module.service.httpx.AsyncClient", return_value=mock_client):
            result = await svc._fetch_sentences("tid_abc")

        assert result == []


@pytest.mark.unit
class TestAssemblyAINormalizeFallback:
    def test_normalize_uses_sentences_when_present(self):
        svc = AssemblyAITranscriptionService(_make_config())
        data = {
            "text": "Hello world.",
            "language_code": "ru",
            "words": [{"text": "Hello", "start": 0, "end": 500}, {"text": "world.", "start": 600, "end": 1100}],
        }
        sentences = [{"text": "Hello world.", "start": 0, "end": 1100}]
        result = svc._normalize(data, "ru", raw_sentences=sentences)
        assert len(result["segments"]) == 1
        assert result["segments"][0]["text"] == "Hello world."

    def test_normalize_falls_back_when_sentences_empty(self):
        svc = AssemblyAITranscriptionService(_make_config())
        data = {
            "text": "Hello world.",
            "language_code": "ru",
            "words": [{"text": "Hello", "start": 0, "end": 500}, {"text": "world.", "start": 600, "end": 1100}],
        }
        result = svc._normalize(data, "ru", raw_sentences=[])
        assert len(result["segments"]) >= 1

    def test_normalize_falls_back_when_all_sentences_empty_text(self):
        svc = AssemblyAITranscriptionService(_make_config())
        data = {
            "text": "Hello.",
            "language_code": "ru",
            "words": [{"text": "Hello.", "start": 0, "end": 500}],
        }
        sentences = [{"text": "", "start": 0, "end": 500}]
        result = svc._normalize(data, "ru", raw_sentences=sentences)
        # _normalize_sentences returns [] → fallback to heuristic
        assert len(result["segments"]) >= 1


@pytest.mark.unit
class TestAssemblyAIServiceNormalize:
    def test_normalize_basic(self):
        svc = AssemblyAITranscriptionService(_make_config())
        data = {
            "text": "Hello world",
            "language_code": "en",
            "words": [
                {"text": "Hello", "start": 0, "end": 500},
                {"text": "world", "start": 600, "end": 1100},
            ],
        }
        result = svc._normalize(data, "ru")
        assert result["text"] == "Hello world"
        assert result["language"] == "en"
        assert len(result["words"]) == 2
        assert result["words"][0]["start"] == pytest.approx(0.0)
        assert result["words"][0]["end"] == pytest.approx(0.5)
        assert len(result["segments"]) >= 1

    def test_normalize_raises_on_empty_words(self):
        svc = AssemblyAITranscriptionService(_make_config())
        with pytest.raises(ValueError, match="No words"):
            svc._normalize({"text": "x", "words": []}, "ru")

    def test_normalize_fallback_language(self):
        svc = AssemblyAITranscriptionService(_make_config())
        data = {"text": "test", "words": [{"text": "test", "start": 0, "end": 500}]}
        result = svc._normalize(data, "en")
        assert result["language"] == "en"


@pytest.mark.unit
class TestAssemblyAIServiceSubmit:
    @pytest.mark.asyncio
    async def test_submit_sends_correct_payload(self):
        svc = AssemblyAITranscriptionService(_make_config())

        mock_response = MagicMock()
        mock_response.json.return_value = {"id": "test_id_123"}
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("assemblyai_module.service.httpx.AsyncClient", return_value=mock_client):
            transcript_id = await svc._submit("https://example.com/audio.mp3", "ru", ["Python"])

        assert transcript_id == "test_id_123"
        call_kwargs = mock_client.post.call_args
        payload = call_kwargs[1]["json"]
        assert payload["audio_url"] == "https://example.com/audio.mp3"
        assert payload["language_code"] == "ru"
        assert payload["keyterms_prompt"] == ["Python"]
        assert payload["speech_models"] == ["universal-2"]


@pytest.mark.unit
class TestAssemblyAIServicePoll:
    @pytest.mark.asyncio
    async def test_poll_returns_on_completed(self):
        svc = AssemblyAITranscriptionService(_make_config())

        completed_response = MagicMock()
        completed_response.json.return_value = {"status": "completed", "text": "ok"}
        completed_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(return_value=completed_response)

        with patch("assemblyai_module.service.httpx.AsyncClient", return_value=mock_client):
            result = await svc._poll("test_id")

        assert result["status"] == "completed"

    @pytest.mark.asyncio
    async def test_poll_raises_on_error_status(self):
        svc = AssemblyAITranscriptionService(_make_config())

        error_response = MagicMock()
        error_response.json.return_value = {"status": "error", "error": "Bad audio"}
        error_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(return_value=error_response)

        with patch("assemblyai_module.service.httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(RuntimeError, match="Bad audio"):
                await svc._poll("test_id")
