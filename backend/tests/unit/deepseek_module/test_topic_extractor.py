"""TopicExtractor: JSON parse, empty/error raises, prompt format, pause chapters."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from api.shared.enums import Granularity
from deepseek_module.config import DeepSeekConfig
from deepseek_module.prompts import JSON_EXAMPLE, TOPIC_EXTRACTION_PROMPT, TOPIC_EXTRACTION_PROMPT_EN
from deepseek_module.topic_extractor import DeepSeekError, TopicExtractor, _sanitize_user_id
from models.recording import ProcessingStageStatus, ProcessingStageType


def _extractor() -> TopicExtractor:
    return TopicExtractor(DeepSeekConfig(api_key="test-key", timeout=900.0, model="deepseek-flash"))


@pytest.mark.unit
def test_prompt_format_keeps_json_example() -> None:
    params = {
        "context_line": "\nContext: course.\n",
        "json_example": JSON_EXAMPLE,
        "recording_topic_hint": "",
        "summary_language": "ru",
        "min_topics": 3,
        "max_topics": 10,
        "min_spacing_minutes": 4.0,
        "questions_count": 3,
        "transcript": "00:00:01 hello",
        "duration_rule": "От 3 до 12 минут на тему.",
        "duration_min": 3,
        "duration_max": 12,
        "duration_range": "3–12",
        "split_instruction": "разбей на 2–3 темы",
        "main_topic_min_words": 2,
        "main_topic_max_words": 8,
    }
    ru = TOPIC_EXTRACTION_PROMPT.format(**params)
    en = TOPIC_EXTRACTION_PROMPT_EN.format(**params)
    assert '"chapters"' in ru
    assert '"chapters"' in en
    assert "json" in ru.lower()
    assert "json" in en.lower()
    assert "Только фактические темы из транскрипции" in ru
    assert "объедини похожие" in ru
    assert "информативные" in ru
    assert "Only factual topics from the transcript" in en
    assert "merge similar" in en
    assert "informative" in en


@pytest.mark.unit
def test_to_request_params_json_and_thinking() -> None:
    cfg = DeepSeekConfig(api_key="k", model="deepseek-flash")
    params = cfg.to_request_params(user_id="user_000007")
    assert params["response_format"] == {"type": "json_object"}
    assert params["extra_body"]["thinking"] == {"type": "disabled"}
    assert params["extra_body"]["user_id"] == "user_000007"


@pytest.mark.unit
def test_sanitize_user_id() -> None:
    assert _sanitize_user_id("user_000007") == "user_000007"
    assert _sanitize_user_id("a b") == "a-b"
    assert _sanitize_user_id("") is None


@pytest.mark.unit
def test_parse_json_happy_path_adds_end_times() -> None:
    ext = _extractor()
    parsed = ext._parse_json_response(
        '{"summary": "A lecture.", "main_topic": "SQL joins", '
        '"chapters": [{"start": "00:05:00", "title": "Inner join"}, '
        '{"start": "00:20:00", "title": "Outer join"}], '
        '"questions": ["What is a join?"]}',
        total_duration=3600,
        max_questions=3,
    )
    assert parsed["main_topics"] == ["SQL joins"]
    assert parsed["summary"]
    assert parsed["questions"] == ["What is a join?"]
    with_end = ext._add_end_timestamps(parsed["topic_timestamps"], 3600)
    assert with_end[0]["end"] == 20 * 60
    assert with_end[-1]["end"] == 3600


@pytest.mark.unit
def test_parse_json_fence_and_empty_chapters_raises() -> None:
    ext = _extractor()
    fenced = '```json\n{"summary": "x", "main_topic": "Hi there", "chapters": [], "questions": []}\n```'
    with pytest.raises(DeepSeekError, match="no in-range chapters"):
        ext._parse_json_response(fenced, total_duration=100)


@pytest.mark.unit
def test_parse_invalid_json_raises() -> None:
    ext = _extractor()
    with pytest.raises(DeepSeekError, match="JSON parse failed"):
        ext._parse_json_response("not json", total_duration=100)


@pytest.mark.unit
def test_pause_inserted_with_detector_end() -> None:
    ext = _extractor()
    chapters = [{"topic": "Intro", "start": 0.0}, {"topic": "After break", "start": 900.0}]
    pauses = [{"start": 200.0, "end": 800.0, "duration_minutes": 10.0}]
    merged = ext._insert_pause_chapters(chapters, pauses, language="ru")
    with_end = ext._add_end_timestamps(merged, 1800.0)
    pause_rows = [c for c in with_end if c.get("type") == "pause"]
    assert len(pause_rows) == 1
    assert pause_rows[0]["topic"] == "Перерыв"
    assert pause_rows[0]["end"] == 800.0
    assert pause_rows[0]["start"] == 200.0
    assert with_end[0]["end"] == 200.0
    assert with_end[-1]["start"] == 900.0
    assert with_end[-1]["end"] == 1800.0
    assert "type" not in with_end[0]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_extract_raises_when_only_pauses_remain() -> None:
    ext = _extractor()
    ext._analyze_full_transcript = AsyncMock(
        return_value={
            "topic_timestamps": [{"topic": "Tail", "start": 1800.0}],
            "main_topics": ["SQL joins"],
            "summary": "s",
            "questions": [],
            "long_pauses": [{"start": 200.0, "end": 800.0}],
        }
    )
    with pytest.raises(DeepSeekError, match="no in-range chapters"):
        await ext.extract_topics([{"start": 0, "end": 1800, "text": "hello"}])


def test_parse_chapter_start_allows_fractional_seconds() -> None:
    ext = _extractor()
    parsed = ext._parse_json_response(
        '{"summary": "A lecture.", "main_topic": "SQL joins", '
        '"chapters": [{"start": "00:05:00.500", "title": "Inner join"}], '
        '"questions": []}',
        total_duration=3600,
        max_questions=3,
    )
    assert parsed["topic_timestamps"][0]["start"] == 5 * 60


@pytest.mark.unit
@pytest.mark.asyncio
async def test_analyze_raises_on_api_error_payload() -> None:
    ext = _extractor()
    response = SimpleNamespace(
        error={"message": "We were unable to start processing your request within the 900-second timeout limit."},
        choices=None,
        usage=None,
    )
    ext.client.chat.completions.create = AsyncMock(return_value=response)
    with pytest.raises(DeepSeekError, match="DeepSeek API error"):
        await ext._analyze_full_transcript(
            "00:00:01 hello",
            total_duration=60,
            segments=[{"start": 0, "end": 60, "text": "hello"}],
        )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_analyze_raises_on_empty_content() -> None:
    ext = _extractor()
    choice = SimpleNamespace(message=SimpleNamespace(content=""))
    response = SimpleNamespace(error=None, choices=[choice], usage=None)
    ext.client.chat.completions.create = AsyncMock(return_value=response)
    with pytest.raises(DeepSeekError, match="empty content"):
        await ext._analyze_full_transcript("00:00:01 hello", total_duration=60, segments=[])


@pytest.mark.unit
def test_skip_completed_requires_chapters() -> None:
    from api.tasks.processing import _should_skip_completed_topics

    stage = MagicMock()
    stage.stage_type = ProcessingStageType.EXTRACT_TOPICS
    stage.status = ProcessingStageStatus.COMPLETED
    rec = MagicMock()
    rec.processing_stages = [stage]
    rec.topic_timestamps = []
    assert _should_skip_completed_topics(rec, force=False) is False
    rec.topic_timestamps = [{"topic": "A", "start": 0, "end": 10}]
    assert _should_skip_completed_topics(rec, force=False) is True
    rec.topic_timestamps = [{"topic": "Перерыв", "start": 0, "end": 10, "type": "pause"}]
    assert _should_skip_completed_topics(rec, force=False) is False
    assert _should_skip_completed_topics(rec, force=True) is False


@pytest.mark.unit
def test_granularity_config_has_no_split_keys() -> None:
    from deepseek_module.prompts import GRANULARITY_CONFIG

    for key in GRANULARITY_CONFIG:
        assert "split_instruction" not in GRANULARITY_CONFIG[key]
        assert "split_instruction_en" not in GRANULARITY_CONFIG[key]
    assert Granularity.LONG.value in GRANULARITY_CONFIG
