"""Subtitle generator from transcriptions (SRT and VTT formats).

Reads ``segments.txt`` and writes ``subtitles.srt``/``subtitles.vtt`` through the
storage backend. All entries live entirely in-memory (subtitle files are small)
so no temp files are required.
"""

import io
import re
from dataclasses import dataclass
from datetime import timedelta

from file_storage.factory import get_storage_backend
from logger import get_logger

logger = get_logger()


@dataclass
class SubtitleEntry:
    """Single subtitle entry with start/end timestamps and text"""

    start_time: timedelta
    end_time: timedelta
    text: str

    def __post_init__(self):
        self.text = self.text.strip()


class SubtitleGenerator:
    """Generate subtitles from transcription files in SRT and VTT formats"""

    TIMESTAMP_PATTERN = re.compile(r"\[(\d{2}):(\d{2}):(\d{2})\s*-\s*(\d{2}):(\d{2}):(\d{2})\]\s*(.*)")
    TIMESTAMP_PATTERN_MS = re.compile(
        r"\[(\d{2}):(\d{2}):(\d{2})\.(\d{3})\s*-\s*(\d{2}):(\d{2}):(\d{2})\.(\d{3})\]\s*(.*)"
    )

    MAX_SUBTITLE_DURATION = 5.0
    PAUSE_THRESHOLD = 0.5

    def __init__(self, max_chars_per_line: int = 42, max_lines: int = 2):
        self.max_chars_per_line = max_chars_per_line
        self.max_lines = max_lines

    # ------------------------------------------------------------------ parsing
    def _parse_timestamp_line(self, line: str) -> tuple[timedelta, timedelta, str] | None:
        """Parse a single transcription line with timestamp."""
        match_ms = self.TIMESTAMP_PATTERN_MS.match(line)
        if match_ms:
            groups = match_ms.groups()
            start_time = timedelta(
                hours=int(groups[0]),
                minutes=int(groups[1]),
                seconds=int(groups[2]),
                milliseconds=int(groups[3]),
            )
            end_time = timedelta(
                hours=int(groups[4]),
                minutes=int(groups[5]),
                seconds=int(groups[6]),
                milliseconds=int(groups[7]),
            )
            return start_time, end_time, groups[8]

        match_s = self.TIMESTAMP_PATTERN.match(line)
        if match_s:
            groups = match_s.groups()
            start_time = timedelta(hours=int(groups[0]), minutes=int(groups[1]), seconds=int(groups[2]))
            end_time = timedelta(hours=int(groups[3]), minutes=int(groups[4]), seconds=int(groups[5]))
            return start_time, end_time, groups[6]

        return None

    def _parse_segments_text(self, text: str) -> list[SubtitleEntry]:
        """Parse the contents of segments.txt into SubtitleEntry objects."""
        entries: list[SubtitleEntry] = []
        for line_num, raw in enumerate(text.splitlines(), start=1):
            line = raw.strip()
            if not line:
                continue
            try:
                parsed = self._parse_timestamp_line(line)
                if parsed:
                    start_time, end_time, body = parsed
                    if body.strip():
                        entries.append(SubtitleEntry(start_time, end_time, body))
            except Exception as e:
                logger.warning(f"Error parsing line {line_num}: {line[:50]} - {e}")
        return entries

    # ----------------------------------------------------------------- format
    def _format_timedelta(self, td: timedelta, separator: str = ",") -> str:
        """Format timedelta as HH:MM:SS{separator}mmm"""
        total_seconds = int(td.total_seconds())
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        milliseconds = int(td.microseconds / 1000)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}{separator}{milliseconds:03d}"

    def _format_timedelta_srt(self, td: timedelta) -> str:
        return self._format_timedelta(td, ",")

    def _format_timedelta_vtt(self, td: timedelta) -> str:
        return self._format_timedelta(td, ".")

    def _split_text(self, text: str) -> list[str]:
        """Split text into lines respecting max_chars_per_line and max_lines."""
        words = text.split()
        lines: list[str] = []
        current_line: list[str] = []
        current_length = 0

        for word in words:
            word_length = len(word)
            space_needed = 1 if current_line else 0

            if current_length + word_length + space_needed > self.max_chars_per_line:
                if current_line:
                    lines.append(" ".join(current_line))
                    if len(lines) >= self.max_lines:
                        break
                    current_line = []
                    current_length = 0

            current_line.append(word)
            current_length += word_length + (1 if len(current_line) > 1 else 0)

        if current_line and len(lines) < self.max_lines:
            lines.append(" ".join(current_line))

        return lines if lines else [text[: self.max_chars_per_line]]

    def _render_srt(self, entries: list[SubtitleEntry]) -> str:
        """Build SRT body in memory."""
        buf = io.StringIO()
        for index, entry in enumerate(entries, start=1):
            buf.write(f"{index}\n")
            buf.write(
                f"{self._format_timedelta_srt(entry.start_time)} --> {self._format_timedelta_srt(entry.end_time)}\n"
            )
            for line in self._split_text(entry.text):
                buf.write(f"{line}\n")
            buf.write("\n")
        return buf.getvalue()

    def _render_vtt(self, entries: list[SubtitleEntry]) -> str:
        """Build VTT body in memory."""
        buf = io.StringIO()
        buf.write("WEBVTT\n\n")
        for entry in entries:
            buf.write(
                f"{self._format_timedelta_vtt(entry.start_time)} --> {self._format_timedelta_vtt(entry.end_time)}\n"
            )
            for line in self._split_text(entry.text):
                buf.write(f"{line}\n")
            buf.write("\n")
        return buf.getvalue()

    # ------------------------------------------------------------------- main
    async def generate_from_transcription(
        self,
        transcription_key: str,
        output_dir_key: str,
        formats: list[str] | None = None,
    ) -> dict[str, str]:
        """Generate subtitles from a ``segments.txt`` key in storage.

        Args:
            transcription_key: Storage key of the ``segments.txt`` (e.g.
                ``users/000001/recordings/42/transcriptions/cache/segments.txt``).
            output_dir_key: Storage key prefix where subtitle files will be written.
            formats: Subset of ``{"srt", "vtt"}``. Defaults to both.

        Returns:
            ``{"srt": "<key>", "vtt": "<key>"}`` for the formats actually generated.
        """
        formats = formats or ["srt", "vtt"]
        storage = get_storage_backend()

        if not await storage.exists(transcription_key):
            raise FileNotFoundError(f"segments.txt not found in storage: {transcription_key}")

        segments_text = (await storage.load(transcription_key)).decode("utf-8")
        entries = self._parse_segments_text(segments_text)
        if not entries:
            raise ValueError(f"No entries extracted from {transcription_key}")

        logger.info(f"Generating subtitles from {transcription_key} | formats={formats}")
        result: dict[str, str] = {}
        prefix = output_dir_key.rstrip("/")

        if "srt" in formats:
            key = f"{prefix}/subtitles.srt"
            await storage.save(key, self._render_srt(entries).encode("utf-8"))
            result["srt"] = key

        if "vtt" in formats:
            key = f"{prefix}/subtitles.vtt"
            await storage.save(key, self._render_vtt(entries).encode("utf-8"))
            result["vtt"] = key

        return result
