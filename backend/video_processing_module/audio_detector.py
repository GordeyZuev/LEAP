import asyncio
import json
import math
from pathlib import Path

from logger import get_logger

logger = get_logger()


def _finite_float(value: object, name: str) -> float:
    """Coerce to a finite float so values cannot inject extra FFmpeg filters."""
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{name} must be a finite number")
    return number


class AudioDetector:
    """Audio detector for content boundary detection"""

    def __init__(
        self,
        silence_threshold: float = -30.0,
        min_silence_duration: float = 2.0,
        padding_after: float = 5.0,
    ):
        self.silence_threshold = _finite_float(silence_threshold, "silence_threshold")
        self.min_silence_duration = _finite_float(min_silence_duration, "min_silence_duration")
        self.padding_after = _finite_float(padding_after, "padding_after")

    def _silence_detect_filter(self) -> str:
        return f"silencedetect=noise={self.silence_threshold:.1f}dB:d={self.min_silence_duration:.3f}"

    async def detect_audio_boundaries_from_file(self, audio_path: str) -> tuple[float | None, float | None]:
        """Analyze audio file for silence detection (faster than video analysis)."""
        try:
            audio_file = Path(audio_path)
            if not audio_file.exists():
                logger.error(f"Audio file not found: {audio_path}")
                return None, None

            cmd = [
                "ffmpeg",
                "-threads",
                "1",
                "-i",
                audio_path,
                "-af",
                self._silence_detect_filter(),
                "-f",
                "null",
                "-",
            ]

            process = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )

            _stdout, stderr = await process.communicate()

            if process.returncode != 0:
                error_msg = stderr.decode()
                logger.error(f"FFmpeg audio detection failed: {error_msg}")
                return None, None

            silence_periods, open_silence_start = self._parse_silence_detection(stderr.decode())
            duration = await self._get_duration(audio_path)
            if open_silence_start is not None and duration is not None:
                # Digital / room silence to EOF: FFmpeg emits silence_start and never silence_end.
                silence_periods.append((open_silence_start, duration))

            if not silence_periods:
                return 0.0, None

            first_sound = self._find_first_sound(silence_periods)
            last_sound = self._find_last_sound(silence_periods, duration)
            last_sil = silence_periods[-1]
            last_s = f"{last_sound:.1f}s" if last_sound is not None else "none"
            dur_s = f"{duration:.1f}s" if duration is not None else "none"
            logger.info(
                f"Audio boundaries: {first_sound:.1f}s - {last_s} | "
                f"last_silence={last_sil[0]:.1f}-{last_sil[1]:.1f}s media={dur_s}"
            )
            return first_sound, last_sound

        except Exception as e:
            logger.error(f"Error detecting audio boundaries: {e}")
            return None, None

    def _parse_silence_detection(self, ffmpeg_output: str) -> tuple[list[tuple[float, float]], float | None]:
        """Parse silencedetect lines. Unclosed trailing ``silence_start`` is the second return value."""
        silence_periods: list[tuple[float, float]] = []
        start_time = None

        for line in ffmpeg_output.split("\n"):
            if "silence_start" in line:
                try:
                    start_time = float(line.split("silence_start: ")[1].split()[0])
                except (IndexError, ValueError):
                    continue
            elif "silence_end" in line:
                try:
                    end_time = float(line.split("silence_end: ")[1].split()[0])
                    if start_time is not None:
                        silence_periods.append((start_time, end_time))
                    start_time = None
                except (IndexError, ValueError):
                    continue

        return silence_periods, start_time

    def _find_first_sound(self, silence_periods: list[tuple[float, float]]) -> float:
        """Find time when first sound starts."""
        if not silence_periods:
            return 0.0

        first_silence_start = silence_periods[0][0]
        if first_silence_start > 0.1:
            return 0.0
        return silence_periods[0][1]

    def _find_last_sound(self, silence_periods: list[tuple[float, float]], duration: float | None) -> float | None:
        """Find when speech ends: trailing silence at EOF only, never a mid-file pause.

        A period's ``end`` is when sound resumed (or EOF). It is outro only if
        the leftover after ``end`` is within ``padding_after`` from the template
        (same margin later applied as ``end_trim = last_sound + padding_after``).
        Mid-lecture breaks and pauses with speech after them are not outro.
        Intro is ``_find_first_sound``.
        """
        if not silence_periods or duration is None:
            return None

        chosen_start: float | None = None
        for start, end in silence_periods:
            if start <= 0.1:
                # Leading-only or whole-file silence. Do not cut at 0.
                continue
            gap = max(0.0, duration - end)
            if gap > self.padding_after:
                continue
            chosen_start = start

        if chosen_start is not None:
            return chosen_start
        return duration

    async def get_duration_seconds(self, file_path: str) -> float | None:
        """Media duration in seconds (ffprobe)."""
        return await self._get_duration(file_path)

    async def _get_duration(self, file_path: str) -> float | None:
        """Get media file duration using ffprobe."""
        try:
            cmd = ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", file_path]

            process = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )

            stdout, _stderr = await process.communicate()

            if process.returncode == 0:
                data = json.loads(stdout.decode())
                return float(data["format"]["duration"])

        except Exception as e:
            logger.error(f"Error getting media duration: {e}")

        return None

    async def _validate_video_file(self, video_path: str) -> bool:
        """Validate video file before processing."""
        try:
            video_file = Path(video_path)

            if not video_file.exists():
                logger.error(f"File does not exist: {video_path}")
                return False

            file_size = video_file.stat().st_size
            if file_size < 1024:
                logger.error(f"File too small: {file_size} bytes")
                return False

            with video_file.open("rb") as f:
                first_chunk = f.read(1024)
                if b"<html" in first_chunk.lower() or b"<!doctype html" in first_chunk.lower():
                    logger.error("File is HTML, not video")
                    return False

            cmd = ["ffprobe", "-v", "error", "-show_entries", "format=format_name", "-of", "json", video_path]

            process = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                logger.error(f"ffprobe validation failed: {stderr.decode()}")
                return False

            try:
                data = json.loads(stdout.decode())
                if "format" not in data or "format_name" not in data["format"]:
                    logger.error("File not recognized as video")
                    return False
            except json.JSONDecodeError:
                logger.error("Could not parse ffprobe output")
                return False

            return True

        except Exception as e:
            logger.error(f"Error validating video file: {e}")
            return False
