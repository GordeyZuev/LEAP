"""Audio compression and processing"""

import asyncio
import json
from pathlib import Path

from logger import get_logger

logger = get_logger()


class AudioCompressor:
    """Audio compression and file splitting"""

    def __init__(
        self,
        target_bitrate: str = "64k",
        target_sample_rate: int = 16000,
        max_file_size_mb: int = 25,
    ):
        self.target_bitrate = target_bitrate
        self.target_sample_rate = target_sample_rate
        self.max_file_size_mb = max_file_size_mb
        self.max_file_size_bytes = max_file_size_mb * 1024 * 1024

    async def compress_audio(self, input_path: str | Path, output_path: str | Path | None = None) -> str:
        """
        Compress audio to optimal parameters for speech recognition.

        Args:
            input_path: Path to original audio file
            output_path: Path to save compressed file (auto-generated if None)

        Returns:
            Path to compressed file
        """
        input_path = Path(input_path)
        if not input_path.exists():
            raise FileNotFoundError(f"Audio file not found: {input_path}")

        file_size_mb = input_path.stat().st_size / (1024 * 1024)
        logger.info(f"Compressing audio: size={file_size_mb:.2f}MB", size_mb=file_size_mb)

        if output_path is None:
            output_path = input_path.parent / f"{input_path.stem}_compressed.mp3"
        else:
            output_path = Path(output_path)

        output_path.parent.mkdir(parents=True, exist_ok=True)

        cmd = [
            "ffmpeg",
            "-i",
            str(input_path),
            "-vn",
            "-acodec",
            "libmp3lame",
            "-ab",
            self.target_bitrate,
            "-ar",
            str(self.target_sample_rate),
            "-ac",
            "1",
            "-y",
            str(output_path),
        ]

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )

            _stdout, stderr = await process.communicate()

            if process.returncode != 0:
                error_msg = stderr.decode() if stderr else "Unknown error"
                raise RuntimeError(f"FFmpeg compression failed: {error_msg}")

            if not output_path.exists():
                raise RuntimeError(f"Compressed file not created: {output_path}")

            compressed_size_mb = output_path.stat().st_size / (1024 * 1024)
            logger.info(f"Compressed: {file_size_mb:.2f}MB -> {compressed_size_mb:.2f}MB")

            if compressed_size_mb > self.max_file_size_mb:
                logger.warning(
                    f"Exceeds limit: size={compressed_size_mb:.2f}MB | limit={self.max_file_size_mb}MB",
                    size_mb=compressed_size_mb,
                    limit_mb=self.max_file_size_mb
                )

            return str(output_path)

        except Exception as e:
            logger.error(f"Compression failed: {e}")
            raise

    async def get_audio_info(self, audio_path: str | Path) -> dict:
        """Get audio file metadata using ffprobe"""
        cmd = [
            "ffprobe",
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(audio_path),
        ]

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                raise RuntimeError(f"ffprobe failed: {stderr.decode()}")

            info = json.loads(stdout.decode())
            audio_stream = next((s for s in info["streams"] if s["codec_type"] == "audio"), None)

            if not audio_stream:
                raise RuntimeError("No audio stream found")

            return {
                "duration": float(info["format"]["duration"]),
                "size": int(info["format"]["size"]),
                "bitrate": int(info["format"].get("bit_rate", 0)),
                "sample_rate": int(audio_stream.get("sample_rate", 0)),
                "channels": int(audio_stream.get("channels", 0)),
                "codec": audio_stream.get("codec_name", "unknown"),
            }

        except Exception as e:
            logger.error(f"Failed to get audio info: {e}")
            raise

    async def split_audio(
        self, audio_path: str | Path, max_size_mb: float = 20.0, output_dir: str | Path | None = None
    ) -> list[str]:
        """
        Split large audio file into smaller parts for processing.

        Args:
            audio_path: Path to audio file
            max_size_mb: Maximum size per part in MB
            output_dir: Output directory (uses source directory if None)

        Returns:
            List of part file paths
        """
        audio_path = Path(audio_path)
        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        audio_info = await self.get_audio_info(audio_path)
        duration = audio_info["duration"]
        file_size_mb = audio_path.stat().st_size / (1024 * 1024)

        logger.info(f"Splitting: size={file_size_mb:.2f}MB | duration={duration:.1f}s")

        if file_size_mb <= max_size_mb:
            return [str(audio_path)]

        size_per_second = file_size_mb / duration
        duration_per_part = max_size_mb / size_per_second
        num_parts = int(duration / duration_per_part) + (1 if duration % duration_per_part else 0)
        actual_duration_per_part = duration / num_parts

        logger.info(f"Split plan: {num_parts} parts x {actual_duration_per_part:.1f}s")

        if output_dir is None:
            output_dir = audio_path.parent
        else:
            output_dir = Path(output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)

        async def create_part(i: int) -> str:
            start_time = i * actual_duration_per_part
            part_duration = duration - start_time if i == num_parts - 1 else actual_duration_per_part

            part_filename = f"{audio_path.stem}_part_{i + 1:03d}.mp3"
            part_path = output_dir / part_filename

            cmd = [
                "ffmpeg",
                "-i",
                str(audio_path),
                "-ss",
                str(start_time),
                "-t",
                str(part_duration),
                "-vn",
                "-acodec",
                "libmp3lame",
                "-ab",
                self.target_bitrate,
                "-ar",
                str(self.target_sample_rate),
                "-ac",
                "1",
                "-y",
                str(part_path),
            ]

            try:
                process = await asyncio.create_subprocess_exec(
                    *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
                )

                _stdout, stderr = await process.communicate()

                if process.returncode != 0:
                    raise RuntimeError(f"Part {i + 1} creation failed: {stderr.decode()}")

                if not part_path.exists():
                    raise RuntimeError(f"Part {i + 1} not created: {part_path}")

                part_size_mb = part_path.stat().st_size / (1024 * 1024)

                if part_size_mb > self.max_file_size_mb:
                    raise ValueError(
                        f"Part {i + 1} exceeds limit: {part_size_mb:.2f}MB > {self.max_file_size_mb}MB"
                    )

                if part_size_mb > self.max_file_size_mb * 0.95:
                    logger.warning(f"Part {i + 1} near limit: {part_size_mb:.2f}MB")

                return str(part_path)

            except Exception as e:
                logger.error(f"Part {i + 1} failed: {e}")
                raise

        part_tasks = [create_part(i) for i in range(num_parts)]
        part_results = await asyncio.gather(*part_tasks, return_exceptions=True)

        parts = []
        errors = []

        for i, result in enumerate(part_results):
            if isinstance(result, Exception):
                errors.append((i + 1, result))
            else:
                parts.append(result)

        if errors:
            logger.error(f"Split failed: {len(errors)}/{num_parts} parts failed")
            for part in parts:
                try:
                    Path(part).unlink()
                except Exception as e:
                    logger.error(f"Failed to delete part {part}: {e}")
            raise RuntimeError(f"Part creation failed: {errors[0][1]}") from errors[0][1]

        parts.sort()
        logger.info(f"Split complete: {len(parts)} parts")
        return parts
