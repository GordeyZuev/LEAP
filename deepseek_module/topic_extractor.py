"""Topic extraction from transcription using DeepSeek"""

import re
from pathlib import Path
from typing import Any

import httpx
from openai import AsyncOpenAI

from logger import get_logger

from .config import DeepSeekConfig
from .prompts import DURATION_CONFIG, SYSTEM_PROMPT, TOPIC_EXTRACTION_PROMPT

logger = get_logger(__name__)

# Constants
MIN_PAUSE_MINUTES = 8.0
MIN_TOPIC_DURATION_SECONDS = 60
NOISE_WINDOW_MINUTES = 15
TIMESTAMP_PATTERN = r"\[?(\d{1,2}):(\d{2})(?::(\d{2}))?\]?\s*[-–—]\s*(.+)"
TIMESTAMP_PATTERN_MS = r"\[(\d{2}):(\d{2}):(\d{2})\.(\d{3})\s*-\s*(\d{2}):(\d{2}):(\d{2})\.(\d{3})\]\s*(.+)"
NOISE_PATTERNS = [r"редактор субтитров", r"корректор", r"продолжение следует"]
FIREWORKS_MAX_TOKENS_NON_STREAM = 4096
MAIN_TOPIC_MIN_WORDS = 2
MAIN_TOPIC_MAX_WORDS = 4
MAIN_TOPIC_MIN_LENGTH = 3


