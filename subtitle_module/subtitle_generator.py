"""Subtitle generator from transcriptions (SRT and VTT formats)"""

import re
from datetime import timedelta
from pathlib import Path

from logger import get_logger

logger = get_logger()


class SubtitleEntry:
    """Single subtitle entry"""

    def __init__(self, start_time: timedelta, end_time: timedelta, text: str):
        self.start_time = start_time
        self.end_time = end_time
        self.text = text.strip()

    def __repr__(self) -> str:
        return f"SubtitleEntry({self.start_time} -> {self.end_time}: {self.text[:50]}...)"


class SubtitleGenerator:
    """Generate subtitles from transcription files"""

    # Regular expression for parsing timestamp: [HH:MM:SS - HH:MM:SS]
    TIMESTAMP_PATTERN = re.compile(r"\[(\d{2}):(\d{2}):(\d{2})\s*-\s*(\d{2}):(\d{2}):(\d{2})\]\s*(.*)")

    # Regular expression for parsing timestamp with milliseconds: [HH:MM:SS.mmm - HH:MM:SS.mmm]
    TIMESTAMP_PATTERN_MS = re.compile(
        r"\[(\d{2}):(\d{2}):(\d{2})\.(\d{3})\s*-\s*(\d{2}):(\d{2}):(\d{2})\.(\d{3})\]\s*(.*)"
    )

    # Regular expression for parsing words with milliseconds (legacy)
    WORDS_TIMESTAMP_PATTERN = re.compile(
        r"\[(\d{2}):(\d{2}):(\d{2})\.(\d{3})\s*-\s*(\d{2}):(\d{2}):(\d{2})\.(\d{3})\]\s*(.*)"
    )

    def __init__(self, max_chars_per_line: int = 42, max_lines: int = 2):
        """
        Args:
            max_chars_per_line: Maximum number of characters in a subtitle line
            max_lines: Maximum number of lines in a subtitle
        """
        self.max_chars_per_line = max_chars_per_line
        self.max_lines = max_lines

    def parse_transcription_file(self, file_path: str) -> list[SubtitleEntry]:
        """
        Parses a transcription file and returns a list of subtitle entries.

        Args:
            file_path: Path to the transcription file

        Returns:
            List of SubtitleEntry objects
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Transcription file not found: {file_path}")

        entries = []

        with path.open(encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue

                match_ms = self.TIMESTAMP_PATTERN_MS.match(line)
                match_s = self.TIMESTAMP_PATTERN.match(line) if not match_ms else None

                if match_ms or match_s:
                    try:
                        if match_ms:
                            start_h, start_m, start_s, start_ms = map(int, match_ms.groups()[:4])
                            end_h, end_m, end_s, end_ms = map(int, match_ms.groups()[4:8])
                            text = match_ms.groups()[8]
                            start_time = timedelta(
                                hours=start_h, minutes=start_m, seconds=start_s, milliseconds=start_ms
                            )
                            end_time = timedelta(hours=end_h, minutes=end_m, seconds=end_s, milliseconds=end_ms)
                        else:
                            start_h, start_m, start_s = map(int, match_s.groups()[:3])
                            end_h, end_m, end_s = map(int, match_s.groups()[3:6])
                            text = match_s.groups()[6]
                            start_time = timedelta(hours=start_h, minutes=start_m, seconds=start_s)
                            end_time = timedelta(hours=end_h, minutes=end_m, seconds=end_s)

                    except Exception as e:
                        logger.warning(f"Error parsing line {line_num} in file {file_path}: {line[:50]}... - {e}")
                        continue

                    if text.strip():
                        entries.append(SubtitleEntry(start_time, end_time, text))
        return entries

    def parse_words_file(self, file_path: str) -> list[SubtitleEntry]:
        """
        Parses a transcription file with words and groups them into subtitles.

        Args:
            file_path: Path to the transcription file with words

        Returns:
            List of SubtitleEntry objects (grouped words)
        """
        if not Path(file_path).exists():
            raise FileNotFoundError(f"Transcription file not found: {file_path}")

        words = []
        total_lines = 0
        parsed_lines = 0

        logger.info(f"Parsing words file: path={file_path}", path=file_path)

        with Path(file_path).open(encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                total_lines += 1
                line = line.strip()
                if not line:
                    continue

                match = self.WORDS_TIMESTAMP_PATTERN.match(line)
                if match:
                    try:
                        # Extract timestamp with milliseconds
                        start_h, start_m, start_s, start_ms = map(int, match.groups()[:4])
                        end_h, end_m, end_s, end_ms = map(int, match.groups()[4:8])
                        word_text = match.groups()[8]

                        if word_text.strip():
                            # Create timedelta objects with milliseconds
                            start_time = timedelta(
                                hours=start_h, minutes=start_m, seconds=start_s, milliseconds=start_ms
                            )
                            end_time = timedelta(hours=end_h, minutes=end_m, seconds=end_s, milliseconds=end_ms)

                            words.append(
                                {
                                    "start": start_time,
                                    "end": end_time,
                                    "text": word_text.strip(),
                                }
                            )
                            parsed_lines += 1
                    except (ValueError, IndexError) as e:
                        logger.warning(
                            f"⚠️ Error parsing line: line_num={line_num} | file={file_path} | preview={line[:50]}...",
                            line_num=line_num,
                            file=file_path,
                            error=str(e)
                        )
                        continue
                # Log only the first few unrecognized lines to avoid clogging the log
                elif line_num <= 5:
                    logger.debug(
                        f"Line doesn't match format: line_num={line_num} | preview={line[:50]}... | file={file_path}",
                        line_num=line_num,
                        file=file_path
                    )

        logger.info(
            f"📊 Parsing completed: processed={total_lines} lines | parsed={parsed_lines} words",
            processed_lines=total_lines,
            parsed_words=parsed_lines
        )

        if not words:
            raise ValueError(f"Unable to extract words from file {file_path}. File is empty or has invalid format.")

        logger.info(f"Grouping words into subtitles: words={len(words)}", words=len(words))
        # Group words into subtitles
        entries = self._group_words_into_subtitles(words)
        logger.info(
            f"Created subtitles: entries={len(entries)} | words={len(words)}",
            entries=len(entries),
            words=len(words)
        )

        return entries

    def _group_words_into_subtitles(
        self, words: list[dict], max_duration_seconds: float = 5.0, pause_threshold_seconds: float = 0.5
    ) -> list[SubtitleEntry]:
        """
        Groups words into subtitles based on time and pauses.

        Args:
            words: List of dictionaries with keys 'start', 'end', 'text' (timedelta)
            max_duration_seconds: Maximum duration of a subtitle in seconds
            pause_threshold_seconds: Pause threshold for starting a new subtitle (seconds)

        Returns:
            List of SubtitleEntry objects
        """
        if not words:
            return []

        entries = []
        current_group = []
        current_start = None

        for word in words:
            word_start = word["start"]
            word_end = word["end"]

            # Determine the start of the group
            if current_start is None:
                current_start = word_start

            # Check if a new group should be started
            should_start_new = False

            # Check 1: Pause between words is greater than the threshold
            if current_group:
                last_word_end = current_group[-1]["end"]
                pause_duration = (word_start - last_word_end).total_seconds()
                if pause_duration > pause_threshold_seconds:
                    should_start_new = True

            # Check 2: Duration of the current group exceeds the maximum
            if not should_start_new:
                group_duration = (word_end - current_start).total_seconds()
                if group_duration > max_duration_seconds:
                    should_start_new = True

            # If a new group should be started, save the current group
            if should_start_new and current_group:
                # Form text from words of the current group
                group_text = " ".join(w["text"] for w in current_group)
                group_start = current_start
                group_end = current_group[-1]["end"]

                entries.append(SubtitleEntry(group_start, group_end, group_text))

                # Start a new group
                current_group = [word]
                current_start = word_start
            else:
                # Add word to the current group
                current_group.append(word)

        # Add the last group
        if current_group:
            group_text = " ".join(w["text"] for w in current_group)
            group_start = current_start
            group_end = current_group[-1]["end"]
            entries.append(SubtitleEntry(group_start, group_end, group_text))

        return entries

    def _format_timedelta_srt(self, td: timedelta) -> str:
        """Formats timedelta in SRT format: HH:MM:SS,mmm"""
        total_seconds = int(td.total_seconds())
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        milliseconds = int(td.microseconds / 1000)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"

    def _format_timedelta_vtt(self, td: timedelta) -> str:
        """Formats timedelta in VTT format: HH:MM:SS.mmm"""
        total_seconds = int(td.total_seconds())
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        milliseconds = int(td.microseconds / 1000)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{milliseconds:03d}"

    def _split_text(self, text: str) -> list[str]:
        """
        Splits text into lines with the maximum length.
        """
        words = text.split()
        lines = []
        current_line = []
        current_length = 0

        for word in words:
            word_length = len(word)

            # If adding a word exceeds the limit, start a new line
            if current_length + word_length + (1 if current_line else 0) > self.max_chars_per_line:
                if current_line:
                    lines.append(" ".join(current_line))
                    current_line = []
                    current_length = 0

                # If the maximum number of lines is reached, stop
                if len(lines) >= self.max_lines:
                    break

            current_line.append(word)
            current_length += word_length + (1 if len(current_line) > 1 else 0)

        # Add remaining words
        if current_line and len(lines) < self.max_lines:
            lines.append(" ".join(current_line))

        return lines if lines else [text[: self.max_chars_per_line]]

    def generate_srt(self, entries: list[SubtitleEntry], output_path: str) -> str:
        """
        Generates a subtitle file in SRT format.
        """
        with Path(output_path).open("w", encoding="utf-8") as f:
            for index, entry in enumerate(entries, start=1):
                # Subtitle number
                f.write(f"{index}\n")

                # Timestamp
                start_str = self._format_timedelta_srt(entry.start_time)
                end_str = self._format_timedelta_srt(entry.end_time)
                f.write(f"{start_str} --> {end_str}\n")

                # Text (split into lines)
                lines = self._split_text(entry.text)
                for line in lines:
                    f.write(f"{line}\n")

                # Empty line between subtitles
                f.write("\n")

        return output_path

    def generate_vtt(self, entries: list[SubtitleEntry], output_path: str) -> str:
        """
        Generates a subtitle file in VTT format.
        """
        with Path(output_path).open("w", encoding="utf-8") as f:
            # VTT header
            f.write("WEBVTT\n\n")

            for entry in entries:
                # Timestamp
                start_str = self._format_timedelta_vtt(entry.start_time)
                end_str = self._format_timedelta_vtt(entry.end_time)
                f.write(f"{start_str} --> {end_str}\n")

                # Text (split into lines)
                lines = self._split_text(entry.text)
                for line in lines:
                    f.write(f"{line}\n")

                # Empty line between subtitles
                f.write("\n")

        return output_path

    def generate_from_transcription(
        self, transcription_path: str, output_dir: str | None = None, formats: list[str] | None = None
    ) -> dict[str, str]:
        """
        Generates subtitles from a transcription file.
        Expected ready segments.txt (with ms); other formats are not used.
        """
        if formats is None:
            formats = ["srt", "vtt"]

        trans_path = Path(transcription_path)
        if output_dir is None:
            output_dir = trans_path.parent

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        entries = []
        base_name = "subtitles"

        if trans_path.is_dir():
            segments_path = trans_path / "segments.txt"
            if segments_path.exists():
                logger.info(f"Using segments.txt: path={segments_path}", path=str(segments_path))
                entries = self.parse_transcription_file(str(segments_path))
            else:
                raise FileNotFoundError(f"No segments.txt in the folder: {transcription_path}")
        elif trans_path.name == "segments.txt":
            logger.info(f"Using segments.txt: path={transcription_path}", path=transcription_path)
            entries = self.parse_transcription_file(transcription_path)
        else:
            raise FileNotFoundError(f"Expected segments.txt or a folder with segments.txt, got: {transcription_path}")

        if not entries:
            raise ValueError(f"Unable to extract records from transcription file: {transcription_path}")

        result = {}

        if "srt" in formats:
            srt_path = output_dir / f"{base_name}.srt"
            self.generate_srt(entries, str(srt_path))
            result["srt"] = str(srt_path)

        if "vtt" in formats:
            vtt_path = output_dir / f"{base_name}.vtt"
            self.generate_vtt(entries, str(vtt_path))
            result["vtt"] = str(vtt_path)

        return result
