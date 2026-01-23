import asyncio
import json
import shutil
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
    """Video processor for trimming and post-processing"""

    def __init__(self, config: ProcessingConfig):
        self.config = config
        self.segment_processor = SegmentProcessor(config)
        self.audio_detector = AudioDetector(
            silence_threshold=config.silence_threshold,
            min_silence_duration=config.min_silence_duration,
        )
        self._ensure_directories()

    def _ensure_directories(self):
        """Create necessary directories."""
        for directory in [self.config.input_dir, self.config.output_dir, self.config.temp_dir]:
            Path(directory).mkdir(parents=True, exist_ok=True)


    async def get_video_info(self, video_path: str) -> dict[str, Any]:
        """Get video information."""
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

            # Calculate FPS from r_frame_rate (e.g., "30/1" or "60000/1001")
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
        """
        Extract full audio from video in MP3 format.

        Format: 64k bitrate, 16kHz sample rate, mono (optimized for transcription).
        """
        try:
            cmd = [
                "ffmpeg",
                "-i", video_path,
                "-vn",
                "-acodec", "libmp3lame",
                "-ab", "64k",
                "-ar", "16000",
                "-ac", "1",
                "-y",
                output_audio_path,
            ]

            logger.info(f"Extracting audio: {video_path} -> {output_audio_path}")

            process = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )

            await process.wait()

            if process.returncode != 0:
                stderr_output = await process.stderr.read()
                logger.error(f"Audio extraction failed: {stderr_output.decode()[:500]}")
                return False

            if Path(output_audio_path).exists():
                file_size = Path(output_audio_path).stat().st_size
                logger.info(f"Audio extracted: {output_audio_path} ({file_size / 1024:.1f} KB)")
                return True

            logger.error(f"Audio file not created: {output_audio_path}")
            return False

        except Exception as e:
            logger.error(f"Exception during audio extraction: {e}")
            return False

    async def trim_audio(
        self, input_audio_path: str, output_audio_path: str, start_time: float, end_time: float
    ) -> bool:
        """
        Trim audio file using stream copy (no re-encoding, instant).

        Args:
            input_audio_path: Path to full audio file
            output_audio_path: Path to save trimmed audio
            start_time: Start time in seconds
            end_time: End time in seconds
        """
        try:
            duration = end_time - start_time

            cmd = [
                "ffmpeg",
                "-ss", str(start_time),
                "-t", str(duration),
                "-i", input_audio_path,
                "-c", "copy",
                "-y",
                output_audio_path,
            ]

            logger.info(f"Trimming audio: {start_time:.1f}s - {end_time:.1f}s")

            process = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )

            await process.wait()

            if process.returncode != 0:
                stderr_output = await process.stderr.read()
                logger.error(f"Audio trimming failed: {stderr_output.decode()[:500]}")
                return False

            if Path(output_audio_path).exists():
                file_size = Path(output_audio_path).stat().st_size
                logger.info(f"Audio trimmed: {output_audio_path} ({file_size / 1024:.1f} KB)")
                return True

            logger.error(f"Trimmed audio not created: {output_audio_path}")
            return False

        except Exception as e:
            logger.error(f"Exception during audio trimming: {e}")
            return False

    async def trim_video(self, input_path: str, output_path: str, start_time: float, end_time: float) -> bool:
        """Trim video by time."""
        duration = end_time - start_time

        # Ensure paths are strings
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
            logger.info(f"FFmpeg command: cmd={' '.join(cmd)}", cmd=" ".join(cmd))

            logger.info("Starting FFmpeg for video processing...")

            process = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )

            # Wait for the process to complete
            await process.wait()

            if process.returncode != 0:
                logger.error(f"FFmpeg finished with error: code={process.returncode}", code=process.returncode)
                stderr_output = await process.stderr.read()
                logger.error(f"FFmpeg error: output={stderr_output.decode()[:500]}", error=stderr_output.decode()[:500])
                return False

            if Path(output_path).exists():
                file_size = Path(output_path).stat().st_size
                logger.info(
                    f"File created: path={output_path} | size={file_size} bytes",
                    path=output_path,
                    size_bytes=file_size
                )
                return True
            logger.error(f"File not created: path={output_path}", path=output_path)
            return False

        except Exception as e:
            logger.error(f"Exception during video trimming: error={e}", error=str(e))
            logger.error(f"Traceback: {traceback.format_exc()}")
            return False

    async def process_segment(self, segment: VideoSegment, input_path: str) -> bool:
        """Process a single segment."""
        try:
            start_time = segment.start_time
            end_time = segment.end_time

            if self.config.remove_intro and start_time == 0:
                start_time = self.config.intro_duration

            if self.config.remove_outro:
                video_info = await self.get_video_info(input_path)
                max_time = video_info["duration"]
                end_time = min(max_time - self.config.outro_duration, end_time)

            Path(segment.output_path).parent.mkdir(parents=True, exist_ok=True)
            success = await self.trim_video(input_path, segment.output_path, start_time, end_time)

            if success:
                segment.processed = True
                segment.processing_time = datetime.now()
                return True
            return False

        except Exception as e:
            logger.info(
                f"Error processing segment: title={segment.title} | error={e}",
                title=segment.title,
                error=str(e)
            )
            return False

    async def process_video(
        self, video_path: str, title: str, custom_segments: list[tuple] | None = None
    ) -> list[VideoSegment]:
        """Main video processing function."""
        try:
            video_info = await self.get_video_info(video_path)
            duration = video_info["duration"]

            logger.info(f"Processing video: title={title}", title=title)
            logger.info(f"   Duration: {duration / 60:.1f} min", duration_min=duration / 60)
            logger.info(
                f"   Size: {video_info['size'] / 1024 / 1024:.1f} MB",
                size_mb=video_info["size"] / 1024 / 1024
            )
            logger.info(
                f"   Resolution: {video_info['width']}x{video_info['height']}",
                width=video_info["width"],
                height=video_info["height"]
            )

            if custom_segments:
                segments = self.segment_processor.create_segments_from_timestamps(custom_segments, title)
            else:
                segments = self.segment_processor.create_segments_from_duration(duration, title)

            logger.info(f"   Created segments: count={len(segments)}", segments=len(segments))

            processed_segments = []
            for i, segment in enumerate(segments, 1):
                logger.info(
                    f"   Processing segment: number={i}/{len(segments)} | title={segment.title}",
                    segment=i,
                    total=len(segments),
                    title=segment.title
                )

                success = await self.process_segment(segment, video_path)
                if success:
                    processed_segments.append(segment)
                    logger.info(f"   Segment processed: path={segment.output_path}", path=segment.output_path)
                else:
                    logger.info(f"   Error processing segment: title={segment.title}", title=segment.title)

            logger.info(
                f"Processing completed: processed={len(processed_segments)}/{len(segments)} segments",
                processed=len(processed_segments),
                total=len(segments)
            )
            return processed_segments

        except Exception as e:
            logger.info(f"Error processing video: title={title} | error={e}", title=title, error=str(e))
            return []


    async def batch_process(self, video_files: list[str]) -> dict[str, list[VideoSegment]]:
        """Batch processing multiple videos."""
        results = {}

        for video_path in video_files:
            if not Path(video_path).exists():
                logger.info(f"File not found: path={video_path}", path=video_path)
                continue

            title = Path(video_path).stem

            segments = await self.process_video(video_path, title)
            results[video_path] = segments

        return results

    def cleanup_temp_files(self):
        """Cleaning up temporary files."""
        if not self.config.keep_temp_files:
            temp_dir = Path(self.config.temp_dir)
            if temp_dir.exists():
                shutil.rmtree(temp_dir)
                logger.info(f"Temporary files cleaned up: dir={temp_dir}", dir=str(temp_dir))

    def get_processing_statistics(self, results: dict[str, list[VideoSegment]]) -> dict[str, Any]:
        """Getting processing statistics."""
        total_videos = len(results)
        total_segments = sum(len(segments) for segments in results.values())
        processed_segments = sum(len([s for s in segments if s.processed]) for segments in results.values())

        total_duration = 0
        for segments in results.values():
            for segment in segments:
                if segment.processed:
                    total_duration += segment.duration

        return {
            "total_videos": total_videos,
            "total_segments": total_segments,
            "processed_segments": processed_segments,
            "success_rate": (processed_segments / total_segments * 100) if total_segments > 0 else 0,
            "total_processed_duration": total_duration,
            "total_processed_duration_formatted": f"{total_duration / 60:.1f} minutes",
        }
