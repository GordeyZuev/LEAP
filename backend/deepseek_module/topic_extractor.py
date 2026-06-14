"""Topic extraction from transcription using DeepSeek"""

import math
import re
from pathlib import Path
from typing import Any

from openai import AsyncOpenAI

from api.shared.enums import Granularity
from logger import get_logger

from .config import DeepSeekConfig
from .prompts import (
    GRANULARITY_CONFIG,
    SYSTEM_PROMPT,
    SYSTEM_PROMPT_EN,
    TOPIC_EXTRACTION_PROMPT,
    TOPIC_EXTRACTION_PROMPT_EN,
)

logger = get_logger(__name__)

# Constants
MIN_PAUSE_MINUTES = 8.0
MIN_TOPIC_DURATION_SECONDS = 60
NOISE_WINDOW_MINUTES = 15
TIMESTAMP_PATTERN = r"\[?(\d{1,2}):(\d{2})(?::(\d{2}))?\]?\s*[-–—]\s*(.+)"
TIMESTAMP_PATTERN_MS = r"\[(\d{2}):(\d{2}):(\d{2})\.(\d{3})\s*-\s*(\d{2}):(\d{2}):(\d{2})\.(\d{3})\]\s*(.+)"
NOISE_PATTERNS = [r"редактор субтитров", r"корректор", r"продолжение следует"]
QUESTION_PATTERN = re.compile(r"^\d+\.\s*(.+)$")
MAIN_TOPIC_MIN_WORDS = 2
MAIN_TOPIC_MAX_WORDS = 4
MAIN_TOPIC_MIN_LENGTH = 3
MAIN_TOPIC_MAX_CHARS = 150

TOPIC_COUNT_FLOOR = 3
TOPIC_COUNT_MIN_CAP = 25
TOPIC_COUNT_MAX_CAP = 30


def _get_granularity_config(granularity: Granularity) -> dict:
    """Return config for granularity. Falls back to LONG if key missing."""
    return GRANULARITY_CONFIG.get(granularity.value, GRANULARITY_CONFIG[Granularity.LONG.value])


def _line_for_timestamp_match(line: str) -> str:
    """Strip markdown bullets/numbering so '* [00:01:00] - topic' matches TIMESTAMP_PATTERN."""
    return re.sub(r"^[-*•\d.)]+\s*", "", line.strip())


def _truncate_topic(topic: str) -> str:
    """Truncate topic: by word count or char length. Keeps first part + ellipsis."""
    words = topic.split()
    if len(words) > MAIN_TOPIC_MAX_WORDS:
        return " ".join(words[:MAIN_TOPIC_MAX_WORDS]) + "..."
    if len(topic) > MAIN_TOPIC_MAX_CHARS:
        return topic[:MAIN_TOPIC_MAX_CHARS].rsplit(" ", 1)[0] + "..."
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


