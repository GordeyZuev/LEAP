"""Audio transcription service via Fireworks Audio Inference API"""

import asyncio
import json
import re
import time
from pathlib import Path
from typing import Any

try:
    from fireworks.client.audio import AudioInference
except ImportError as exc:  # pragma: no cover - environment without dependency
    raise ImportError(
        "Package 'fireworks-ai' is not installed. Install it with the command "
        "`pip install fireworks-ai` or add it to requirements, "
        "to use Fireworks transcription."
    ) from exc

try:
    import httpx
except ImportError as exc:  # pragma: no cover - environment without dependency
    raise ImportError(
        "Package 'httpx' is not installed. Install it with the command `pip install httpx` to use Batch API."
    ) from exc


from logger import get_logger

from .config import FireworksConfig
from .prompts import (
    TRANSCRIPTION_DEFAULT_PROMPT,
    TRANSCRIPTION_TOPIC,
    TRANSCRIPTION_VOCABULARY,
)

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
    def compose_fireworks_prompt(
        base_prompt: str | None,
        recording_topic: str | None,
        vocabulary: list[str] | None = None,
    ) -> str:
        """Compose prompt from base (user), topic, vocabulary. Templates in fireworks_module/prompts.py."""
        base = (base_prompt or "").strip()
        topic = (recording_topic or "").strip()
        vocab = [v.strip() for v in (vocabulary or []) if v and v.strip()]

        if not base and not topic and not vocab:
            return ""

        use_default = not base and (topic or vocab)
        if use_default:
            base = TRANSCRIPTION_DEFAULT_PROMPT.format(topic=topic or "запись")

        if not vocab and (not topic or use_default):
            return base

        parts: list[str] = [base]
        if not use_default and topic:
            parts.append(TRANSCRIPTION_TOPIC.format(topic=topic))
        if vocab:
            vocab_str = ", ".join(vocab[:50])  # Limit to avoid prompt overflow
            parts.append(TRANSCRIPTION_VOCABULARY.format(vocabulary=vocab_str))

        return " ".join(parts).strip()

    async def transcribe_audio(
        self,
        audio_path: str,
        language: str | None = None,
        audio_duration: float | None = None,
        prompt: str | None = None,
    ) -> dict[str, Any]:
        """Transcribe audio file using Fireworks API with retry logic."""
        if not Path(audio_path).exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        params = self.config.to_request_params()
        if language:
            params["language"] = language
        if prompt:
            params["prompt"] = prompt

        retry_attempts = max(1, self.config.retry_attempts)
        base_delay = max(0.0, self.config.retry_delay)
        max_delay = 60.0

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
                logger.info(f"Fireworks | Success: model={self.config.model} | elapsed={elapsed:.1f}s")

                normalized = (
                    self._normalize_srt_response(response)
                    if self.config.response_format in ("srt", "vtt")
                    else self._normalize_response(response)
                )

                if audio_duration:
                    ratio = elapsed / audio_duration
                    logger.info(f"Fireworks | Speed: audio={audio_duration / 60:.1f}m | ratio={ratio:.2f}x")

                return normalized

            except Exception as exc:
                last_error = exc
                elapsed = time.time() - start_time
                error_info = self._format_error_info(exc)
                error_msg = f"{exc} | {error_info}" if error_info else str(exc)
                logger.warning(
                    f"Fireworks | Error: attempt={attempt}/{retry_attempts} | elapsed={elapsed:.1f}s | {error_msg}"
                )

                if attempt < retry_attempts and base_delay > 0:
                    delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
                    logger.info(f"Fireworks | Retry in {delay:.1f}s")
                    await asyncio.sleep(delay)

        raise RuntimeError(f"Transcription failed after {retry_attempts} attempts") from last_error

    def _format_error_info(self, exc: Exception) -> str:
        """Extract status code and response body from exception."""
        status_code = getattr(exc, "status_code", None)
        response_obj = getattr(exc, "response", None)

        if not status_code and response_obj:
            status_code = getattr(response_obj, "status_code", None)

        response_body = ""
        if response_obj:
            response_body = getattr(response_obj, "text", "") or str(getattr(response_obj, "content", ""))
        elif hasattr(exc, "body"):
            response_body = str(exc.body)

        parts: list[str] = []
        if status_code:
            parts.append(f"status={status_code}")
        if response_body:
            max_len = 500
            trimmed = response_body[:max_len].strip()
            if len(response_body) > max_len:
                trimmed += "..."
            parts.append(f"body={trimmed}")

        return " | ".join(parts)

    @staticmethod
    def _build_form_data(params: dict[str, Any]) -> list[tuple[str, Any]]:
        """Convert params dict to multipart form field tuples for httpx files= parameter.

        Lists are expanded as repeated fields with [] suffix (e.g. timestamp_granularities[]).
        Form fields use (None, value) format compatible with httpx multipart encoding.
        """
        items: list[tuple[str, Any]] = []
        for key, value in params.items():
            if isinstance(value, list):
                for item in value:
                    items.append((f"{key}[]", (None, str(item))))
            elif isinstance(value, bool):
                items.append((key, (None, "true" if value else "false")))
            elif isinstance(value, str):
                items.append((key, (None, value)))
            else:
                items.append((key, (None, str(value))))
        return items

    @staticmethod
    def _to_dict(obj: Any) -> dict[str, Any] | None:
        """Convert object to dict using available serialization methods."""
        if hasattr(obj, "model_dump"):
            return obj.model_dump()
        if hasattr(obj, "to_dict"):
            return obj.to_dict()
        if isinstance(obj, dict):
            return obj
        return None

    def _extract_segments_from_payload(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        """Extract and normalize segments from API response."""
        raw_segments = payload.get("segments", [])
        if not isinstance(raw_segments, list) or not raw_segments:
            return []

        segments = []
        for seg_item in raw_segments:
            seg_dict = self._to_dict(seg_item)
            if not seg_dict:
                continue

            seg_text = seg_dict.get("text") or seg_dict.get("segment") or ""
            if not seg_text.strip():
                continue

            seg_start = seg_dict.get("start") or seg_dict.get("start_time") or seg_dict.get("offset") or 0
            seg_end = seg_dict.get("end") or seg_dict.get("end_time") or seg_dict.get("offset_end") or 0

            seg_start_float = float(seg_start) if isinstance(seg_start, (int, float)) else 0.0
            seg_end_float = float(seg_end) if isinstance(seg_end, (int, float)) else 0.0

            if seg_end_float <= seg_start_float:
                seg_end_float = seg_start_float + 0.1

            segments.append(
                {
                    "id": len(segments),
                    "start": seg_start_float,
                    "end": seg_end_float,
                    "text": seg_text.strip(),
                }
            )

        return segments

    def _extract_words_from_payload(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        """Extract and normalize words from API response."""
        raw_words = payload.get("words", [])
        if not isinstance(raw_words, list):
            logger.warning("No words in response. Check timestamp_granularities config")
            return []

        words = []
        for word_item in raw_words:
            word_dict = self._to_dict(word_item)
            if not word_dict:
                continue

            word_text = word_dict.get("word") or word_dict.get("text") or ""
            if not word_text.strip():
                continue

            word_start = word_dict.get("start") or word_dict.get("start_time") or word_dict.get("offset") or 0
            word_end = word_dict.get("end") or word_dict.get("end_time") or word_dict.get("offset_end") or 0

            word_start_float = float(word_start) if isinstance(word_start, (int, float)) else 0.0
            word_end_float = float(word_end) if isinstance(word_end, (int, float)) else 0.0

            if word_end_float <= word_start_float:
                word_end_float = word_start_float + 0.1

            words.append(
                {
                    "id": len(words),
                    "start": word_start_float,
                    "end": word_end_float,
                    "word": word_text.strip(),
                }
            )

        words.sort(key=lambda x: x["start"])
        return words

    def _create_segments_from_words(
        self,
        words: list[dict[str, Any]],
        max_duration_seconds: float = 8.0,
        pause_threshold_seconds: float = 0.4,
    ) -> list[dict[str, Any]]:
        """Create segments from words using sentence boundaries, pauses, and duration limits."""
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
        for seg in segments:
            word_count = len(seg.get("text", "").split())
            duration = seg.get("end", 0.0) - seg.get("start", 0.0)

            if merged and word_count < short_segment_words and duration < short_segment_duration:
                prev = merged.pop()
                merged.append(
                    {
                        "id": prev["id"],
                        "start": prev["start"],
                        "end": seg["end"],
                        "text": f"{prev['text']} {seg['text']}".strip(),
                    }
                )
            else:
                merged.append(seg)

        for idx, seg in enumerate(merged):
            seg["id"] = idx

        return merged

    def _normalize_response(self, response: Any) -> dict[str, Any]:
        """Normalize Fireworks response to Whisper-compatible format."""
        if response is None:
            raise ValueError("Empty response from Fireworks API")

        payload = self._to_dict(response)
        if not payload:
            payload = {
                k: getattr(response, k) for k in ("text", "segments", "language", "words") if hasattr(response, k)
            }

        text = payload.get("text") or ""
        language = payload.get("language") or self.config.language

        segments_from_api = self._extract_segments_from_payload(payload)
        if segments_from_api:
            logger.info(f"Using {len(segments_from_api)} segments from API")
        else:
            logger.info("No API segments, building from words")

        all_words = self._extract_words_from_payload(payload)
        if all_words:
            durations = [w["end"] - w["start"] for w in all_words]
            avg_duration = sum(durations) / len(durations)
            max_duration = max(durations)
            long_words = [w for w in all_words if w["end"] - w["start"] > 3.0]
            logger.info(
                f"Words: total={len(all_words)} | avg={avg_duration:.3f}s | max={max_duration:.3f}s | long={len(long_words)}"
            )

        if not all_words:
            raise ValueError("No words in response. Ensure timestamp_granularities contains 'word'")

        segments_auto = self._create_segments_from_words(all_words)
        logger.info(f"Created {len(segments_auto)} local segments")

        final_segments = segments_from_api or segments_auto
        final_segments.sort(key=lambda x: x.get("start", 0))

        logger.info(f"Final: {len(final_segments)} segments | {len(all_words)} words")

        return {
            "text": text,
            "segments": final_segments,
            "segments_auto": segments_auto,
            "words": all_words,
            "language": language,
        }

    @staticmethod
    def _parse_srt_time(time_str: str) -> float:
        """Parse SRT time format (HH:MM:SS,mmm) to seconds."""
        time_str = time_str.replace(",", ".")
        parts = time_str.split(":")

        if len(parts) != 3:
            return 0.0

        hours, minutes = int(parts[0]), int(parts[1])
        seconds_parts = parts[2].split(".")
        seconds = int(seconds_parts[0])
        milliseconds = int(seconds_parts[1]) if len(seconds_parts) > 1 else 0

        return hours * 3600 + minutes * 60 + seconds + milliseconds / 1000.0

    def _normalize_srt_response(self, response: Any) -> dict[str, Any]:
        """Parse SRT/VTT format response to standard format."""
        if response is None:
            raise ValueError("Empty response from Fireworks API")

        srt_content = self._extract_srt_content(response)
        if not srt_content:
            raise ValueError("Failed to extract SRT content")

        logger.info(f"Parsing SRT: {len(srt_content)} chars")

        segments, full_text_parts = self._parse_srt_segments(srt_content)
        full_text = " ".join(full_text_parts)

        logger.info(f"SRT parsed: {len(full_text)} chars | {len(segments)} segments")

        return {
            "text": full_text,
            "segments": segments,
            "words": [],
            "language": self.config.language,
            "srt_content": srt_content,
        }

    def _extract_srt_content(self, response: Any) -> str:
        """Extract SRT text from response object."""
        if isinstance(response, str):
            return response

        if hasattr(response, "text"):
            return response.text

        payload = self._to_dict(response)
        if payload:
            return payload.get("text", "") or payload.get("content", "")

        return ""

    def _parse_srt_segments(self, srt_content: str) -> tuple[list[dict[str, Any]], list[str]]:
        """Parse SRT content into segments and text parts."""
        segments: list[dict[str, Any]] = []
        text_parts: list[str] = []
        timestamp_pattern = re.compile(r"(\d{2}):(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2})[,.](\d{3})")

        lines = srt_content.split("\n")
        i = 0

        while i < len(lines):
            line = lines[i].strip()

            if not line or line.isdigit():
                i += 1
                continue

            match = timestamp_pattern.match(line)
            if match:
                start_str = f"{match.group(1)}:{match.group(2)}:{match.group(3)}.{match.group(4)}"
                end_str = f"{match.group(5)}:{match.group(6)}:{match.group(7)}.{match.group(8)}"

                start_sec = self._parse_srt_time(start_str)
                end_sec = self._parse_srt_time(end_str)

                i += 1
                subtitle_lines = []
                while i < len(lines) and lines[i].strip():
                    subtitle_lines.append(lines[i].strip())
                    i += 1

                subtitle_text = " ".join(subtitle_lines).strip()
                if subtitle_text:
                    segments.append(
                        {
                            "id": len(segments),
                            "start": start_sec,
                            "end": end_sec,
                            "text": subtitle_text,
                        }
                    )
                    text_parts.append(subtitle_text)
            else:
                i += 1

        return segments, text_parts

    # ==================== Batch API Methods ====================

    async def submit_batch_transcription(
        self,
        audio_path: str,
        language: str | None = None,
        prompt: str | None = None,
    ) -> dict[str, Any]:
        """Submit audio for async Batch API transcription (cheaper but requires polling)."""
        if not self.config.account_id:
            raise ValueError("account_id required for Batch API (find in Fireworks dashboard)")

        if not Path(audio_path).exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        endpoint_id = "audio-turbo" if self.config.model == "whisper-v3-turbo" else "audio-prod"

        params = self.config.to_request_params()
        if language:
            params["language"] = language
        if prompt:
            params["prompt"] = prompt

        url = f"{self.config.batch_base_url}/v1/audio/transcriptions"
        logger.info(f"Batch | Submitting: {Path(audio_path).name} | {endpoint_id}")

        async with httpx.AsyncClient(timeout=60.0) as client:
            with Path(audio_path).open("rb") as audio_file:
                multipart_fields = self._build_form_data(params)
                multipart_fields.append(("file", (Path(audio_path).name, audio_file, "audio/mpeg")))

                response = await client.post(
                    url,
                    params={"endpoint_id": endpoint_id},
                    headers={"Authorization": self.config.api_key},
                    files=multipart_fields,
                )

                if response.status_code != 200:
                    error = response.text[:500]
                    logger.error(f"Batch | Submit Error: {response.status_code} | {error}")
                    raise RuntimeError(f"Batch API error: {response.status_code} - {error}")

                result = response.json()
                logger.info(f"Batch | Submitted: batch_id={result.get('batch_id')}")
                return result

    async def check_batch_status(self, batch_id: str) -> dict[str, Any]:
        """Check batch job status (returns dict with status and optionally result)."""
        if not self.config.account_id:
            raise ValueError("account_id required for Batch API")

        url = f"{self.config.batch_base_url}/v1/accounts/{self.config.account_id}/batch_job/{batch_id}"

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, headers={"Authorization": self.config.api_key})

            if response.status_code != 200:
                error = response.text[:500]
                logger.error(f"Batch | Status Error: {batch_id} | {response.status_code} | {error}")
                raise RuntimeError(f"Batch status check failed: {response.status_code}")

            result = response.json()
            status = result.get("status", "unknown")
            logger.debug(f"Batch | Status: {batch_id} | {status}")
            return result

    async def get_batch_result(
        self,
        batch_id: str,
        status_response: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Get batch job result (only for completed jobs).

        Args:
            batch_id: Batch job ID.
            status_response: Pre-fetched status response to avoid redundant API call.
        """
        if status_response is None:
            status_response = await self.check_batch_status(batch_id)

        if status_response.get("status") != "completed":
            raise RuntimeError(f"Batch {batch_id} not completed: {status_response.get('status')}")

        body_str = status_response.get("body")
        if not body_str:
            raise RuntimeError(f"Batch {batch_id} has no result")

        content_type = status_response.get("content_type", "application/json")

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
