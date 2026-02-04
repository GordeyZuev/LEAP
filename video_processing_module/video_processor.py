import asyncio
import json
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any

from logger import get_logger

from .audio_detector import AudioDetector
from .config import ProcessingConfig
from .segments import SegmentProcessor, VideoSegment

logger = get_logger()


class VideoProcessor:
    """Video processor for trimming, audio extraction and segmentation."""

    def __init__(self, config: ProcessingConfig):
        self.config = config
        self.segment_processor = SegmentProcessor(config)
        self.audio_detector = AudioDetector(
            silence_threshold=config.silence_threshold,
            min_silence_duration=config.min_silence_duration,
        )
        self._ensure_directories()

    def _ensure_directories(self):
        for directory in [self.config.input_dir, self.config.output_dir, self.config.temp_dir]:
            Path(directory).mkdir(parents=True, exist_ok=True)

    async def get_video_info(self, video_path: str) -> dict[str, Any]:
        """Extract video metadata using ffprobe."""
        cmd = [
            "ffprobe",
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            video_path,
        ]

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                raise RuntimeError(f"FFprobe error: {stderr.decode()}")

            info = json.loads(stdout.decode())
            video_stream = next((s for s in info["streams"] if s["codec_type"] == "video"), None)
            audio_stream = next((s for s in info["streams"] if s["codec_type"] == "audio"), None)

            fps = 0
            if video_stream and "r_frame_rate" in video_stream:
                try:
                    numerator, denominator = map(int, video_stream["r_frame_rate"].split("/"))
                    fps = numerator / denominator if denominator != 0 else 0
                except (ValueError, ZeroDivisionError):
                    fps = 0

            return {
                "duration": float(info["format"]["duration"]),
                "size": int(info["format"]["size"]),
                "width": int(video_stream["width"]) if video_stream else 0,
                "height": int(video_stream["height"]) if video_stream else 0,
                "fps": fps,
                "video_codec": video_stream["codec_name"] if video_stream else None,
                "audio_codec": audio_stream["codec_name"] if audio_stream else None,
                "bitrate": int(info["format"]["bit_rate"]) if "bit_rate" in info["format"] else 0,
            }

        except Exception as e:
            raise RuntimeError(f"Error getting video information: {e}") from e

    async def extract_audio_full(self, video_path: str, output_audio_path: str) -> bool:
        """Extract full audio from video as MP3 (64k, 16kHz mono for transcription)."""
        try:
            cmd = [
                "ffmpeg",
                "-i",
                video_path,
                "-vn",
                "-acodec",
                "libmp3lame",
                "-ab",
                "64k",
                "-ar",
                "16000",
                "-ac",
                "1",
                "-y",
                output_audio_path,
            ]

            process = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )

            await process.wait()

            if process.returncode != 0:
                assert process.stderr is not None, "stderr should be available"
                stderr_output = await process.stderr.read()
                logger.error(f"Audio extraction failed: {stderr_output.decode()[:500]}")
                return False

            if Path(output_audio_path).exists():
                return True

            logger.error(f"Audio file not created: {output_audio_path}")
            return False

        except Exception as e:
            logger.error(f"Audio extraction error: {e}")
            return False

    async def trim_audio(
        self, input_audio_path: str, output_audio_path: str, start_time: float, end_time: float
    ) -> bool:
        """Trim audio using stream copy (fast, no re-encoding)."""
        try:
            duration = end_time - start_time

            cmd = [
                "ffmpeg",
                "-ss",
                str(start_time),
                "-t",
                str(duration),
                "-i",
                input_audio_path,
                "-c",
                "copy",
                "-y",
                output_audio_path,
            ]

            process = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )

            await process.wait()

            if process.returncode != 0:
                assert process.stderr is not None, "stderr should be available"
                stderr_output = await process.stderr.read()
                logger.error(f"Audio trimming failed: {stderr_output.decode()[:500]}")
                return False

            if Path(output_audio_path).exists():
                return True

            logger.error(f"Trimmed audio not created: {output_audio_path}")
            return False

        except Exception as e:
            logger.error(f"Audio trimming error: {e}")
            return False

    async def trim_video(self, input_path: str, output_path: str, start_time: float, end_time: float) -> bool:
        """Trim video to specified time range."""
        duration = end_time - start_time
        input_path = str(input_path)
        output_path = str(output_path)

        cmd = [
            "ffmpeg",
            "-i",
            input_path,
            "-ss",
            str(start_time),
            "-t",
            str(duration),
            "-c:v",
            self.config.video_codec,
            "-c:a",
            self.config.audio_codec,
        ]

        if self.config.video_bitrate != "original":
            cmd.extend(["-b:v", self.config.video_bitrate])
        if self.config.audio_bitrate != "original":
            cmd.extend(["-b:a", self.config.audio_bitrate])
        if self.config.video_codec != "copy" and self.config.fps > 0:
            cmd.extend(["-r", str(self.config.fps)])
        if self.config.resolution != "original":
            cmd.extend(["-s", self.config.resolution])

        cmd.extend(["-y", output_path])

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )

            await process.wait()

            if process.returncode != 0:
                assert process.stderr is not None, "stderr should be available"
                stderr_output = await process.stderr.read()
                logger.error(f"FFmpeg trimming failed: {stderr_output.decode()[:500]}")
                return False

            if Path(output_path).exists():
                return True

            logger.error(f"Trimmed video not created: {output_path}")
            return False

        except Exception as e:
            logger.error(f"Video trimming error: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            return False

    async def process_segment(self, segment: VideoSegment, input_path: str) -> bool:
        """Process single video segment."""
        try:
            Path(segment.output_path).parent.mkdir(parents=True, exist_ok=True)
            success = await self.trim_video(input_path, segment.output_path, segment.start_time, segment.end_time)

            if success:
                segment.processed = True
                segment.processing_time = datetime.now()
                return True
            return False

        except Exception as e:
            logger.error(f"Segment processing failed: {segment.title} - {e}")
            return False

    async def process_video(
        self, video_path: str, title: str, custom_segments: list[tuple] | None = None
    ) -> list[VideoSegment]:
        """Process video into segments."""
        try:
            video_info = await self.get_video_info(video_path)
            duration = video_info["duration"]

            logger.info(
                f"Processing video: {title} | {duration / 60:.1f}min | "
                f"{video_info['size'] / 1024 / 1024:.1f}MB | "
                f"{video_info['width']}x{video_info['height']}"
            )

            if custom_segments:
                segments = self.segment_processor.create_segments_from_timestamps(custom_segments, title)
            else:
                segments = self.segment_processor.create_segments_from_duration(duration, title)

            processed_segments = []
            for segment in segments:
                success = await self.process_segment(segment, video_path)
                if success:
                    processed_segments.append(segment)

            logger.info(f"Completed: {len(processed_segments)}/{len(segments)} segments")
            return processed_segments

        except Exception as e:
            logger.error(f"Video processing failed: {title} - {e}")
            return []
