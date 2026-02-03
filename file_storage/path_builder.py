"""Storage path builder for consistent path generation"""

import shutil
import time
import uuid
from pathlib import Path

from logger import get_logger

logger = get_logger(__name__)


class StoragePathBuilder:
    """Build storage paths with ID-based naming"""

    def __init__(self, base_path: Path | str = "storage"):
        self.base = Path(base_path)

    def shared_thumbnail(self, filename: str) -> Path:
        return self.base / "shared" / "thumbnails" / filename

    def shared_thumbnails_dir(self) -> Path:
        return self.base / "shared" / "thumbnails"

    def temp_dir(self) -> Path:
        return self.base / "temp"

    def create_temp_file(self, prefix: str = "proc_", suffix: str = "") -> Path:
        """Create unique temp file path (creates directory if needed)"""
        temp_dir = self.temp_dir()
        temp_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{prefix}{uuid.uuid4().hex[:8]}{suffix}"
        return temp_dir / filename

    def user_root(self, user_slug: int) -> Path:
        """Get user root: storage/users/user_000001"""
        return self.base / "users" / f"user_{user_slug:06d}"

    def user_thumbnails_dir(self, user_slug: int) -> Path:
        return self.user_root(user_slug) / "thumbnails"

    def recording_root(self, user_slug: int, recording_id: int) -> Path:
        """Get recording root: storage/users/user_000001/recordings/74"""
        return self.user_root(user_slug) / "recordings" / str(recording_id)

    def recording_source(self, user_slug: int, recording_id: int) -> Path:
        """Original video: .../recordings/74/source.mp4"""
        return self.recording_root(user_slug, recording_id) / "source.mp4"

    def recording_video(self, user_slug: int, recording_id: int) -> Path:
        """Processed video: .../recordings/74/video.mp4"""
        return self.recording_root(user_slug, recording_id) / "video.mp4"

    def recording_audio(self, user_slug: int, recording_id: int) -> Path:
        """Extracted audio: .../recordings/74/audio.mp3"""
        return self.recording_root(user_slug, recording_id) / "audio.mp3"

    def transcription_dir(self, user_slug: int, recording_id: int) -> Path:
        return self.recording_root(user_slug, recording_id) / "transcriptions"

    def transcription_cache_dir(self, user_slug: int, recording_id: int) -> Path:
        return self.transcription_dir(user_slug, recording_id) / "cache"

    def transcription_master(self, user_slug: int, recording_id: int) -> Path:
        return self.transcription_dir(user_slug, recording_id) / "master.json"

    def transcription_topics(self, user_slug: int, recording_id: int) -> Path:
        return self.transcription_dir(user_slug, recording_id) / "topics.json"

    def transcription_subtitles(self, user_slug: int, recording_id: int, file_format: str) -> Path:
        """Get subtitles path: .../transcriptions/subtitles.{format}"""
        return self.transcription_dir(user_slug, recording_id) / f"subtitles.{file_format}"

    def delete_recording_files(self, user_slug: int, recording_id: int) -> None:
        """Delete entire recording directory"""
        recording_dir = self.recording_root(user_slug, recording_id)
        if recording_dir.exists():
            shutil.rmtree(recording_dir)
            logger.info(f"Deleted recording directory: {recording_dir}")

    def get_recording_size(self, user_slug: int, recording_id: int) -> int:
        """Get total recording size in bytes"""
        recording_dir = self.recording_root(user_slug, recording_id)
        if not recording_dir.exists():
            return 0

        return sum(
            file_path.stat().st_size
            for file_path in recording_dir.rglob("*")
            if file_path.is_file() and self._can_access_file(file_path)
        )

    def _can_access_file(self, file_path: Path) -> bool:
        """Check if file is accessible for stat operations"""
        try:
            file_path.stat()
            return True
        except (OSError, FileNotFoundError):
            return False

    def cleanup_temp(self, max_age_hours: int = 24) -> int:
        """Delete temp files older than max_age_hours"""
        temp_dir = self.temp_dir()
        if not temp_dir.exists():
            return 0

        cutoff_time = time.time() - (max_age_hours * 3600)
        deleted = 0

        for file_path in temp_dir.iterdir():
            if file_path.is_file() and self._is_file_old(file_path, cutoff_time):
                try:
                    file_path.unlink()
                    deleted += 1
                except (OSError, FileNotFoundError):
                    continue

        if deleted > 0:
            logger.info(f"Cleaned up {deleted} temp files (>{max_age_hours}h)")

        return deleted

    def _is_file_old(self, file_path: Path, cutoff_time: float) -> bool:
        """Check if file is older than cutoff time"""
        try:
            return file_path.stat().st_mtime < cutoff_time
        except (OSError, FileNotFoundError):
            return False


# Singleton instance
_path_builder: StoragePathBuilder | None = None


def get_path_builder(base_path: Path | str = "storage") -> StoragePathBuilder:
    """Get singleton path builder instance"""
    global _path_builder
    if _path_builder is None:
        _path_builder = StoragePathBuilder(base_path)
    return _path_builder
