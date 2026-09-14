"""Topic extraction from transcription using DeepSeek"""

import json
import math
import re
from pathlib import Path
from typing import Any

from openai import AsyncOpenAI

from api.shared.enums import Granularity
from config.settings import settings
from logger import get_logger

from .config import DeepSeekConfig
from .prompts import (
    GRANULARITY_CONFIG,
    JSON_EXAMPLE,
    SYSTEM_PROMPT,
    SYSTEM_PROMPT_EN,
    TOPIC_EXTRACTION_PROMPT,
    TOPIC_EXTRACTION_PROMPT_EN,
)

logger = get_logger(__name__)

TIMESTAMP_PATTERN_MS = r"\[(\d{2}):(\d{2}):(\d{2})\.(\d{3})\s*-\s*(\d{2}):(\d{2}):(\d{2})\.(\d{3})\]\s*(.+)"
NOISE_PATTERNS = [r"редактор субтитров", r"корректор", r"продолжение следует"]
HHMMSS_PATTERN = re.compile(r"^(\d{1,2}):(\d{2}):(\d{2})(?:\.\d+)?$")
JSON_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)

_te = settings.topic_extraction


class DeepSeekError(Exception):
    """DeepSeek API or parse failure. Empty extract must not be treated as success."""


def _get_granularity_config(granularity: Granularity) -> dict:
    """Return config for granularity. Falls back to LONG if key missing."""
    return GRANULARITY_CONFIG.get(granularity.value, GRANULARITY_CONFIG[Granularity.LONG.value])


def _truncate_topic(topic: str) -> str:
    """Truncate a main-topic title by word count, then by character length.

    Does not append an ellipsis: ``{{ themes }}`` is used in published video titles.
    """
    words = topic.split()
    if len(words) > _te.main_topic_max_words:
        topic = " ".join(words[: _te.main_topic_max_words])
    if len(topic) > _te.main_topic_max_chars:
        return topic[: _te.main_topic_max_chars].rsplit(" ", 1)[0]
    return topic


def _normalize_granularity(value: Granularity | str | None) -> Granularity:
    """Normalize str or None to Granularity enum. Invalid values fall back to LONG."""
    if isinstance(value, Granularity):
        return value
    s = (value or Granularity.LONG.value).strip().lower()
    try:
        return Granularity(s)
    except ValueError:
        return Granularity.LONG


def _sanitize_user_id(user_id: str | None) -> str | None:
    """DeepSeek user_id: [a-zA-Z0-9\\-_]+, max 512."""
    if not user_id:
        return None
    cleaned = re.sub(r"[^a-zA-Z0-9\-_]", "-", user_id.strip())[:512]
    return cleaned or None


