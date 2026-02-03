"""Subtitle generator from transcriptions (SRT and VTT formats)"""

import re
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

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

    def _parse_timestamp_line(self, line: str) -> tuple[timedelta, timedelta, str] | None:
        """Parse a single transcription line with timestamp"""
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

    def parse_transcription_file(self, file_path: str) -> list[SubtitleEntry]:
        """Parse transcription file and return subtitle entries"""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Transcription file not found: {file_path}")

        entries = []
        with path.open(encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue

                try:
                    parsed = self._parse_timestamp_line(line)
                    if parsed:
                        start_time, end_time, text = parsed
                        if text.strip():
                            entries.append(SubtitleEntry(start_time, end_time, text))
                except Exception as e:
                    logger.warning(f"Error parsing line {line_num}: {line[:50]} - {e}")

        return entries

    def parse_words_file(self, file_path: str) -> list[SubtitleEntry]:
        """Parse transcription file with individual words and group them into subtitles"""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Transcription file not found: {file_path}")

        words = []
        with path.open(encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue

                try:
                    parsed = self._parse_timestamp_line(line)
                    if parsed:
                        start_time, end_time, text = parsed
                        if text.strip():
                            words.append({"start": start_time, "end": end_time, "text": text.strip()})
                except (ValueError, IndexError) as e:
                    logger.warning(f"Error parsing line {line_num}: {line[:50]} - {e}")

        if not words:
            raise ValueError(f"No words extracted from {file_path}")

        logger.info(f"Parsed {len(words)} words from {file_path}")
        return self._group_words_into_subtitles(words)

    def _group_words_into_subtitles(
        self,
        words: list[dict],
        max_duration_seconds: float | None = None,
        pause_threshold_seconds: float | None = None,
    ) -> list[SubtitleEntry]:
        """Group words into subtitles based on duration and pauses between words"""
        if not words:
            return []

        max_duration = max_duration_seconds or self.MAX_SUBTITLE_DURATION
        pause_threshold = pause_threshold_seconds or self.PAUSE_THRESHOLD

        entries = []
        current_group = []
        current_start = None

        for word in words:
            word_start = word["start"]
            word_end = word["end"]

            if current_start is None:
                current_start = word_start

            should_start_new = False

            if current_group:
                pause_duration = (word_start - current_group[-1]["end"]).total_seconds()
                if pause_duration > pause_threshold:
                    should_start_new = True

            if not should_start_new and (word_end - current_start).total_seconds() > max_duration:
                should_start_new = True

            if should_start_new and current_group:
                text = " ".join(w["text"] for w in current_group)
                entries.append(SubtitleEntry(current_start, current_group[-1]["end"], text))
                current_group = [word]
                current_start = word_start
            else:
                current_group.append(word)

        if current_group:
            text = " ".join(w["text"] for w in current_group)
            entries.append(SubtitleEntry(current_start, current_group[-1]["end"], text))

        return entries

    def _format_timedelta(self, td: timedelta, separator: str = ",") -> str:
        """Format timedelta as HH:MM:SS{separator}mmm"""
        total_seconds = int(td.total_seconds())
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        milliseconds = int(td.microseconds / 1000)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}{separator}{milliseconds:03d}"

    def _format_timedelta_srt(self, td: timedelta) -> str:
        """Format timedelta in SRT format: HH:MM:SS,mmm"""
        return self._format_timedelta(td, ",")

    def _format_timedelta_vtt(self, td: timedelta) -> str:
        """Format timedelta in VTT format: HH:MM:SS.mmm"""
        return self._format_timedelta(td, ".")

    def _split_text(self, text: str) -> list[str]:
        """Split text into lines respecting max_chars_per_line and max_lines"""
        words = text.split()
        lines = []
        current_line = []
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

    def generate_srt(self, entries: list[SubtitleEntry], output_path: str) -> str:
        """Generate subtitle file in SRT format"""
        with Path(output_path).open("w", encoding="utf-8") as f:
            for index, entry in enumerate(entries, start=1):
                f.write(f"{index}\n")
                start_str = self._format_timedelta_srt(entry.start_time)
                end_str = self._format_timedelta_srt(entry.end_time)
                f.write(f"{start_str} --> {end_str}\n")
                
                for line in self._split_text(entry.text):
                    f.write(f"{line}\n")
                f.write("\n")

        return output_path

    def generate_vtt(self, entries: list[SubtitleEntry], output_path: str) -> str:
        """Generate subtitle file in VTT format"""
        with Path(output_path).open("w", encoding="utf-8") as f:
            f.write("WEBVTT\n\n")

            for entry in entries:
                start_str = self._format_timedelta_vtt(entry.start_time)
                end_str = self._format_timedelta_vtt(entry.end_time)
                f.write(f"{start_str} --> {end_str}\n")
                
                for line in self._split_text(entry.text):
                    f.write(f"{line}\n")
                f.write("\n")

        return output_path

    def generate_from_transcription(
        self, transcription_path: str, output_dir: str | None = None, formats: list[str] | None = None
    ) -> dict[str, str]:
        """Generate subtitles from transcription file (expects segments.txt)"""
        formats = formats or ["srt", "vtt"]
        trans_path = Path(transcription_path)
        output_dir = Path(output_dir) if output_dir else trans_path.parent
        output_dir.mkdir(parents=True, exist_ok=True)

        if trans_path.is_dir():
            segments_path = trans_path / "segments.txt"
            if not segments_path.exists():
                raise FileNotFoundError(f"No segments.txt in folder: {transcription_path}")
            trans_path = segments_path
        elif trans_path.name != "segments.txt":
            raise FileNotFoundError(f"Expected segments.txt, got: {transcription_path}")

        logger.info(f"Generating subtitles from {trans_path}")
        entries = self.parse_transcription_file(str(trans_path))

        if not entries:
            raise ValueError(f"No entries extracted from {transcription_path}")

        result = {}
        base_name = "subtitles"

        if "srt" in formats:
            srt_path = output_dir / f"{base_name}.srt"
            self.generate_srt(entries, str(srt_path))
            result["srt"] = str(srt_path)

        if "vtt" in formats:
            vtt_path = output_dir / f"{base_name}.vtt"
            self.generate_vtt(entries, str(vtt_path))
            result["vtt"] = str(vtt_path)

        return result
