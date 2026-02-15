"""Transcription and extraction file manager"""

import json
from datetime import datetime
from pathlib import Path

from file_storage.path_builder import StoragePathBuilder
from logger import get_logger

logger = get_logger(__name__)


class TranscriptionManager:
    """Manage transcription files (master.json) and extraction (extracted.json, cache)"""

    def __init__(self):
        """Initialize transcription manager."""

    def get_dir(self, recording_id: int, user_slug: int) -> Path:
        """
        Get transcription directory for recording.

        Args:
            recording_id: Recording ID
            user_slug: User slug (6-digit integer from users.user_slug)

        Returns:
            Path to transcriptions directory

        Raises:
            ValueError: If user_slug is None
        """
        if user_slug is None:
            raise ValueError("user_slug is required. Get it from recording.owner.user_slug or user.user_slug")

        storage_builder = StoragePathBuilder()
        return storage_builder.transcription_dir(user_slug, recording_id)

    def has_master(self, recording_id: int, user_slug: int) -> bool:
        """Check if master.json exists."""
        return (self.get_dir(recording_id, user_slug) / "master.json").exists()

    def has_extracted(self, recording_id: int, user_slug: int) -> bool:
        """Check if extracted.json exists (topics, summary from DeepSeek)."""
        return (self.get_dir(recording_id, user_slug) / "extracted.json").exists()

    def save_master(
        self,
        recording_id: int,
        words: list[dict],
        segments: list[dict],
        language: str = "ru",
        model: str = "fireworks",
        duration: float = 0.0,
        usage_metadata: dict | None = None,
        user_slug: int | None = None,
        **meta,
    ) -> str:
        """Save transcription results to master.json with words, segments, and metadata."""
        if user_slug is None:
            raise ValueError("user_slug is required. Get it from recording.owner.user_slug or user.user_slug")
        dir_path = self.get_dir(recording_id, user_slug)
        dir_path.mkdir(parents=True, exist_ok=True)

        stats = {
            "words_count": len(words),
            "segments_count": len(segments),
            "total_duration": duration,
        }

        master_data = {
            "recording_id": recording_id,
            "created_at": datetime.now().isoformat(),
            "model": model,
            "language": language,
            "duration": duration,
            "words": words,
            "segments": segments,
            "stats": stats,
            "_metadata": usage_metadata or {},
            **meta,
        }

        master_path = dir_path / "master.json"
        with master_path.open("w", encoding="utf-8") as f:
            json.dump(master_data, f, ensure_ascii=False, indent=2)

        logger.info(
            f"Saved master.json for recording {recording_id}: "
            f"words={len(words)}, segments={len(segments)}, model={model}"
        )
        return str(master_path)

    def load_master(self, recording_id: int, user_slug: int) -> dict:
        """Load transcription data from master.json."""
        master_path = self.get_dir(recording_id, user_slug) / "master.json"
        if not master_path.exists():
            raise FileNotFoundError(f"master.json not found for recording {recording_id}: {master_path}")

        with master_path.open(encoding="utf-8") as f:
            return json.load(f)

    def add_extracted_version(
        self,
        recording_id: int,
        version_id: str,
        model: str,
        granularity: str,
        main_topics: list[str],
        topic_timestamps: list[dict],
        pauses: list[dict] | None = None,
        summary: str | None = None,
        is_active: bool = True,
        usage_metadata: dict | None = None,
        user_slug: int | None = None,
        **meta,
    ) -> str:
        """Add new extraction version to extracted.json (topics, summary from DeepSeek)."""
        if user_slug is None:
            raise ValueError("user_slug is required. Get it from recording.owner.user_slug or user.user_slug")
        extracted_path = self.get_dir(recording_id, user_slug) / "extracted.json"

        if extracted_path.exists():
            with extracted_path.open(encoding="utf-8") as f:
                extracted_file = json.load(f)
        else:
            extracted_file = {
                "recording_id": recording_id,
                "active_version": None,
                "versions": [],
            }

        if is_active:
            for v in extracted_file["versions"]:
                v["is_active"] = False
            extracted_file["active_version"] = version_id

        version_data = {
            "id": version_id,
            "model": model,
            "granularity": granularity,
            "created_at": datetime.now().isoformat(),
            "is_active": is_active,
            "main_topics": main_topics,
            "topic_timestamps": topic_timestamps,
            "pauses": pauses or [],
            "summary": (summary or "").strip(),
            "_metadata": usage_metadata or {},
            **meta,
        }

        extracted_file["versions"].append(version_data)

        extracted_path.parent.mkdir(parents=True, exist_ok=True)
        with extracted_path.open("w", encoding="utf-8") as f:
            json.dump(extracted_file, f, ensure_ascii=False, indent=2)

        logger.info(
            f"Added extracted version {version_id} for recording {recording_id}: "
            f"topics={len(topic_timestamps)}, model={model}"
        )
        return str(extracted_path)

    def load_extracted(self, recording_id: int, user_slug: int) -> dict:
        """Load extraction data from extracted.json."""
        extracted_path = self.get_dir(recording_id, user_slug) / "extracted.json"
        if not extracted_path.exists():
            raise FileNotFoundError(f"extracted.json not found for recording {recording_id}: {extracted_path}")

        with extracted_path.open(encoding="utf-8") as f:
            return json.load(f)

    def get_active_extracted(self, recording_id: int, user_slug: int) -> dict | None:
        """Return active extraction version (topics, summary) or None if not found."""
        try:
            extracted_data = self.load_extracted(recording_id, user_slug)
            active_version_id = extracted_data.get("active_version")

            if not active_version_id:
                return None

            for version in extracted_data.get("versions", []):
                if version.get("id") == active_version_id:
                    return version

            return None
        except FileNotFoundError:
            return None

    def generate_cache_files(self, recording_id: int, user_slug: int) -> dict[str, str]:
        """Generate cache files (segments.txt, words.txt, auto_segments.txt) from master.json."""
        master = self.load_master(recording_id, user_slug)
        cache_dir = self.get_dir(recording_id, user_slug) / "cache"
        cache_dir.mkdir(parents=True, exist_ok=True)

        files = {}

        segments_path = cache_dir / "segments.txt"
        self._generate_segments_txt(master["segments"], segments_path)
        files["segments_txt"] = str(segments_path)

        words_path = cache_dir / "words.txt"
        self._generate_words_txt(master["words"], words_path)
        files["words_txt"] = str(words_path)

        auto_segments_path = cache_dir / "auto_segments.txt"
        self._generate_segments_txt(master["segments"], auto_segments_path)
        files["auto_segments_txt"] = str(auto_segments_path)

        logger.info(f"Generated cache files for recording {recording_id}: {list(files.keys())}")
        return files

    def ensure_segments_txt(self, recording_id: int, user_slug: int) -> Path:
        """Ensure segments.txt exists, generating from master.json if needed."""
        segments_path = self.get_dir(recording_id, user_slug) / "cache" / "segments.txt"

        if not segments_path.exists():
            master = self.load_master(recording_id, user_slug)
            segments_path.parent.mkdir(parents=True, exist_ok=True)
            self._generate_segments_txt(master["segments"], segments_path)

        return segments_path

    def generate_subtitles(self, recording_id: int, formats: list[str], user_slug: int) -> dict[str, str]:
        """Generate subtitle files in specified formats from master.json."""
        from subtitle_module import SubtitleGenerator

        segments_path = self.ensure_segments_txt(recording_id, user_slug)
        cache_dir = self.get_dir(recording_id, user_slug) / "cache"

        generator = SubtitleGenerator()
        result = generator.generate_from_transcription(
            transcription_path=str(segments_path),
            output_dir=str(cache_dir),
            formats=formats,
        )

        logger.info(f"Generated subtitles for recording {recording_id}: {formats}")
        return result

    def generate_version_id(self, recording_id: int, user_slug: int) -> str:
        """Generate next version ID (v1, v2, etc.) for extracted.json."""
        try:
            extracted_data = self.load_extracted(recording_id, user_slug)
            version_count = len(extracted_data.get("versions", []))
            return f"v{version_count + 1}"
        except FileNotFoundError:
            return "v1"

    def _generate_segments_txt(self, segments: list[dict], output_path: Path):
        """Generate segments.txt with timestamped text segments."""
        with output_path.open("w", encoding="utf-8") as f:
            for seg in segments:
                start = self._format_time_ms(seg["start"])
                end = self._format_time_ms(seg["end"])
                text = seg["text"]
                f.write(f"[{start} - {end}] {text}\n")

        logger.debug(f"Generated segments.txt: {output_path}, count={len(segments)}")

    def _generate_words_txt(self, words: list[dict], output_path: Path):
        """Generate words.txt with timestamped individual words."""
        with output_path.open("w", encoding="utf-8") as f:
            for word in words:
                start = self._format_time_ms(word["start"])
                end = self._format_time_ms(word["end"])
                text = word["word"]
                f.write(f"[{start} - {end}] {text}\n")

        logger.debug(f"Generated words.txt: {output_path}, count={len(words)}")

    @staticmethod
    def _format_time_ms(seconds: float) -> str:
        """Format time as HH:MM:SS.mmm."""
        total_seconds = int(seconds)
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        secs = total_seconds % 60
        milliseconds = int((seconds - total_seconds) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}.{milliseconds:03d}"


_transcription_manager: TranscriptionManager | None = None


def get_transcription_manager() -> TranscriptionManager:
    """Get global TranscriptionManager instance."""
    global _transcription_manager
    if _transcription_manager is None:
        _transcription_manager = TranscriptionManager()
    return _transcription_manager
