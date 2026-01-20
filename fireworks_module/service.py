"""Audio transcription service via Fireworks Audio Inference API"""

import asyncio
import json
import re
import time
from collections import Counter
from pathlib import Path
from typing import Any

try:
    from fireworks.client.audio import AudioInference
except ImportError as exc:  # pragma: no cover - среда без зависимости
    raise ImportError(
        "Package 'fireworks-ai' is not installed. Install it with the command "
        "`pip install fireworks-ai` or add it to requirements, "
        "to use Fireworks transcription."
    ) from exc

try:
    import httpx
except ImportError as exc:  # pragma: no cover - среда без зависимости
    raise ImportError(
        "Package 'httpx' is not installed. Install it with the command `pip install httpx` to use Batch API."
    ) from exc


from logger import get_logger

from .config import FireworksConfig

logger = get_logger()


class FireworksTranscriptionService:
    """Asynchronous wrapper over Fireworks AudioInference API."""

    def __init__(self, config: FireworksConfig):
        self.config = config
        self._client = AudioInference(
            model=self.config.model,
            base_url=self.config.base_url,
            api_key=self.config.api_key,
        )

    @staticmethod
    def compose_fireworks_prompt(base_prompt: str | None, recording_topic: str | None) -> str:
        """
        Compose prompt for Fireworks with recording topic.

        Args:
            base_prompt: Base prompt from config (can be None)
            recording_topic: Recording topic (can be None)

        Returns:
            Composed prompt for Fireworks
        """
        base = (base_prompt or "").strip()
        topic = (recording_topic or "").strip()

        if base and topic:
            return f'{base} Topic name: "{topic}". Consider the specifics of this course when recognizing terms.'
        if base:
            return base
        if topic:
            return f'Topic name: "{topic}". Consider the specifics of this course when recognizing terms.'
        return ""

    async def transcribe_audio(
        self,
        audio_path: str,
        language: str | None = None,
        audio_duration: float | None = None,
        prompt: str | None = None,
    ) -> dict[str, Any]:
        """
        Transcription of an audio file through Fireworks.

        Args:
            audio_path: Path to the audio file
            language: Audio language
            audio_duration: Known audio duration (seconds) for logging
        """
        if not Path(audio_path).exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        params = self.config.to_request_params()
        if language:
            params["language"] = language
        if prompt:
            params["prompt"] = prompt

        debug_payload = self._build_request_log(params, audio_path)
        logger.debug(f"Fireworks | Request | {debug_payload}")

        retry_attempts = max(1, self.config.retry_attempts)
        base_delay = max(0.0, self.config.retry_delay)
        max_delay = 60.0  # Maximum delay 60 seconds

        with Path(audio_path).open("rb") as audio_file:
            audio_bytes = audio_file.read()

        last_error: Exception | None = None

        for attempt in range(1, retry_attempts + 1):
            start_time = time.time()
            try:
                logger.info(
                    f"Fireworks | Attempt {attempt}/{retry_attempts} | model={self.config.model} | file={Path(audio_path).name}"
                )

                response = await asyncio.to_thread(
                    self._client.transcribe,
                    audio=audio_bytes,
                    **params,
                )

                elapsed = time.time() - start_time
                logger.info(
                    f"Fireworks | Success: model={self.config.model} | elapsed={elapsed:.1f}s ({elapsed / 60:.1f} min)"
                )

                self._log_raw_response(response)

                # If the response format is SRT or VTT, process as a string
                if self.config.response_format in ("srt", "vtt"):
                    normalized = self._normalize_srt_response(response)
                else:
                    normalized = self._normalize_response(response)
                if audio_duration:
                    ratio = (elapsed / audio_duration) if audio_duration else 0
                    logger.info(
                        f"Fireworks | Speed: audio={audio_duration / 60:.1f} min | proc_ratio={ratio:.2f}x"
                    )

                return normalized

            except Exception as exc:
                last_error = exc
                elapsed = time.time() - start_time
                extra_info = self._format_error_info(exc)
                error_msg = str(exc) if not extra_info else f"{exc} | {extra_info}"
                logger.warning(
                    f"Fireworks | Error: model={self.config.model} | attempt={attempt}/{retry_attempts} | elapsed={elapsed:.1f}s | error={error_msg}"
                )
                debug_payload = self._build_request_log(params, audio_path)
                logger.debug(f"Fireworks | Request | {debug_payload}")

                if attempt < retry_attempts and base_delay > 0:
                    attempt_index = attempt - 1
                    delay = min(base_delay * (2**attempt_index), max_delay)
                    logger.info(
                        f"Fireworks | Retry: delay={delay:.1f}s | next_attempt={attempt + 1}/{retry_attempts}"
                    )
                    await asyncio.sleep(delay)

        raise RuntimeError(f"Error transcribing through Fireworks after {retry_attempts} attempts") from last_error

    def _build_request_log(self, params: dict[str, Any], audio_path: str) -> dict[str, Any]:
        """Uniform body for logging request parameters."""
        safe_params = {k: v for k, v in params.items() if k != "api_key"}
        return {
            "model": self.config.model,
            "base_url": self.config.base_url,
            "file": Path(audio_path).name,
            **safe_params,
        }

    def _format_error_info(self, exc: Exception) -> str:
        """Returns a string with the status code and response body if available."""
        status_code = getattr(exc, "status_code", None)
        response_obj = getattr(exc, "response", None)
        if status_code is None and response_obj is not None:
            status_code = getattr(response_obj, "status_code", None)

        response_body = ""
        if response_obj is not None:
            if getattr(response_obj, "text", None):
                response_body = response_obj.text.strip()
            elif getattr(response_obj, "content", None):
                response_body = str(response_obj.content)
        elif hasattr(exc, "body"):
            response_body = str(exc.body)

        parts: list[str] = []
        if status_code is not None:
            parts.append(f"status_code={status_code}")
        if response_body:
            max_len = 1000
            trimmed = response_body[:max_len]
            if len(response_body) > max_len:
                trimmed += "... (truncated)"
            parts.append(f"response_body={trimmed}")

        return " | ".join(parts)

    def _log_raw_response(self, response: Any) -> None:
        """Logs raw response from Fireworks for debugging."""
        try:
            if hasattr(response, "model_dump"):
                payload = response.model_dump()
            elif hasattr(response, "to_dict"):
                payload = response.to_dict()
            elif isinstance(response, dict):
                payload = response
            else:
                logger.debug("Raw Fireworks response: object without standard serialization methods")
                return

            logger.debug(f"Fireworks response structure: keys={list(payload.keys())}")

            words = payload.get("words", [])
            if isinstance(words, list) and len(words) > 0:
                logger.debug(f"First 10 words from Fireworks response: count={len(words)}")
                for i, word in enumerate(words[:10]):
                    if hasattr(word, "model_dump"):
                        word_dict = word.model_dump()
                    elif hasattr(word, "to_dict"):
                        word_dict = word.to_dict()
                    elif isinstance(word, dict):
                        word_dict = word
                    else:
                        continue

                    word_text = word_dict.get("word") or word_dict.get("text") or ""
                    word_start = word_dict.get("start") or word_dict.get("start_time") or word_dict.get("offset")
                    word_end = word_dict.get("end") or word_dict.get("end_time") or word_dict.get("offset_end")
                    duration = float(word_end) - float(word_start) if word_start and word_end else 0.0

                    logger.debug(
                        f"Word [{i + 1}]: text='{word_text}' | start={word_start} | end={word_end} | duration={duration:.3f}s"
                    )

            segments = payload.get("segments", [])
            if isinstance(segments, list) and len(segments) > 0:
                logger.debug(f"First 5 segments from Fireworks response: total={len(segments)}")
                for i, seg in enumerate(segments[:5]):
                    if hasattr(seg, "model_dump"):
                        seg_dict = seg.model_dump()
                    elif hasattr(seg, "to_dict"):
                        seg_dict = seg.to_dict()
                    elif isinstance(seg, dict):
                        seg_dict = seg
                    else:
                        continue

                    seg_text = seg_dict.get("text") or ""
                    seg_start = seg_dict.get("start") or seg_dict.get("start_time") or seg_dict.get("offset")
                    seg_end = seg_dict.get("end") or seg_dict.get("end_time") or seg_dict.get("offset_end")
                    duration = float(seg_end) - float(seg_start) if seg_start and seg_end else 0.0

                    logger.info(
                        f"   [{i + 1}] '{seg_text[:50]}...': start={seg_start}, end={seg_end}, duration={duration:.3f}s"
                    )

        except Exception as e:
            logger.warning(f"Failed to log raw response: error={e}")

    def _create_segments_from_words(
        self,
        words: list[dict[str, Any]],
        max_duration_seconds: float = 8.0,
        pause_threshold_seconds: float = 0.4,
    ) -> list[dict[str, Any]]:
        """
        Creates segments from words with maximum synchronization accuracy.

        Segmentation priorities (in order of importance):
        1. Sentence end (., !, ?) - always break
        2. Pause > pause_threshold_seconds - mandatory boundary (if group has enough words)
        3. Comma + pause > 0.25s - break into sentence parts (if group has enough words)
        4. Exceeding max_duration_seconds - forced break (if group has enough words)

        Args:
            words: List of dicts with keys 'start', 'end', 'word'
            max_duration_seconds: Maximum segment duration in seconds
            pause_threshold_seconds: Pause threshold for starting new segment in seconds

        Returns:
            List of segments with keys 'id', 'start', 'end', 'text'
        """
        if not words:
            return []

        sentence_endings = (".", "!", "?", "…")
        comma_punctuation = (",",)
        pause_for_comma = 0.25
        min_group_duration_for_pause_break = 0.7
        min_words_for_break = 3
        short_segment_duration = 1.2
        short_segment_words = 3

        segments: list[dict[str, Any]] = []
        current_group: list[dict[str, Any]] = []
        current_start: float | None = None
        segment_id = 0

        def _finalize_segment(group: list[dict[str, Any]], start: float) -> dict[str, Any] | None:
            """Creates segment from word group with precise timestamps."""
            if not group or start is None:
                return None

            group_text = " ".join(w.get("word", "").strip() for w in group)
            if not group_text.strip():
                return None

            group_start = start
            last_word_end_raw = group[-1].get("end", 0.0)
            group_end = float(last_word_end_raw) if isinstance(last_word_end_raw, (int, float)) else 0.0

            if group_end <= group_start:
                group_end = group_start + 0.1

            return {
                "id": segment_id,
                "start": group_start,
                "end": group_end,
                "text": group_text.strip(),
            }

        for _, word_item in enumerate(words):
            word_start = word_item.get("start", 0.0)
            word_end = word_item.get("end", 0.0)
            word_text = word_item.get("word", "").strip()

            if not word_text:
                continue

            word_start_float = float(word_start) if isinstance(word_start, (int, float)) else 0.0
            word_end_float = float(word_end) if isinstance(word_end, (int, float)) else 0.0

            if word_end_float <= word_start_float:
                word_end_float = word_start_float + 0.1

            word_item = {**word_item, "start": word_start_float, "end": word_end_float}

            if current_start is None:
                current_start = word_start_float

            pause_duration = 0.0
            if current_group:
                last_word_end = current_group[-1].get("end", 0.0)
                last_word_end_float = float(last_word_end) if isinstance(last_word_end, (int, float)) else 0.0
                pause_duration = word_start_float - last_word_end_float

            ends_with_sentence = word_text.endswith(sentence_endings)
            ends_with_comma = word_text.endswith(comma_punctuation)

            should_break_sentence = ends_with_sentence
            current_group_duration = (
                (current_group[-1].get("end", 0.0) - current_start)
                if current_group and current_start is not None
                else 0.0
            )
            enough_group = (
                current_group_duration >= min_group_duration_for_pause_break
                or len(current_group) >= min_words_for_break
            )

            should_break_pause = pause_duration > pause_threshold_seconds and enough_group
            should_break_comma = ends_with_comma and pause_duration > pause_for_comma and enough_group

            group_duration_after = word_end_float - current_start
            should_break_duration = group_duration_after > max_duration_seconds and enough_group
            should_break_before = (
                should_break_pause or should_break_comma or should_break_duration
            ) and not should_break_sentence

            if should_break_before and current_group and current_start is not None:
                segment = _finalize_segment(current_group, current_start)
                if segment:
                    segments.append(segment)
                    segment_id += 1

                current_group = []
                current_start = word_start_float

            current_group.append(word_item)

            if should_break_sentence and current_group and current_start is not None:
                segment = _finalize_segment(current_group, current_start)
                if segment:
                    segments.append(segment)
                    segment_id += 1

                current_group = []
                current_start = None

        if current_group and current_start is not None:
            segment = _finalize_segment(current_group, current_start)
            if segment:
                segments.append(segment)

        if not segments:
            return segments

        merged: list[dict[str, Any]] = []

        def seg_word_count(seg: dict[str, Any]) -> int:
            return len(seg.get("text", "").split())

        for seg in segments:
            if (
                seg_word_count(seg) < short_segment_words
                and (seg.get("end", 0.0) - seg.get("start", 0.0)) < short_segment_duration
                and merged
            ):
                prev = merged.pop()
                merged_seg = {
                    "id": prev["id"],
                    "start": prev["start"],
                    "end": seg["end"],
                    "text": f"{prev['text']} {seg['text']}".strip(),
                }
                merged.append(merged_seg)
            else:
                merged.append(seg)

        for idx, seg in enumerate(merged):
            seg["id"] = idx

        return merged

    def _normalize_response(self, response: Any) -> dict[str, Any]:
        """
        Normalizes Fireworks response to Whisper format.

        Returns dict with keys `text`, `segments`, `words`, `language`.
        Segments are created locally from words grouped by sentences and pauses.
        Requires timestamp_granularities to contain 'word' in Fireworks config.
        """
        if response is None:
            raise ValueError("Пустой ответ от Fireworks API")

        if hasattr(response, "model_dump"):
            payload = response.model_dump()  # Pydantic v2
        elif hasattr(response, "to_dict"):
            payload: dict[str, Any] = response.to_dict()  # type: ignore[assignment]
        elif isinstance(response, dict):
            payload = response
        else:
            payload = {}
            for key in ("text", "segments", "language", "words"):
                if hasattr(response, key):
                    payload[key] = getattr(response, key)

        text = payload.get("text") or ""
        language = payload.get("language") or self.config.language

        raw_segments = payload.get("segments", [])
        segments_from_api: list[dict[str, Any]] = []
        if isinstance(raw_segments, list) and len(raw_segments) > 0:
            logger.debug(f"Found {len(raw_segments)} segments in Fireworks response (API)")
            for seg_item in raw_segments:
                if hasattr(seg_item, "model_dump"):
                    seg_dict = seg_item.model_dump()
                elif hasattr(seg_item, "to_dict"):
                    seg_dict = seg_item.to_dict()
                elif isinstance(seg_item, dict):
                    seg_dict = seg_item
                else:
                    continue

                seg_text = seg_dict.get("text") or seg_dict.get("segment") or ""
                seg_start = seg_dict.get("start") or seg_dict.get("start_time") or seg_dict.get("offset")
                seg_end = seg_dict.get("end") or seg_dict.get("end_time") or seg_dict.get("offset_end")

                if not seg_text.strip():
                    continue

                seg_start_float = float(seg_start) if isinstance(seg_start, (int, float)) else 0.0
                seg_end_float = float(seg_end) if isinstance(seg_end, (int, float)) else 0.0
                if seg_end_float <= seg_start_float:
                    seg_end_float = seg_start_float + 0.1

                segments_from_api.append(
                    {
                        "id": len(segments_from_api),
                        "start": seg_start_float,
                        "end": seg_end_float,
                        "text": seg_text.strip(),
                    }
                )

            logger.info(f"Received {len(segments_from_api)} segments from Fireworks API")
        else:
            logger.info("Segments absent in Fireworks response, will build them locally from words")

        all_words: list[dict[str, Any]] = []
        raw_words: list[dict[str, Any]] = []

        if isinstance(payload.get("words"), list):
            raw_words = payload["words"]
            logger.debug(f"First 10 words with full structure from Fireworks: total={len(raw_words)}")
            for i, word_item in enumerate(raw_words[:10]):
                if hasattr(word_item, "model_dump"):
                    word_dict = word_item.model_dump()
                elif hasattr(word_item, "to_dict"):
                    word_dict = word_item.to_dict()
                elif isinstance(word_item, dict):
                    word_dict = word_item
                else:
                    continue

                logger.debug(f"Word [{i + 1}] full structure: {word_dict}")

                word_start = word_dict.get("start") or word_dict.get("start_time") or word_dict.get("offset")
                word_end = word_dict.get("end") or word_dict.get("end_time") or word_dict.get("offset_end")
                word_text = word_dict.get("word") or word_dict.get("text") or ""

                logger.debug(
                    f"Word [{i + 1}]: text='{word_text}' | start={word_start} | end={word_end} | "
                    f"duration={float(word_end) - float(word_start) if word_start and word_end else 0.0:.3f}s"
                )
        else:
            logger.warning(
                "⚠️ Words not found in Fireworks response. Ensure timestamp_granularities contains 'word'."
            )

        word_id = 0
        for word_item in raw_words:
            if hasattr(word_item, "model_dump"):
                word_dict = word_item.model_dump()
            elif hasattr(word_item, "to_dict"):
                word_dict = word_item.to_dict()
            elif isinstance(word_item, dict):
                word_dict = word_item
            else:
                continue

            word_start = word_dict.get("start") or word_dict.get("start_time") or word_dict.get("offset")
            word_end = word_dict.get("end") or word_dict.get("end_time") or word_dict.get("offset_end")
            word_text = word_dict.get("word") or word_dict.get("text") or ""

            if not word_text.strip():
                continue

            word_start_float = float(word_start) if isinstance(word_start, (int, float)) else 0.0
            word_end_float = float(word_end) if isinstance(word_end, (int, float)) else 0.0

            if word_end_float <= word_start_float:
                word_end_float = word_start_float + 0.1

            word_duration = word_end_float - word_start_float

            if word_duration > 3.0:
                logger.debug(
                    f"Long word detected: '{word_text}' | "
                    f"start={word_start_float:.3f}s, end={word_end_float:.3f}s, "
                    f"duration={word_duration:.3f}s"
                )

            all_words.append(
                {
                    "id": word_id,
                    "start": word_start_float,
                    "end": word_end_float,
                    "word": word_text.strip(),
                }
            )
            word_id += 1

        all_words.sort(key=lambda x: x.get("start", 0))

        if all_words:
            durations = [w.get("end", 0) - w.get("start", 0) for w in all_words]
            avg_duration = sum(durations) / len(durations) if durations else 0.0
            max_duration = max(durations) if durations else 0.0
            long_words = [w for w in all_words if (w.get("end", 0) - w.get("start", 0)) > 3.0]

            logger.info(
                f"📊 Words statistics: total={len(all_words)} | avg_duration={avg_duration:.3f}s | max_duration={max_duration:.3f}s | long_words={len(long_words)}"
            )

            if long_words:
                # Log summary on DEBUG level (usually not a problem)
                sample_words = [w.get("word", "")[:20] for w in long_words[:3]]
                logger.debug(
                    f"Found {len(long_words)} abnormally long words (>3s). "
                    f"Sample: {', '.join(sample_words)}... "
                    f"(This is usually fine for technical terms or pauses)"
                )

        segments_auto: list[dict[str, Any]] = []
        if all_words:
            logger.info(f"Creating segments from words: count={len(all_words)} | mode=local")
            segments_auto = self._create_segments_from_words(all_words)
            logger.info(f"Segments created locally: count={len(segments_auto)}")
        else:
            logger.error(
                "Failed to create segments: words=missing | check_config=timestamp_granularities"
            )
            raise ValueError(
                "Failed to extract words from Fireworks response. "
                "Ensure timestamp_granularities contains 'word' in config."
            )

        final_segments = segments_from_api if segments_from_api else segments_auto

        if final_segments:
            start_times = [seg["start"] for seg in final_segments]
            time_counts = Counter(start_times)
            duplicates = {time: count for time, count in time_counts.items() if count > 1}
            if duplicates:
                logger.warning(
                    f"Duplicate timestamps found: unique_times={len(duplicates)} | max_duplicates={max(duplicates.values())}"
                )

        final_segments.sort(key=lambda x: x.get("start", 0))

        logger.info(
            f"Summary: segments={len(final_segments)} (API priority) | words={len(all_words)} | local_segments=saved as backup"
        )

        return {
            "text": text,
            "segments": final_segments,
            "segments_auto": segments_auto,
            "words": all_words,
            "language": language,
        }

    def _parse_srt_time(self, time_str: str) -> float:
        """
        Parses time from SRT format (HH:MM:SS,mmm) to seconds.

        Args:
            time_str: Time string in format HH:MM:SS,mmm or HH:MM:SS.mmm

        Returns:
            Time in seconds (float)
        """
        time_str = time_str.replace(",", ".")

        parts = time_str.split(":")
        if len(parts) != 3:
            return 0.0

        hours = int(parts[0])
        minutes = int(parts[1])
        seconds_parts = parts[2].split(".")
        seconds = int(seconds_parts[0])
        milliseconds = int(seconds_parts[1]) if len(seconds_parts) > 1 else 0

        return hours * 3600 + minutes * 60 + seconds + milliseconds / 1000.0

    def _normalize_srt_response(self, response: Any) -> dict[str, Any]:
        """
        Parses Fireworks response in SRT/VTT format and converts to standard format.

        Args:
            response: Response from Fireworks API (can be string or object)

        Returns:
            Dict with keys `text`, `segments`, `language`, `srt_content`.
        """
        if response is None:
            raise ValueError("Empty response from Fireworks API")

        srt_content = ""
        if isinstance(response, str):
            srt_content = response
        elif hasattr(response, "text"):
            srt_content = response.text
        elif isinstance(response, dict):
            srt_content = response.get("text", "") or response.get("content", "")
        elif hasattr(response, "model_dump"):
            payload = response.model_dump()
            srt_content = payload.get("text", "") or payload.get("content", "")
        elif hasattr(response, "to_dict"):
            payload = response.to_dict()
            srt_content = payload.get("text", "") or payload.get("content", "")

        if not srt_content:
            raise ValueError("Failed to extract SRT content from Fireworks response")

        logger.info(
            f"Parsing SRT response: length={len(srt_content)} chars"
        )

        segments: list[dict[str, Any]] = []
        full_text_parts: list[str] = []

        timestamp_pattern = re.compile(r"(\d{2}):(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2})[,.](\d{3})")

        lines = srt_content.split("\n")
        i = 0
        segment_id = 0

        while i < len(lines):
            line = lines[i].strip()

            if not line or line.isdigit():
                i += 1
                continue

            match = timestamp_pattern.match(line)
            if match:
                start_time_str = f"{match.group(1)}:{match.group(2)}:{match.group(3)}.{match.group(4)}"
                end_time_str = f"{match.group(5)}:{match.group(6)}:{match.group(7)}.{match.group(8)}"

                start_seconds = self._parse_srt_time(start_time_str)
                end_seconds = self._parse_srt_time(end_time_str)

                i += 1
                subtitle_lines = []
                while i < len(lines) and lines[i].strip():
                    subtitle_lines.append(lines[i].strip())
                    i += 1

                subtitle_text = " ".join(subtitle_lines).strip()

                if subtitle_text:
                    segments.append(
                        {
                            "id": segment_id,
                            "start": start_seconds,
                            "end": end_seconds,
                            "text": subtitle_text,
                        }
                    )
                    full_text_parts.append(subtitle_text)
                    segment_id += 1
            else:
                i += 1

        full_text = " ".join(full_text_parts)
        language = self.config.language

        logger.info(
            f"SRT parsing completed: chars={len(full_text)} | segments={len(segments)}"
        )

        return {
            "text": full_text,
            "segments": segments,
            "words": [],
            "language": language,
            "srt_content": srt_content,
        }

    # ==================== Batch API Methods ====================

    async def submit_batch_transcription(
        self,
        audio_path: str,
        language: str | None = None,
        prompt: str | None = None,
    ) -> dict[str, Any]:
        """
        Submits audio for transcription via Fireworks Batch API.

        Batch API is cheaper than synchronous but requires polling for results.
        Docs: https://docs.fireworks.ai/api-reference/create-batch-request

        Args:
            audio_path: Path to audio file
            language: Audio language
            prompt: Prompt for quality improvement

        Returns:
            Dict with batch_id and metadata

        Raises:
            ValueError: If account_id is not configured
            FileNotFoundError: If file not found
        """
        if not self.config.account_id:
            raise ValueError(
                "account_id is not configured. Add account_id in config/fireworks_creds.json "
                "for using Batch API (find in Fireworks dashboard)."
            )

        if not Path(audio_path).exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        endpoint_id = "audio-turbo" if self.config.model == "whisper-v3-turbo" else "audio-prod"

        params = self.config.to_request_params()
        if language:
            params["language"] = language
        if prompt:
            params["prompt"] = prompt

        url = f"{self.config.batch_base_url}/v1/audio/transcriptions"

        logger.info(
            f"Fireworks Batch | Submitting: endpoint={endpoint_id} | file={Path(audio_path).name} | model={self.config.model}",
            endpoint=endpoint_id,
            file=Path(audio_path).name,
            model=self.config.model
        )

        async with httpx.AsyncClient(timeout=60.0) as client:
            with Path(audio_path).open("rb") as audio_file:
                files = {"file": (Path(audio_path).name, audio_file, "audio/mpeg")}

                data = {
                    key: json.dumps(value) if not isinstance(value, str) else value for key, value in params.items()
                }

                response = await client.post(
                    url,
                    params={"endpoint_id": endpoint_id},
                    headers={"Authorization": self.config.api_key},
                    files=files,
                    data=data,
                )

                if response.status_code != 200:
                    error_text = response.text
                    logger.error(
                        f"Fireworks Batch | Submit Error: status={response.status_code} | error={error_text[:500]}",
                        status=response.status_code,
                        error=error_text[:500]
                    )
                    raise RuntimeError(f"Error sending to Batch API: {response.status_code} - {error_text[:200]}")

                result = response.json()
                logger.info(
                    f"Fireworks Batch | Submitted: batch_id={result.get('batch_id')} | status={result.get('status')}"
                )
                return result

    async def check_batch_status(self, batch_id: str) -> dict[str, Any]:
        """
        Checks batch job status.

        Docs: https://docs.fireworks.ai/api-reference/get-batch-status

        Args:
            batch_id: Batch job ID (from submit_batch_transcription)

        Returns:
            Dict with status and optionally body/content_type if completed
        """
        if not self.config.account_id:
            raise ValueError("account_id is not configured for Batch API")

        url = f"{self.config.batch_base_url}/v1/accounts/{self.config.account_id}/batch_job/{batch_id}"

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                url,
                headers={"Authorization": self.config.api_key},
            )

            if response.status_code != 200:
                error_text = response.text
                logger.error(
                    f"Fireworks Batch | Status Check Error: batch_id={batch_id} | status={response.status_code} | error={error_text[:500]}",
                    batch_id=batch_id,
                    status=response.status_code,
                    error=error_text[:500]
                )
                raise RuntimeError(f"Error checking status of Batch API: {response.status_code} - {error_text[:200]}")

            result = response.json()
            status = result.get("status", "unknown")
            logger.debug(f"Fireworks Batch | Status Check: batch_id={batch_id} | status={status}", batch_id=batch_id, status=status)
            return result

    async def get_batch_result(self, batch_id: str) -> dict[str, Any]:
        """
        Gets batch job result (only for completed jobs).

        Args:
            batch_id: Batch job ID

        Returns:
            Normalized result (similar to transcribe_audio)

        Raises:
            RuntimeError: If job not yet completed
        """
        status_response = await self.check_batch_status(batch_id)

        if status_response.get("status") != "completed":
            raise RuntimeError(f"Batch job {batch_id} not yet completed. Status: {status_response.get('status')}")

        body_str = status_response.get("body")
        if not body_str:
            raise RuntimeError(f"Batch job {batch_id} has no result (body is empty)")

        content_type = status_response.get("content_type", "application/json")

        if "json" in content_type:
            result = json.loads(body_str)
            return self._normalize_response(result)
        if "srt" in content_type or "vtt" in content_type:
            return self._normalize_srt_response(body_str)
        try:
            result = json.loads(body_str)
            return self._normalize_response(result)
        except json.JSONDecodeError:
            return {
                "text": body_str,
                "segments": [],
                "words": [],
                "language": self.config.language,
            }

    async def wait_for_batch_completion(
        self,
        batch_id: str,
        poll_interval: float = 10.0,
        max_wait_time: float = 3600.0,
    ) -> dict[str, Any]:
        """
        Waits for batch job completion with polling.

        Args:
            batch_id: Batch job ID
            poll_interval: Check interval in seconds
            max_wait_time: Maximum wait time in seconds

        Returns:
            Normalized transcription result

        Raises:
            TimeoutError: If max_wait_time exceeded
        """
        start_time = time.time()
        attempt = 0

        logger.info(
            f"Fireworks Batch | Waiting: batch_id={batch_id} | poll_interval={poll_interval}s"
        )

        while True:
            attempt += 1
            elapsed = time.time() - start_time

            if elapsed > max_wait_time:
                raise TimeoutError(f"Batch job {batch_id} not completed in {max_wait_time}s (attempts: {attempt})")

            status_response = await self.check_batch_status(batch_id)
            status = status_response.get("status", "unknown")

            if status == "completed":
                logger.info(
                    f"Fireworks Batch | Completed: batch_id={batch_id} | elapsed={elapsed:.1f}s | attempts={attempt}"
                )
                return await self.get_batch_result(batch_id)

            logger.debug(
                f"Fireworks Batch | Polling: batch_id={batch_id} | status={status} | attempt={attempt} | elapsed={elapsed:.1f}s"
            )

            await asyncio.sleep(poll_interval)