class TopicExtractor:
    """Extract topics from transcription using DeepSeek or Fireworks API."""

    def __init__(self, config: DeepSeekConfig):
        self.config = config

        base = (config.base_url or "").lower()
        allowed_domains = ("deepseek.com", "fireworks.ai")

        if not any(domain in base for domain in allowed_domains):
            raise ValueError(
                "Invalid TopicExtractor endpoint. "
                "Expected DeepSeek API (https://api.deepseek.com/v1) "
                "or Fireworks API (https://api.fireworks.ai/inference/v1). "
                f"Got: {config.base_url}"
            )

        self.is_fireworks = "fireworks.ai" in base

        if self.is_fireworks:
            self.client = None  # Use httpx directly for Fireworks-specific params
            self.api_key = config.api_key
            self.base_url = config.base_url
        else:
            self.client = AsyncOpenAI(
                api_key=config.api_key,
                base_url=config.base_url,
            )
            self.api_key = None
            self.base_url = None

        if self.is_fireworks:
            provider = "fireworks_deepseek"
        else:
            provider = "deepseek"
        logger.info(
            f"TopicExtractor initialized: provider={provider} | base_url={config.base_url} | model={config.model}",
            provider=provider,
            base_url=config.base_url,
            model=config.model,
        )

    async def extract_topics(
        self,
        segments: list[dict],
        recording_topic: str | None = None,
        granularity: str = "long",  # "short" | "medium" | "long"
        language: str | None = None,
    ) -> dict[str, Any]:
        """
        Extract topics from transcription via DeepSeek/Fireworks.

        Args:
            segments: List of segments with timestamps (required).
            recording_topic: Course/subject name for context (optional).

        Returns:
            Dict with topics:
                topic_timestamps: [{'topic', 'start', 'end'}, ...]
                main_topics: [str] (exactly 1 topic)
                long_pauses: [{'start', 'end', 'duration_minutes'}, ...] (pauses >=8 min)
        """
        if not segments:
            raise ValueError("Segments are required for topic extraction")

        granularity = (granularity or "long").strip().lower()
        if granularity not in ("short", "medium", "long"):
            granularity = "long"

        total_duration = max(seg.get("end", seg.get("start", 0)) for seg in segments) if segments else 0.0
        duration_minutes = total_duration / 60
        min_topics, max_topics = self._calculate_topic_range(duration_minutes, granularity=granularity)

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
                granularity=granularity,
                segments=segments,
                language=language,
            )

            main_topics = result.get("main_topics", [])
            topic_timestamps = result.get("topic_timestamps", [])

            topic_timestamps_with_end = self._add_end_timestamps(topic_timestamps, total_duration)

            logger.info(
                f"Topics extracted successfully: main={len(main_topics)} | detailed={len(topic_timestamps_with_end)}",
                main_topics=len(main_topics),
                detailed_topics=len(topic_timestamps_with_end),
            )

            return {
                "topic_timestamps": topic_timestamps_with_end,
                "main_topics": main_topics,
                "summary": result.get("summary", ""),
                "long_pauses": result.get("long_pauses", []),
            }
        except Exception as error:
            logger.exception(f"Failed to extract topics: error={error}", error=str(error))
            return {
                "topic_timestamps": [],
                "main_topics": [],
                "summary": "",
                "long_pauses": [],
            }

    async def extract_topics_from_file(
        self,
        segments_file_path: str,
        recording_topic: str | None = None,
        granularity: str = "long",  # "short" | "medium" | "long"
        language: str | None = None,
    ) -> dict[str, Any]:
        """
        Extract topics from segments.txt file.

        Args:
            segments_file_path: Path to segments.txt with format [HH:MM:SS - HH:MM:SS] text.
            recording_topic: Course/subject name for context (optional).
            granularity: "short", "medium", or "long".

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
                        else:
                            start_h, start_m, start_s, end_h, end_m, end_s = map(int, match_s.groups()[:6])
                            text = match_s.groups()[6].strip()
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

    def _calculate_topic_range(self, duration_minutes: float, granularity: str = "long") -> tuple[int, int]:
        """
        Dynamic topic range based on duration.
        short: 3-12 topics, medium: 6-16 topics, long: 10-26 topics.

        Args:
            duration_minutes: Session duration in minutes (clamped to 50-180).
            granularity: "short", "medium", or "long".

        Returns:
            (min_topics, max_topics)
        """
        duration_minutes = max(50, min(180, duration_minutes))

        if granularity == "short":
            min_topics = int(3 + (duration_minutes - 50) * 4 / 130)
            max_topics = int(5 + (duration_minutes - 50) * 5 / 130)
            min_topics = max(3, min(8, min_topics))
            max_topics = max(5, min(12, max_topics))
            return min_topics, max_topics

        if granularity == "medium":
            min_topics = int(6 + (duration_minutes - 50) * 5 / 130)
            max_topics = int(10 + (duration_minutes - 50) * 8 / 130)
            min_topics = max(6, min(12, min_topics))
            max_topics = max(10, min(18, max_topics))
            return min_topics, max_topics

        min_topics = int(10 + (duration_minutes - 50) * 8 / 130)
        max_topics = int(16 + (duration_minutes - 50) * 10 / 130)
        min_topics = max(10, min(18, min_topics))
        max_topics = max(16, min(26, max_topics))

        return min_topics, max_topics

    async def _analyze_full_transcript(
        self,
        transcript: str,
        total_duration: float,
        recording_topic: str | None = None,
        min_topics: int = 10,
        max_topics: int = 30,
        granularity: str = "long",  # "short" | "long"
        segments: list[dict] | None = None,
        language: str | None = None,
    ) -> dict[str, Any]:
        """
        Analyze transcript via DeepSeek/Fireworks.

        Args:
            transcript: Full transcript with timestamps.
            total_duration: Video duration in seconds.
            recording_topic: Course/subject name.

        Returns:
            Dict with main_topics and topic_timestamps.
        """
        context_line = ""
        if recording_topic:
            context_line = f"\nКонтекст: это видео по курсу '{recording_topic}'.\n"

        if granularity == "short":
            min_spacing_minutes = max(10, min(18, total_duration / 60 * 0.12))
        elif granularity == "medium":
            min_spacing_minutes = max(6, min(10, total_duration / 60 * 0.08))
        else:  # granularity == "long"
            min_spacing_minutes = max(4, min(6, total_duration / 60 * 0.05))

        long_pauses = self._detect_long_pauses(segments or [], min_gap_minutes=MIN_PAUSE_MINUTES)
        pauses_instruction = ""
        if long_pauses:
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
            recording_topic_hint = (
                f" Название темы НЕ должно содержать слова из названия курса '{recording_topic}'. "
                "Если тема содержит такие слова — убери их. Например, если курс называется "
                "'Прикладной Python', а тема 'Асинхронное программирование Python', "
                "напиши только 'Асинхронное программирование'."
            )

        summary_language = (language or "").strip().lower() or "ru"
        duration = DURATION_CONFIG.get(granularity, DURATION_CONFIG["long"])

        prompt = TOPIC_EXTRACTION_PROMPT.format(
            context_line=context_line,
            pauses_instruction=pauses_instruction,
            recording_topic_hint=recording_topic_hint,
            summary_language=summary_language,
            min_topics=min_topics,
            max_topics=max_topics,
            min_spacing_minutes=min_spacing_minutes,
            transcript=transcript,
            **duration,
        )

        try:
            if self.is_fireworks:
                content = await self._fireworks_request(prompt)
            else:
                response = await self.client.chat.completions.create(
                    model=self.config.model,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    **self.config.to_request_params(),
                )
                if not hasattr(response, "choices") or not response.choices:
                    error_msg = f"Unexpected DeepSeek API response format: type={type(response)}, value={response}"
                    logger.error(error_msg)
                    raise ValueError(error_msg)
                content = response.choices[0].message.content.strip()

            if not content:
                return {"main_topics": [], "topic_timestamps": [], "summary": ""}

            logger.info(f"DeepSeek response: length={len(content)} | preview={content[:500]}...")
            logger.debug(f"Full DeepSeek response:\n{content}")

            parsed = self._parse_structured_response(content, total_duration)
            parsed["long_pauses"] = long_pauses
            logger.info(
                f"Parsed result: main_topics={len(parsed.get('main_topics', []))} | "
                f"topic_timestamps={len(parsed.get('topic_timestamps', []))} | total_duration={total_duration}s"
            )

            return parsed

        except Exception as error:
            logger.exception(f"Failed to analyze transcript: error={error}", error=str(error))
            return {"main_topics": [], "topic_timestamps": [], "summary": "", "long_pauses": []}

    async def _fireworks_request(self, prompt: str) -> str:
        """
        Direct HTTP request to Fireworks API with model, max_tokens, top_p, top_k, etc.

        Args:
            prompt: User prompt to send.

        Returns:
            Model response text.
        """
        url = f"{self.base_url}/chat/completions"

        params: dict[str, Any] = {
            "max_tokens": self.config.max_tokens,
            "top_k": self.config.top_k,
            "presence_penalty": self.config.presence_penalty,
            "frequency_penalty": self.config.frequency_penalty,
            "temperature": self.config.temperature,
        }

        if self.config.top_k != 1 and self.config.top_p is not None:
            params["top_p"] = self.config.top_p

        # Fireworks non-stream requests require max_tokens <= 4096
        if params.get("max_tokens", 0) > FIREWORKS_MAX_TOKENS_NON_STREAM:
            logger.warning(
                f"⚠️ max_tokens={params.get('max_tokens')} exceeds Fireworks limit ({FIREWORKS_MAX_TOKENS_NON_STREAM}). "
                f"Reducing to {FIREWORKS_MAX_TOKENS_NON_STREAM}."
            )
            params["max_tokens"] = FIREWORKS_MAX_TOKENS_NON_STREAM

        params = {k: v for k, v in params.items() if v is not None}

        payload = {
            "model": self.config.model,
            "messages": [
                {
                    "role": "system",
                    "content": SYSTEM_PROMPT,
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
            **params,
        }

        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        timeout = httpx.Timeout(self.config.timeout, connect=10.0)

        logger.debug(f"Fireworks API request: url={url} | model={self.config.model} | params={list(params.keys())}")

        async with httpx.AsyncClient(timeout=timeout) as client:
            try:
                response = await client.post(url, json=payload, headers=headers)

                if response.status_code != 200:
                    self._log_api_error(response, url, payload, params)
                    response.raise_for_status()

                data = response.json()

                if "choices" not in data or not data["choices"]:
                    raise ValueError(f"Invalid Fireworks API response format: {data}")

                return data["choices"][0]["message"]["content"].strip()
            except httpx.HTTPStatusError as e:
                if e.response is not None:
                    self._log_http_error(e.response)
                raise

    def _log_api_error(self, response: httpx.Response, url: str, payload: dict, params: dict) -> None:
        """Log Fireworks API error response."""
        try:
            error_text = str(response.json())
        except Exception:
            error_text = response.text

        logger.error(
            f"❌ Fireworks API error (status {response.status_code}):\n"
            f"URL: {url}\n"
            f"Payload keys: {list(payload.keys())}\n"
            f"Params: {params}\n"
            f"Response: {error_text[:2000]}"
        )

    def _log_http_error(self, response: httpx.Response) -> None:
        """Log HTTP error details."""
        try:
            error_data = response.json()
            logger.error(f"Fireworks API error: data={error_data}", error_data=error_data)
        except Exception:
            error_text = response.text
            logger.error(f"Fireworks API error: text={error_text[:1000]}", error_text=error_text[:1000])

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

    def _parse_structured_response(self, text: str, total_duration: float) -> dict[str, Any]:
        """
        Parse LLM response: summary, main topics section, and [HH:MM:SS] - topic lines.

        Returns:
            Dict with summary, main_topics, topic_timestamps (start only; end added later).
        """
        main_topics: list[str] = []
        topic_timestamps: list[dict] = []
        summary = ""

        lines = text.split("\n")

        in_main_topics = False
        in_detailed_topics = False
        in_summary = False
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
                in_detailed_topics = False
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
                in_detailed_topics = True
                continue
            if line.startswith("##"):
                in_main_topics = False
                in_detailed_topics = False
                continue

            timestamp_match = re.match(TIMESTAMP_PATTERN, line)
            if timestamp_match:
                in_detailed_topics = True
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
                continue

            if in_main_topics:
                if not line or line.startswith(("##", "#")):
                    continue

                topic = re.sub(r"^[-*•\d.)]+\s*", "", line).strip()
                topic = re.sub(r"^\[.*?\]\s*", "", topic).strip()

                if topic.startswith("[") and "выведи" in topic.lower():
                    continue

                if topic and len(topic) > 3:
                    words = topic.split()
                    if len(words) > MAIN_TOPIC_MAX_WORDS:
                        topic = " ".join(words[:MAIN_TOPIC_MAX_WORDS]) + "..."
                    elif len(topic) > 150:
                        topic = topic[:150].rsplit(" ", 1)[0] + "..."
                    main_topics.append(topic)

            elif in_detailed_topics:
                match = re.match(TIMESTAMP_PATTERN, line)
                if match:
                    hours_str, minutes_str, seconds_str, topic = match.groups()
                    total_seconds = self._parse_timestamp_to_seconds(
                        hours_str, minutes_str, seconds_str, total_duration
                    )

                    if 0 <= total_seconds <= total_duration:
                        topic_timestamps.append(
                            {
                                "topic": topic.strip(),
                                "start": float(total_seconds),
                            }
                        )
                    else:
                        logger.debug(
                            f"Timestamp skipped (out of range): topic={topic.strip()} | position={total_seconds / 60:.1f}min | range=0-{total_duration / 60:.1f}min",
                            topic=topic.strip(),
                            position_min=round(total_seconds / 60, 1),
                            valid_range=f"0-{round(total_duration / 60, 1)}",
                        )

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
        }

    @staticmethod
    def _process_main_topics(main_topics: list[str]) -> list[str]:
        """Process and normalize main topics."""
        processed = []
        for topic in main_topics[:1]:
            topic = " ".join(topic.split())
            if topic and len(topic) > MAIN_TOPIC_MIN_LENGTH:
                words = topic.split()
                if len(words) > MAIN_TOPIC_MAX_WORDS:
                    topic = " ".join(words[:MAIN_TOPIC_MAX_WORDS]) + "..."
                processed.append(topic)
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
            match = re.match(TIMESTAMP_PATTERN, line)
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