class TopicExtractor:
    """Extract topics from transcription using DeepSeek API."""

    def __init__(self, config: DeepSeekConfig):
        self.config = config

        self.client = AsyncOpenAI(
            api_key=config.api_key,
            base_url=config.base_url,
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
    ) -> dict[str, Any]:
        """
        Extract topics from transcription via DeepSeek.

        Args:
            segments: List of segments with timestamps (required).
            recording_topic: Course/subject name for context (optional).
            granularity: Topic density (short/medium/long).

        Returns:
            Dict with topic_timestamps, main_topics, summary, questions, long_pauses.
            Optionally "usage" (prompt_tokens, completion_tokens, total_tokens) if API returns it.
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

        try:
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
            )

            main_topics = result.get("main_topics", [])
            topic_timestamps = result.get("topic_timestamps", [])

            topic_timestamps_with_end = self._add_end_timestamps(topic_timestamps, total_duration)

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
        except Exception as error:
            logger.exception(f"Failed to extract topics: error={error}", error=str(error))
            return {
                "topic_timestamps": [],
                "main_topics": [],
                "summary": "",
                "questions": [],
                "long_pauses": [],
            }

    async def extract_topics_from_file(
        self,
        segments_file_path: str,
        recording_topic: str | None = None,
        granularity: Granularity | str = Granularity.LONG,
        language: str | None = None,
        questions_count: int = 3,
    ) -> dict[str, Any]:
        """
        Extract topics from segments.txt file.

        Args:
            segments_file_path: Path to segments.txt with format [HH:MM:SS - HH:MM:SS] text.
            recording_topic: Course/subject name for context (optional).
            granularity: Topic density (Granularity or str "short"|"medium"|"long").
            questions_count: Number of self-check questions to generate.

        Returns:
            Same structure as extract_topics.
        """
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

            # Skip noise segments and segments in noise window
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
            if (last_noise - first_noise) >= NOISE_WINDOW_MINUTES * 60:
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
        """
        Topic count from duration and GRANULARITY_CONFIG.
        Derived: min = ceil(duration/duration_max), max = floor(duration/duration_min).

        Args:
            duration_minutes: Session duration in minutes.
            granularity: Topic density (short/medium/long).

        Returns:
            (min_topics, max_topics)
        """
        cfg = _get_granularity_config(granularity)
        d_min, d_max = cfg["duration_min"], cfg["duration_max"]
        min_topics = max(TOPIC_COUNT_FLOOR, min(TOPIC_COUNT_MIN_CAP, math.ceil(duration_minutes / d_max)))
        max_topics = max(min_topics, min(TOPIC_COUNT_MAX_CAP, math.floor(duration_minutes / d_min)))
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
    ) -> dict[str, Any]:
        """
        Analyze transcript via DeepSeek/Fireworks.

        Args:
            transcript: Full transcript with timestamps.
            total_duration: Video duration in seconds.
            recording_topic: Course/subject name.
            granularity: Topic density.

        Returns:
            Dict with main_topics, topic_timestamps, summary, questions, long_pauses.
            Optional "usage" if API returns it (OpenAI-compatible: prompt_tokens, completion_tokens, total_tokens).
        """
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

        long_pauses = self._detect_long_pauses(segments or [], min_gap_minutes=MIN_PAUSE_MINUTES)
        pauses_instruction = ""
        if long_pauses:
            if is_en:
                pauses_lines = [
                    f"- {self._format_time(pause['start'])} – {self._format_time(pause['end'])} "
                    f"(≈{pause['duration_minutes']:.1f} min)"
                    for pause in long_pauses
                ]
                pauses_instruction = (
                    "\n\n⚠️ IMPORTANT: Pauses of >=8 minutes were found. You MUST add them to the topic list:\n"
                    + "\n".join(pauses_lines)
                    + "\n\nFor each pause: [HH:MM:SS] - Break (HH:MM:SS is the start time from the list above)."
                )
            else:
                pauses_lines = [
                    f"- {self._format_time(pause['start'])} – {self._format_time(pause['end'])} (≈{pause['duration_minutes']:.1f} мин)"
                    for pause in long_pauses
                ]
                pauses_instruction = (
                    "\n\n⚠️ ВАЖНО: Найдены перерывы >=8 минут. ОБЯЗАТЕЛЬНО добавь их в список тем:\n"
                    + "\n".join(pauses_lines)
                    + "\n\nДля каждой паузы: [HH:MM:SS] - Перерыв (где HH:MM:SS — время начала из списка выше)."
                )

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
            split_instruction = cfg.get(
                "split_instruction_en",
                cfg.get("split_instruction", f"split into several topics of {d_min}–{d_max} minutes each"),
            )
            duration_rule = f"From {d_min} to {d_max} minutes per topic."
        else:
            split_instruction = cfg.get("split_instruction", f"разбей на несколько тем по {d_min}–{d_max} минут каждая")
            duration_rule = f"От {d_min} до {d_max} минут на тему."
        prompt_params = {
            "context_line": context_line,
            "pauses_instruction": pauses_instruction,
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
        }
        template = TOPIC_EXTRACTION_PROMPT_EN if is_en else TOPIC_EXTRACTION_PROMPT
        prompt = template.format(**prompt_params)

        try:
            usage: dict[str, int] | None = None
            response = await self.client.chat.completions.create(
                model=self.config.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
                **self.config.to_request_params(),
            )
            if not hasattr(response, "choices") or not response.choices:
                error_msg = f"Unexpected DeepSeek API response format: type={type(response)}, value={response}"
                logger.error(error_msg)
                raise ValueError(error_msg)
            content = response.choices[0].message.content.strip()
            if hasattr(response, "usage") and response.usage is not None:
                u = response.usage
                usage = {
                    "prompt_tokens": getattr(u, "prompt_tokens", 0) or 0,
                    "completion_tokens": getattr(u, "completion_tokens", 0) or 0,
                    "total_tokens": getattr(u, "total_tokens", 0) or 0,
                }

            if not content:
                return {"main_topics": [], "topic_timestamps": [], "summary": "", "questions": [], "usage": usage}

            logger.debug(
                f"Response: length={len(content)} | preview={content[:500]}..."
                + (f" | tokens={usage}" if usage else "")
            )

            parsed = self._parse_structured_response(content, total_duration, questions_count)
            parsed["long_pauses"] = long_pauses
            if usage is not None:
                parsed["usage"] = usage
            logger.info(
                f"Parsed result: main_topics={len(parsed.get('main_topics', []))} | "
                f"topic_timestamps={len(parsed.get('topic_timestamps', []))} | total_duration={total_duration}s"
            )

            return parsed

        except Exception as error:
            logger.exception(f"Failed to analyze transcript: error={error}", error=str(error))
            return {
                "main_topics": [],
                "topic_timestamps": [],
                "summary": "",
                "questions": [],
                "long_pauses": [],
            }

    def _detect_long_pauses(self, segments: list[dict], min_gap_minutes: float = 8.0) -> list[dict]:
        """
        Find long pauses between segments.

        Args:
            segments: List of segments (will be sorted by start).
            min_gap_minutes: Minimum gap in minutes to report.

        Returns:
            [{"start", "end", "duration_minutes"}, ...]
        """
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

    def _parse_structured_response(self, text: str, total_duration: float, max_questions: int = 3) -> dict[str, Any]:
        """
        Parse LLM response: summary, main topics section, and [HH:MM:SS] - topic lines.

        Returns:
            Dict with summary, main_topics, topic_timestamps (start only; end added later).
        """
        main_topics: list[str] = []
        topic_timestamps: list[dict] = []
        summary = ""
        questions: list[str] = []

        lines = text.split("\n")

        in_main_topics = False
        in_summary = False
        in_questions = False
        main_topics_section_found = False
        summary_lines: list[str] = []

        for _, line in enumerate(lines):
            line_stripped = line.strip()
            if not line_stripped:
                continue
            if "САММАРИ" in line_stripped.upper() or "SUMMARY" in line_stripped.upper():
                in_summary = True
                continue
            if in_summary:
                if (
                    line_stripped.startswith("##")
                    or "ОСНОВНАЯ ТЕМА" in line_stripped.upper()
                    or "ДЕТАЛИЗИРОВАННЫЕ ТОПИКИ" in line_stripped.upper()
                ):
                    if summary_lines:
                        summary = " ".join(summary_lines).strip()
                    in_summary = False
                    summary_lines = []
                else:
                    summary_lines.append(line_stripped)
                continue

        main_topic = self._find_main_topic_before_section(lines)
        if main_topic:
            main_topics.append(main_topic)

        for i, line in enumerate(lines):
            line = line.strip()
            if not line:
                continue

            if (
                "ОСНОВНЫЕ ТЕМЫ" in line.upper()
                or "ОСНОВНЫЕ ТЕМЫ ПАРЫ" in line.upper()
                or "ОСНОВНАЯ ТЕМА" in line.upper()
            ):
                in_main_topics = True
                main_topics_section_found = True
                if i + 1 < len(lines):
                    next_line = lines[i + 1].strip()
                    if next_line and not next_line.startswith("##") and not next_line.startswith("#"):
                        topic_candidate = re.sub(r"^[-*•\d.)]+\s*", "", next_line).strip()
                        topic_candidate = re.sub(r"^\[.*?\]\s*", "", topic_candidate).strip()
                        if topic_candidate and len(topic_candidate) > 3 and "выведи" not in topic_candidate.lower():
                            words = topic_candidate.split()
                            if len(words) <= 4:
                                main_topics.append(topic_candidate)
                continue
            if "ДЕТАЛИЗИРОВАННЫЕ ТОПИКИ" in line.upper() or "ТОПИКИ С ТАЙМКОДАМИ" in line.upper():
                in_main_topics = False
                in_questions = False
                continue
            if "ВОПРОСЫ ДЛЯ САМОПРОВЕРКИ" in line.upper():
                in_main_topics = False
                in_questions = True
                continue
            if line.startswith("##"):
                in_main_topics = False
                in_questions = False
                continue

            question_match = QUESTION_PATTERN.match(line)
            if question_match and in_questions and len(questions) < max_questions:
                q = question_match.group(1).strip()
                if q:
                    questions.append(q)
                continue

            timestamp_match = re.match(TIMESTAMP_PATTERN, _line_for_timestamp_match(line))
            if timestamp_match:
                in_main_topics = False
                hours_str, minutes_str, seconds_str, topic = timestamp_match.groups()
                total_seconds = self._parse_timestamp_to_seconds(hours_str, minutes_str, seconds_str, total_duration)
                if 0 <= total_seconds <= total_duration:
                    topic_timestamps.append(
                        {
                            "topic": topic.strip(),
                            "start": float(total_seconds),
                        }
                    )
                else:
                    logger.debug(
                        f"Timestamp skipped (out of range): topic={topic.strip()} | "
                        f"position={total_seconds / 60:.1f}min | range=0-{total_duration / 60:.1f}min"
                    )
                continue

            if in_main_topics:
                if not line or line.startswith(("##", "#")):
                    continue

                topic = re.sub(r"^[-*•\d.)]+\s*", "", line).strip()
                topic = re.sub(r"^\[.*?\]\s*", "", topic).strip()

                if topic.startswith("[") and "выведи" in topic.lower():
                    continue

                if topic and len(topic) > 3:
                    main_topics.append(_truncate_topic(topic))

        if not topic_timestamps:
            topic_timestamps = self._parse_all_timestamps(lines, total_duration)

        if not topic_timestamps and not main_topics:
            topic_timestamps = self._parse_simple_timestamps(text, total_duration)

        if main_topics_section_found and not main_topics:
            logger.debug("Main topics section found but not extracted. Fallback search.")
            main_topic = self._find_topic_after_section_header(lines)
            if main_topic:
                main_topics.append(main_topic)

        if in_summary and summary_lines:
            summary = " ".join(summary_lines).strip()

        processed_main_topics = self._process_main_topics(main_topics)

        if processed_main_topics:
            logger.info(f"Main topic: {processed_main_topics[0]}")
        elif main_topics_section_found:
            logger.warning(
                f"⚠️ Main topics section found but extraction failed. First lines:\n{chr(10).join(lines[:10])}"
            )

        return {
            "summary": summary,
            "main_topics": processed_main_topics,
            "topic_timestamps": topic_timestamps,
            "questions": questions,
        }

    @staticmethod
    def _process_main_topics(main_topics: list[str]) -> list[str]:
        """Process and normalize main topics."""
        processed = []
        for topic in main_topics[:1]:
            topic = " ".join(topic.split())
            if topic and len(topic) > MAIN_TOPIC_MIN_LENGTH:
                processed.append(_truncate_topic(topic))
        return processed

    def _find_main_topic_before_section(self, lines: list[str]) -> str | None:
        """Find main topic before detailed topics section."""
        for i, line in enumerate(lines):
            line_stripped = line.strip()
            if not line_stripped:
                continue

            if "ДЕТАЛИЗИРОВАННЫЕ ТОПИКИ" in line_stripped.upper() or "ТОПИКИ С ТАЙМКОДАМИ" in line_stripped.upper():
                for j in range(max(0, i - 10), i):
                    candidate = lines[j].strip()
                    if not candidate or candidate.startswith(("##", "#")):
                        continue
                    if any(word in candidate.lower() for word in ["выведи", "тема", "пример"]):
                        continue
                    if re.match(TIMESTAMP_PATTERN, candidate):
                        continue

                    topic_candidate = re.sub(r"^[-*•\d.)]+\s*", "", candidate).strip()
                    topic_candidate = re.sub(r"^\[.*?\]\s*", "", topic_candidate).strip()
                    if topic_candidate and MAIN_TOPIC_MIN_WORDS <= len(topic_candidate.split()) <= MAIN_TOPIC_MAX_WORDS:
                        return topic_candidate
                break

        for line in lines[:10]:
            line_stripped = line.strip()
            if not line_stripped or line_stripped.startswith(("##", "#")):
                continue
            if re.match(TIMESTAMP_PATTERN, line_stripped):
                break
            if any(word in line_stripped.lower() for word in ["выведи", "тема", "пример"]):
                continue

            topic_candidate = re.sub(r"^[-*•\d.)]+\s*", "", line_stripped).strip()
            topic_candidate = re.sub(r"^\[.*?\]\s*", "", topic_candidate).strip()
            if topic_candidate and MAIN_TOPIC_MIN_WORDS <= len(topic_candidate.split()) <= MAIN_TOPIC_MAX_WORDS:
                return topic_candidate

        return None

    def _find_topic_after_section_header(self, lines: list[str]) -> str | None:
        """Find main topic after section header."""
        for i, line in enumerate(lines):
            if "ОСНОВНЫЕ ТЕМЫ" in line.upper() or "ОСНОВНЫЕ ТЕМЫ ПАРЫ" in line.upper():
                for j in range(i + 1, min(i + 5, len(lines))):
                    candidate = lines[j].strip()
                    if not candidate or candidate.startswith(("##", "#")):
                        continue

                    topic_candidate = re.sub(r"^[-*•\d.)]+\s*", "", candidate).strip()
                    topic_candidate = re.sub(r"^\[.*?\]\s*", "", topic_candidate).strip()

                    if (
                        topic_candidate
                        and len(topic_candidate) > MAIN_TOPIC_MIN_LENGTH
                        and not any(word in topic_candidate.lower() for word in ["выведи", "тема", "пример"])
                        and MAIN_TOPIC_MIN_WORDS <= len(topic_candidate.split()) <= MAIN_TOPIC_MAX_WORDS
                    ):
                        return topic_candidate
                break
        return None

    @staticmethod
    def _parse_timestamp_to_seconds(
        hours_str: str,
        minutes_str: str,
        seconds_str: str | None,
        total_duration_seconds: float = 0.0,
    ) -> int:
        """Convert timestamp components to total seconds.

        When seconds_str is None (MM:SS format), interprets as HH:MM if total_duration > 1h
        and first component >= 1 (likely hour), else MM:SS.
        """
        if seconds_str is not None:
            return int(hours_str) * 3600 + int(minutes_str) * 60 + int(seconds_str)
        # Two-part: HH:MM or MM:SS
        h, m = int(hours_str), int(minutes_str)
        if total_duration_seconds > 3600 and h >= 1:
            return h * 3600 + m * 60  # HH:MM
        return h * 60 + m  # MM:SS

    def _parse_all_timestamps(self, lines: list[str], total_duration: float) -> list[dict]:
        """Parse all lines with timestamps as fallback."""
        timestamps = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            match = re.match(TIMESTAMP_PATTERN, _line_for_timestamp_match(line))
            if match:
                hours_str, minutes_str, seconds_str, topic = match.groups()
                total_seconds = self._parse_timestamp_to_seconds(hours_str, minutes_str, seconds_str, total_duration)
                if 0 <= total_seconds <= total_duration:
                    timestamps.append({"topic": topic.strip(), "start": float(total_seconds)})
        return timestamps

    def _parse_simple_timestamps(self, text: str, total_duration: float) -> list[dict]:
        """Parse simple timestamp format as fallback."""
        return self._parse_all_timestamps(text.split("\n"), total_duration)

    def _add_end_timestamps(self, timestamps: list[dict], total_duration: float) -> list[dict]:
        """Add end timestamps to topics."""
        if not timestamps:
            return []

        sorted_timestamps = sorted(timestamps, key=lambda x: x.get("start", 0))
        result = []

        for i, ts in enumerate(sorted_timestamps):
            start = ts.get("start", 0)
            topic = ts.get("topic", "").strip()

            if not topic:
                continue

            if i < len(sorted_timestamps) - 1:
                end = sorted_timestamps[i + 1].get("start", 0)
                if end - start < MIN_TOPIC_DURATION_SECONDS:
                    end = min(start + MIN_TOPIC_DURATION_SECONDS, sorted_timestamps[i + 1].get("start", 0))
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
