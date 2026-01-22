"""Storage path builder for consistent path generation"""

import shutil
import time
import uuid
from pathlib import Path

from logger import get_logger

logger = get_logger(__name__)


class StoragePathBuilder:
    """Build storage paths following the new structure with ID-based naming"""

    def __init__(self, base_path: str = "storage"):
        """
        Initialize path builder.

        Args:
            base_path: Base directory for storage
        """
        self.base = Path(base_path)

    # Shared resources
    def shared_thumbnail(self, filename: str) -> Path:
        """Get path to shared thumbnail"""
        return self.base / "shared" / "thumbnails" / filename

    def shared_thumbnails_dir(self) -> Path:
        """Get shared thumbnails directory"""
        return self.base / "shared" / "thumbnails"

    # Temp directory
    def temp_dir(self) -> Path:
        """Get temp directory for processing"""
        return self.base / "temp"

    def create_temp_file(self, prefix: str = "proc_", suffix: str = "") -> Path:
        """
        Create unique temp file path.

        Args:
            prefix: Filename prefix
            suffix: Filename suffix (e.g., '.mp4')

        Returns:
            Path to temp file (directory created if needed)
        """
        temp_dir = self.temp_dir()
        temp_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{prefix}{uuid.uuid4().hex[:8]}{suffix}"
        return temp_dir / filename

    # User directories
    def user_root(self, user_slug: int) -> Path:
        """
        Get user root directory.

        Args:
            user_slug: User slug (6-digit integer from sequence)

        Returns:
            Path like: storage/users/user_000001
        """
        return self.base / "users" / f"user_{user_slug:06d}"

    def user_thumbnails_dir(self, user_slug: int) -> Path:
        """Get user thumbnails directory"""
        return self.user_root(user_slug) / "thumbnails"

    # Recording directories
    def recording_root(self, user_slug: int, recording_id: int) -> Path:
        """
        Get recording root directory.

        Args:
            user_slug: User slug
            recording_id: Recording ID

        Returns:
            Path like: storage/users/user_000001/recordings/74
        """
        return self.user_root(user_slug) / "recordings" / str(recording_id)

    # Recording files (ID-based naming - no display_name!)
    def recording_source(self, user_slug: int, recording_id: int) -> Path:
        """
        Get path to original video file.

        Returns:
            Path like: storage/users/user_000001/recordings/74/source.mp4
        """
        return self.recording_root(user_slug, recording_id) / "source.mp4"

    def recording_video(self, user_slug: int, recording_id: int) -> Path:
        """
        Get path to processed video file.

        Returns:
            Path like: storage/users/user_000001/recordings/74/video.mp4
        """
        return self.recording_root(user_slug, recording_id) / "video.mp4"

    def recording_audio(self, user_slug: int, recording_id: int) -> Path:
        """
        Get path to extracted audio file.

        Returns:
            Path like: storage/users/user_000001/recordings/74/audio.mp3
        """
        return self.recording_root(user_slug, recording_id) / "audio.mp3"

    # Transcription files
    def transcription_dir(self, user_slug: int, recording_id: int) -> Path:
        """
        Get transcription directory.

        Returns:
            Path like: storage/users/user_000001/recordings/74/transcriptions
        """
        return self.recording_root(user_slug, recording_id) / "transcriptions"

    def transcription_cache_dir(self, user_slug: int, recording_id: int) -> Path:
        """
        Get transcription cache directory.

        Returns:
            Path like: storage/users/user_000001/recordings/74/transcriptions/cache
        """
        return self.transcription_dir(user_slug, recording_id) / "cache"

    def transcription_master(self, user_slug: int, recording_id: int) -> Path:
        """Get path to master.json"""
        return self.transcription_dir(user_slug, recording_id) / "master.json"

    def transcription_topics(self, user_slug: int, recording_id: int) -> Path:
        """Get path to topics.json"""
        return self.transcription_dir(user_slug, recording_id) / "topics.json"

    def transcription_subtitles(self, user_slug: int, recording_id: int, file_format: str) -> Path:
        """
        Get path to subtitles file.

        Args:
            user_slug: User slug
            recording_id: Recording ID
            file_format: Subtitle format (e.g., 'srt', 'vtt')

        Returns:
            Path like: storage/users/user_000001/recordings/74/transcriptions/subtitles.srt
        """
        return self.transcription_dir(user_slug, recording_id) / f"subtitles.{file_format}"

    # Helpers
    def delete_recording_files(self, user_slug: int, recording_id: int) -> None:
        """
        Delete entire recording directory.

        Args:
            user_slug: User slug
            recording_id: Recording ID
        """
        recording_dir = self.recording_root(user_slug, recording_id)
        if recording_dir.exists():
            shutil.rmtree(recording_dir)
            logger.info(f"Deleted recording directory: {recording_dir}")
        else:
            logger.warning(f"Recording directory not found: {recording_dir}")

    def get_recording_size(self, user_slug: int, recording_id: int) -> int:
        """
        Get total size of recording files in bytes.

        Args:
            user_slug: User slug
            recording_id: Recording ID

        Returns:
            Total size in bytes
        """
        recording_dir = self.recording_root(user_slug, recording_id)
        total_size = 0

        if not recording_dir.exists():
            return 0

        for file_path in recording_dir.rglob("*"):
            if file_path.is_file():
                try:
                    total_size += file_path.stat().st_size
                except (OSError, FileNotFoundError):
                    # Skip files that can't be accessed
                    continue

        return total_size

    def cleanup_temp(self, max_age_hours: int = 24) -> int:
        """
        Clean up old temp files.

        Args:
            max_age_hours: Maximum age of temp files in hours

        Returns:
            Number of files deleted
        """
        temp_dir = self.temp_dir()
        if not temp_dir.exists():
            return 0

        deleted = 0
        cutoff_time = time.time() - (max_age_hours * 3600)

        for file_path in temp_dir.iterdir():
            if file_path.is_file():
                try:
                    if file_path.stat().st_mtime < cutoff_time:
                        file_path.unlink()
                        deleted += 1
                except (OSError, FileNotFoundError):
                    # Skip files that can't be accessed
                    continue

        if deleted > 0:
            logger.info(f"Cleaned up {deleted} temp files older than {max_age_hours}h")

        return deleted


# Singleton instance
_path_builder: StoragePathBuilder | None = None


def get_path_builder(base_path: str = "storage") -> StoragePathBuilder:
    """
    Get singleton path builder instance.

    Args:
        base_path: Base directory for storage

    Returns:
        StoragePathBuilder instance (cached)
    """
    global _path_builder

    if _path_builder is None:
        _path_builder = StoragePathBuilder(base_path)

    return _path_builder
