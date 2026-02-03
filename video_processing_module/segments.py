from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from logger import get_logger

if TYPE_CHECKING:
    from .config import ProcessingConfig

logger = get_logger()


@dataclass
class VideoSegment:
    """Video segment with time boundaries and metadata."""

    start_time: float
    end_time: float
    duration: float
    title: str
    description: str
    output_path: str
    processed: bool = False
    processing_time: datetime | None = None

    def __post_init__(self):
        if self.start_time < 0:
            raise ValueError("start_time cannot be negative")

        if self.end_time <= self.start_time:
            raise ValueError("end_time must be greater than start_time")

        if self.duration != (self.end_time - self.start_time):
            self.duration = self.end_time - self.start_time


class SegmentProcessor:
    """Creates video segments based on duration or timestamps."""

    def __init__(self, config: "ProcessingConfig") -> None:
        self.config = config

    def create_segments_from_duration(self, video_duration: float, title: str) -> list[VideoSegment]:
        """Split video into equal-duration segments with overlap."""
        segments = []
        segment_duration_sec = self.config.segment_duration * 60
        overlap_sec = self.config.overlap_duration * 60

        current_start = 0
        segment_index = 1

        while current_start < video_duration:
            current_end = min(current_start + segment_duration_sec, video_duration)
            segment_title = f"{title} - Part {segment_index}"
            segment_description = f"Segment {segment_index} of {title}"

            output_filename = f"{title}_part_{segment_index:02d}.{self.config.output_format}"
            output_path = Path(self.config.output_dir) / output_filename

            segment = VideoSegment(
                start_time=current_start,
                end_time=current_end,
                duration=current_end - current_start,
                title=segment_title,
                description=segment_description,
                output_path=output_path,
            )

            segments.append(segment)

            current_start = current_end - overlap_sec
            segment_index += 1
            if current_start >= video_duration:
                break

        return segments

    def create_segments_from_timestamps(self, timestamps: list[tuple], title: str) -> list[VideoSegment]:
        """Create segments from explicit timestamp boundaries."""
        segments = []

        for i, (start_time, end_time, segment_title) in enumerate(timestamps, 1):
            if not segment_title:
                segment_title = f"{title} - Part {i}"

            output_filename = f"{title}_part_{i:02d}.{self.config.output_format}"
            output_path = Path(self.config.output_dir) / output_filename

            segment = VideoSegment(
                start_time=start_time,
                end_time=end_time,
                duration=end_time - start_time,
                title=segment_title,
                description=f"Segment {i} of {title}",
                output_path=output_path,
            )

            segments.append(segment)

        return segments
