"""Minimal processing config for internal VideoProcessor use only"""

from dataclasses import dataclass


@dataclass
class ProcessingConfig:
    """Minimal config for VideoProcessor internal use"""

    output_dir: str
    silence_threshold: float = -40.0
    min_silence_duration: float = 2.0
    padding_before: float = 5.0
    padding_after: float = 5.0
    input_dir: str = "storage/temp"
    temp_dir: str = "storage/temp"
    video_codec: str = "copy"
    audio_codec: str = "copy"
    video_bitrate: str = "original"
    audio_bitrate: str = "original"
    fps: int = 0
    resolution: str = "original"
    segment_duration: int = 30
    overlap_duration: int = 1
    keep_temp_files: bool = False