class TopicExtractor:
    """Extract topics from transcription using DeepSeek API."""

    def __init__(self, config: DeepSeekConfig):
        self.config = config

        self.client = AsyncOpenAI(
            api_key=config.api_key,
            base_url=config.base_url,
            timeout=config.timeout,
        )

        logger.info(
            f"TopicExtractor initialized: base_url={config.base_url} | model={config.model}",
            base_url=config.base_url,
            model=config.model,
        )

    async def extract_topics(
        self,
        segments: list[dict],
        recording_topic: str | None = None,
        granularity: Granularity | str = Granularity.LONG,
        language: str | None = None,
        questions_count: int = 3,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Extract topics from transcription via DeepSeek.

        Returns:
            Dict with topic_timestamps, main_topics, summary, questions, long_pauses.
            Optionally "usage" if the API returns it.

        Raises:
            DeepSeekError: API, empty, or unusable JSON (no lecture chapters).
            ValueError: Segments missing.
        """
        if not segments:
            raise ValueError("Segments are required for topic extraction")

        gran = _normalize_granularity(granularity)

        total_duration = max(seg.get("end", seg.get("start", 0)) for seg in segments) if segments else 0.0
        duration_minutes = total_duration / 60
        min_topics, max_topics = self._calculate_topic_range(duration_minutes, granularity=gran)

        context_info = f" | topic={recording_topic}" if recording_topic else ""
        logger.info(
            f"Extracting topics: segments={len(segments)} | duration={duration_minutes:.1f}min | "
            f"range={min_topics}-{max_topics}{context_info}"
        )

        transcript_with_timestamps = self._format_transcript_with_timestamps(segments)

        result = await self._analyze_full_transcript(
            transcript_with_timestamps,
            total_duration,
            recording_topic,
            min_topics,
            max_topics,
            granularity=gran,
            segments=segments,
            language=language,
            questions_count=questions_count,
            user_id=user_id,
        )

        main_topics = result.get("main_topics", [])
        topic_timestamps = result.get("topic_timestamps", [])

        # Insert pauses first so lecture `end` is the pause start, not overlapping it.
        # `_add_end_timestamps` keeps detector `end`/`type` on pause rows.
        with_pauses = self._insert_pause_chapters(
            topic_timestamps,
            result.get("long_pauses", []),
            language=language,
        )
        topic_timestamps_with_end = self._add_end_timestamps(with_pauses, total_duration)
        if not any(ts.get("type") != "pause" for ts in topic_timestamps_with_end):
            raise DeepSeekError("DeepSeek JSON contained no in-range chapters")

        logger.info(
            f"Topics extracted successfully: main={len(main_topics)} | detailed={len(topic_timestamps_with_end)}",
            main_topics=len(main_topics),
            detailed_topics=len(topic_timestamps_with_end),
        )

        out: dict[str, Any] = {
            "topic_timestamps": topic_timestamps_with_end,
            "main_topics": main_topics,
            "summary": result.get("summary", ""),
            "questions": result.get("questions", []),
            "long_pauses": result.get("long_pauses", []),
        }
        if "usage" in result:
            out["usage"] = result["usage"]
        return out

    async def extract_topics_from_file(
        self,
        segments_file_path: str,
        recording_topic: str | None = None,
        granularity: Granularity | str = Granularity.LONG,
        language: str | None = None,
        questions_count: int = 3,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        """Extract topics from segments.txt file."""
        segments_path = Path(segments_file_path)
        if not segments_path.exists():
            raise FileNotFoundError(f"segments.txt file not found: {segments_file_path}")

        logger.info(f"Reading segments from file: {segments_file_path}")

        segments = self._parse_segments_from_file(segments_path)

        if not segments:
            raise ValueError(f"Failed to extract segments from file {segments_file_path}")

        logger.info(f"Read {len(segments)} segments from file {segments_file_path}")

        return await self.extract_topics(
            segments=segments,
            recording_topic=recording_topic,
            granularity=granularity,
            language=language,
            questions_count=questions_count,
            user_id=user_id,
        )

    def _format_transcript_with_timestamps(self, segments: list[dict]) -> str:
        """Format transcript with timestamps, filtering noise."""
        exclude_from, exclude_to = self._detect_noise_window(segments)
        segments_text = []

        for seg in segments:
            start = seg.get("start", 0)
            text = seg.get("text", "").strip()
            if not text:
                continue

            if any(re.search(pat, text.lower()) for pat in NOISE_PATTERNS):
                continue
            if exclude_from is not None and exclude_from <= start <= exclude_to:
                continue

            time_str = self._format_time(start)
            segments_text.append(f"{time_str} {text}")

        return "\n".join(segments_text)

    def _detect_noise_window(self, segments: list[dict]) -> tuple[float | None, float | None]:
        """Detect long noise window in segments."""
        noise_times = [
            float(seg.get("start", 0))
            for seg in segments
            if (text := (seg.get("text") or "").strip().lower()) and any(re.search(pat, text) for pat in NOISE_PATTERNS)
        ]

        if noise_times:
            first_noise, last_noise = min(noise_times), max(noise_times)
            if (last_noise - first_noise) >= _te.noise_window_minutes * 60:
                return first_noise, last_noise

        return None, None

    def _parse_segments_from_file(self, segments_path: Path) -> list[dict]:
        """Parse segments from file with timestamps."""
        segments = []
        timestamp_pattern = re.compile(r"\[(\d{2}):(\d{2}):(\d{2})\s*-\s*(\d{2}):(\d{2}):(\d{2})\]\s*(.+)")
        timestamp_pattern_ms = re.compile(TIMESTAMP_PATTERN_MS)

        with segments_path.open(encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue

                match_ms = timestamp_pattern_ms.match(line)
                match_s = timestamp_pattern.match(line) if not match_ms else None

                if match_ms or match_s:
                    try:
                        if match_ms:
                            start_h, start_m, start_s, start_ms = map(int, match_ms.groups()[:4])
                            end_h, end_m, end_s, end_ms = map(int, match_ms.groups()[4:8])
                            text = match_ms.groups()[8].strip()
                            start_seconds = start_h * 3600 + start_m * 60 + start_s + start_ms / 1000.0
                            end_seconds = end_h * 3600 + end_m * 60 + end_s + end_ms / 1000.0
                        elif match_s:
                            gr = match_s.groups()
                            start_h, start_m, start_s, end_h, end_m, end_s = map(int, gr[:6])
                            text = gr[6].strip()
                            start_seconds = start_h * 3600 + start_m * 60 + start_s
                            end_seconds = end_h * 3600 + end_m * 60 + end_s

                        if text:
                            segments.append(
                                {
                                    "start": float(start_seconds),
                                    "end": float(end_seconds),
                                    "text": text,
                                }
                            )
                    except (ValueError, IndexError) as e:
                        logger.warning(f"⚠️ Parse error at line {line_num}: {line[:50]}... - {e}")
                        continue

        return segments

    def _calculate_topic_range(
        self, duration_minutes: float, granularity: Granularity = Granularity.LONG
    ) -> tuple[int, int]:
        """Topic count from duration and GRANULARITY_CONFIG."""
        cfg = _get_granularity_config(granularity)
        d_min, d_max = cfg["duration_min"], cfg["duration_max"]
        min_topics = max(_te.topic_count_floor, min(_te.topic_count_min_cap, math.ceil(duration_minutes / d_max)))
        max_topics = max(min_topics, min(_te.topic_count_max_cap, math.floor(duration_minutes / d_min)))
        return min_topics, max_topics

    async def _analyze_full_transcript(
        self,
        transcript: str,
        total_duration: float,
        recording_topic: str | None = None,
        min_topics: int = 10,
        max_topics: int = 30,
        granularity: Granularity | str = Granularity.LONG,
        segments: list[dict] | None = None,
        language: str | None = None,
        questions_count: int = 3,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        """Call DeepSeek JSON mode and parse the object."""
        summary_language = (language or "").strip().lower() or "ru"
        is_en = summary_language.startswith("en")
        system_prompt = SYSTEM_PROMPT_EN if is_en else SYSTEM_PROMPT

        context_line = ""
        if recording_topic:
            if is_en:
                context_line = f"\nContext: this video is from the course '{recording_topic}'.\n"
            else:
                context_line = f"\nКонтекст: это видео по курсу '{recording_topic}'.\n"

        gran = _normalize_granularity(granularity)
        cfg = _get_granularity_config(gran)
        dur_min = total_duration / 60
        min_spacing_minutes = max(
            cfg["spacing_min"],
            min(cfg["spacing_max"], dur_min * cfg["spacing_factor"]),
        )

        long_pauses = self._detect_long_pauses(segments or [], min_gap_minutes=_te.min_pause_minutes)

        recording_topic_hint = ""
        if recording_topic:
            if is_en:
                recording_topic_hint = (
                    f" The topic title MUST NOT repeat words from the course title '{recording_topic}'. "
                    "If a topic contains such words — remove them. For example, if the course is "
                    "'Applied Python' and the topic would be 'Async programming in Python', "
                    "write only 'Async programming'."
                )
            else:
                recording_topic_hint = (
                    f" Название темы НЕ должно содержать слова из названия курса '{recording_topic}'. "
                    "Если тема содержит такие слова — убери их. Например, если курс называется "
                    "'Прикладной Python', а тема 'Асинхронное программирование Python', "
                    "напиши только 'Асинхронное программирование'."
                )

        d_min, d_max = cfg["duration_min"], cfg["duration_max"]
        if is_en:
            split_instruction = f"split into 2–3 topics of {d_min}–{d_max} minutes each"
            duration_rule = f"From {d_min} to {d_max} minutes per topic."
        else:
            split_instruction = f"разбей на 2–3 темы по {d_min}–{d_max} минут каждая"
            duration_rule = f"От {d_min} до {d_max} минут на тему."
        prompt_params = {
            "context_line": context_line,
            "json_example": JSON_EXAMPLE,
            "recording_topic_hint": recording_topic_hint,
            "summary_language": summary_language,
            "min_topics": min_topics,
            "max_topics": max_topics,
            "min_spacing_minutes": min_spacing_minutes,
            "questions_count": questions_count,
            "transcript": transcript,
            "duration_rule": duration_rule,
            "duration_min": d_min,
            "duration_max": d_max,
            "duration_range": f"{d_min}–{d_max}",
            "split_instruction": split_instruction,
            "main_topic_min_words": _te.main_topic_min_words,
            "main_topic_max_words": _te.main_topic_max_words,
        }
        template = TOPIC_EXTRACTION_PROMPT_EN if is_en else TOPIC_EXTRACTION_PROMPT
        prompt = template.format(**prompt_params)

        response = await self.client.chat.completions.create(
            model=self.config.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            **self.config.to_request_params(user_id=_sanitize_user_id(user_id)),
        )
        api_error = getattr(response, "error", None)
        if api_error:
            raise DeepSeekError(f"DeepSeek API error: {api_error}")
        if not getattr(response, "choices", None):
            raise DeepSeekError(f"Unexpected DeepSeek API response: type={type(response)}, value={response}")

        message = response.choices[0].message
        raw_content = getattr(message, "content", None)
        if not raw_content or not str(raw_content).strip():
            raise DeepSeekError("DeepSeek returned empty content")
        content = str(raw_content).strip()

        usage: dict[str, int] | None = None
        if getattr(response, "usage", None) is not None:
            u = response.usage
            usage = {
                "prompt_tokens": getattr(u, "prompt_tokens", 0) or 0,
                "completion_tokens": getattr(u, "completion_tokens", 0) or 0,
                "total_tokens": getattr(u, "total_tokens", 0) or 0,
                "prompt_cache_hit_tokens": getattr(u, "prompt_cache_hit_tokens", 0) or 0,
                "prompt_cache_miss_tokens": getattr(u, "prompt_cache_miss_tokens", 0) or 0,
            }
            details = getattr(u, "prompt_tokens_details", None)
            if details is not None and not usage["prompt_cache_hit_tokens"]:
                usage["prompt_cache_hit_tokens"] = getattr(details, "cached_tokens", 0) or 0

        logger.debug(
            f"Response: length={len(content)} | preview={content[:500]}..." + (f" | tokens={usage}" if usage else "")
        )

        parsed = self._parse_json_response(content, total_duration, questions_count)
        parsed["long_pauses"] = long_pauses
        if usage is not None:
            parsed["usage"] = usage
        logger.info(
            f"Parsed result: main_topics={len(parsed.get('main_topics', []))} | "
            f"topic_timestamps={len(parsed.get('topic_timestamps', []))} | total_duration={total_duration}s"
        )
        return parsed

    def _detect_long_pauses(self, segments: list[dict], min_gap_minutes: float = 8.0) -> list[dict]:
        """Find long pauses between segments."""
        if not segments:
            return []

        min_gap_seconds = min_gap_minutes * 60
        pauses: list[dict] = []
        sorted_segments = sorted(segments, key=lambda s: s.get("start", 0))

        for idx in range(len(sorted_segments) - 1):
            current = sorted_segments[idx]
            nxt = sorted_segments[idx + 1]
            current_end = float(current.get("end", current.get("start", 0) or 0))
            next_start = float(nxt.get("start", 0) or 0)
            gap = next_start - current_end
            if gap >= min_gap_seconds:
                pauses.append(
                    {
                        "start": current_end,
                        "end": next_start,
                        "duration_minutes": gap / 60,
                    }
                )

        return pauses

    @staticmethod
    def _format_time(seconds: float) -> str:
        """Format seconds to HH:MM:SS."""
        total_seconds = int(seconds)
        hours, remainder = divmod(total_seconds, 3600)
        minutes, secs = divmod(remainder, 60)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"

    def _parse_json_response(self, text: str, total_duration: float, max_questions: int = 3) -> dict[str, Any]:
        """Parse JSON object from the model. Raises DeepSeekError if unusable."""
        stripped = JSON_FENCE.sub("", text.strip()).strip()
        try:
            data = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise DeepSeekError(f"DeepSeek JSON parse failed: {exc}") from exc
        if not isinstance(data, dict):
            raise DeepSeekError("DeepSeek JSON must be an object")

        summary = str(data.get("summary") or "").strip()
        main_raw = data.get("main_topic")
        main_topics: list[str] = []
        if isinstance(main_raw, str) and main_raw.strip():
            main_topics = [main_raw.strip()]
        elif isinstance(main_raw, list) and main_raw:
            first = main_raw[0]
            if isinstance(first, str) and first.strip():
                main_topics.append(first.strip())

        topic_timestamps: list[dict] = []
        chapters = data.get("chapters") or []
        if not isinstance(chapters, list):
            raise DeepSeekError("DeepSeek JSON chapters must be a list")
        for ch in chapters:
            if not isinstance(ch, dict):
                continue
            title = str(ch.get("title") or ch.get("topic") or "").strip()
            start_raw = ch.get("start")
            if not title or start_raw is None:
                continue
            total_seconds = self._parse_chapter_start(start_raw, total_duration)
            if total_seconds is None:
                continue
            if 0 <= total_seconds <= total_duration:
                topic_timestamps.append({"topic": title, "start": float(total_seconds)})

        if not topic_timestamps:
            raise DeepSeekError("DeepSeek JSON contained no in-range chapters")

        questions: list[str] = []
        raw_questions = data.get("questions") or []
        if isinstance(raw_questions, list):
            for q in raw_questions:
                if isinstance(q, str) and q.strip() and len(questions) < max_questions:
                    questions.append(q.strip())

        processed_main_topics = self._process_main_topics(main_topics)
        if processed_main_topics:
            logger.info(f"Main topic: {processed_main_topics[0]}")

        return {
            "summary": summary,
            "main_topics": processed_main_topics,
            "topic_timestamps": topic_timestamps,
            "questions": questions,
        }

    def _parse_chapter_start(self, start_raw: Any, total_duration: float) -> float | None:
        """Parse HH:MM:SS or numeric seconds into seconds."""
        if isinstance(start_raw, (int, float)):
            return float(start_raw)
        s = str(start_raw).strip()
        match = HHMMSS_PATTERN.match(s)
        if not match:
            logger.debug(f"Chapter start skipped (not HH:MM:SS): {s!r}")
            return None
        h, m, sec = (int(match.group(1)), int(match.group(2)), int(match.group(3)))
        total = h * 3600 + m * 60 + sec
        if total > total_duration:
            return None
        return float(total)

    @staticmethod
    def _process_main_topics(main_topics: list[str]) -> list[str]:
        """Process and normalize main topics."""
        processed = []
        for topic in main_topics[:1]:
            topic = " ".join(topic.split())
            if topic and len(topic) > _te.main_topic_min_length:
                processed.append(_truncate_topic(topic))
        return processed

    def _insert_pause_chapters(
        self,
        timestamps: list[dict],
        long_pauses: list[dict],
        language: str | None = None,
    ) -> list[dict]:
        """Insert detector pauses into the chapter list. Uses detector end times."""
        if not long_pauses:
            return timestamps

        is_en = (language or "").strip().lower().startswith("en")
        title = "Break" if is_en else "Перерыв"
        result = list(timestamps)

        for pause in long_pauses:
            p_start = float(pause.get("start", 0))
            p_end = float(pause.get("end", p_start))
            if p_end <= p_start:
                continue
            if any(abs(float(ts.get("start", 0)) - p_start) < 1.0 for ts in result):
                continue
            result.append({"topic": title, "start": p_start, "end": p_end, "type": "pause"})

        return sorted(result, key=lambda x: x.get("start", 0))

    def _add_end_timestamps(self, timestamps: list[dict], total_duration: float) -> list[dict]:
        """Add end timestamps to lecture topics; keep detector end/type on pauses."""
        if not timestamps:
            return []

        sorted_timestamps = sorted(timestamps, key=lambda x: x.get("start", 0))
        result = []

        for i, ts in enumerate(sorted_timestamps):
            start = ts.get("start", 0)
            topic = ts.get("topic", "").strip()
            if not topic:
                continue

            if ts.get("type") == "pause":
                end = float(ts.get("end", start))
                end = min(end, total_duration)
                if start >= end:
                    continue
                result.append({"topic": topic, "start": start, "end": end, "type": "pause"})
                continue

            if i < len(sorted_timestamps) - 1:
                end = sorted_timestamps[i + 1].get("start", 0)
                if end - start < _te.min_topic_duration_seconds:
                    end = min(start + _te.min_topic_duration_seconds, sorted_timestamps[i + 1].get("start", 0))
            else:
                end = total_duration

            end = min(end, total_duration)
            if start >= end:
                logger.warning(
                    f"Topic skipped (invalid timestamps): topic={topic} | start={start:.1f}s | end={end:.1f}s",
                    topic=topic,
                    start_sec=round(start, 1),
                    end_sec=round(end, 1),
                )
                continue

            result.append({"topic": topic, "start": start, "end": end})

        return result
