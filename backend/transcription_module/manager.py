"""Transcription and extraction file manager.

All persistent files live in the storage backend (S3 in production, local FS in dev).
Methods that perform I/O are ``async`` — they go through ``StorageBackend.load``/``save``.
Pure path helpers (``get_dir``) stay synchronous since they only build keys.

File layout (storage keys, relative to backend root):
    users/{user_slug:06d}/recordings/{rec_id}/transcriptions/master.json     — raw ASR result
    users/{user_slug:06d}/recordings/{rec_id}/transcriptions/extracted.json  — topics/summary versions
    users/{user_slug:06d}/recordings/{rec_id}/transcriptions/cache/segments.txt
    users/{user_slug:06d}/recordings/{rec_id}/transcriptions/cache/words.txt
    users/{user_slug:06d}/recordings/{rec_id}/transcriptions/cache/subtitles.{srt,vtt}
"""

import json
from datetime import datetime
from pathlib import Path

from file_storage.factory import get_storage_backend
from file_storage.path_builder import StoragePathBuilder, to_storage_key
from logger import get_logger

logger = get_logger(__name__)


class TranscriptionManager:
    """Manage transcription files (master.json) and extraction (extracted.json, cache).

    All methods that touch storage are ``async``. ``get_dir`` is sync and returns
    a ``Path`` that can be passed to ``to_storage_key`` to obtain the storage key.
    """

    def __init__(self):
        self._builder = StoragePathBuilder()

    # ------------------------------------------------------------------ paths
    def get_dir(self, recording_id: int, user_slug: int) -> Path:
        """Get transcription directory path (purely a key builder — no I/O)."""
        if user_slug is None:
            raise ValueError("user_slug is required. Get it from recording.owner.user_slug or user.user_slug")
        return self._builder.transcription_dir(user_slug, recording_id)

    def _master_key(self, recording_id: int, user_slug: int) -> str:
        return to_storage_key(self._builder.transcription_master(user_slug, recording_id))

    def _extracted_key(self, recording_id: int, user_slug: int) -> str:
        return to_storage_key(self._builder.transcription_extracted(user_slug, recording_id))

    def _cache_dir_key(self, recording_id: int, user_slug: int) -> str:
        return to_storage_key(self._builder.transcription_cache_dir(user_slug, recording_id))

    # --------------------------------------------------------------- master.json
    async def has_master(self, recording_id: int, user_slug: int) -> bool:
        """Check if master.json exists in storage."""
        return await get_storage_backend().exists(self._master_key(recording_id, user_slug))

    async def save_master(
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
        """Save transcription results to master.json. Returns the storage key."""
        if user_slug is None:
            raise ValueError("user_slug is required. Get it from recording.owner.user_slug or user.user_slug")

        master_data = {
            "recording_id": recording_id,
            "created_at": datetime.now().isoformat(),
            "model": model,
            "language": language,
            "duration": duration,
            "words": words,
            "segments": segments,
            "stats": {
                "words_count": len(words),
                "segments_count": len(segments),
                "total_duration": duration,
            },
            "_metadata": usage_metadata or {},
            **meta,
        }

        key = self._master_key(recording_id, user_slug)
        payload = json.dumps(master_data, ensure_ascii=False, indent=2).encode("utf-8")
        await get_storage_backend().save(key, payload)

        logger.info(
            f"Saved master.json for recording {recording_id}: "
            f"words={len(words)}, segments={len(segments)}, model={model}"
        )
        return key

    async def load_master(self, recording_id: int, user_slug: int) -> dict:
        """Load transcription data from master.json."""
        key = self._master_key(recording_id, user_slug)
        storage = get_storage_backend()
        if not await storage.exists(key):
            raise FileNotFoundError(f"master.json not found for recording {recording_id}: {key}")
        return json.loads(await storage.load(key))

    # ------------------------------------------------------------ extracted.json
    async def has_extracted(self, recording_id: int, user_slug: int) -> bool:
        """Check if extracted.json exists (topics, summary from DeepSeek)."""
        return await get_storage_backend().exists(self._extracted_key(recording_id, user_slug))

    async def add_extracted_version(
        self,
        recording_id: int,
        version_id: str,
        model: str,
        granularity: str,
        main_topics: list[str],
        topic_timestamps: list[dict],
        pauses: list[dict] | None = None,
        summary: str | None = None,
        questions: list[str] | None = None,
        is_active: bool = True,
        usage_metadata: dict | None = None,
        user_slug: int | None = None,
        **meta,
    ) -> str:
        """Add new extraction version to extracted.json."""
        if user_slug is None:
            raise ValueError("user_slug is required. Get it from recording.owner.user_slug or user.user_slug")

        key = self._extracted_key(recording_id, user_slug)
        storage = get_storage_backend()

        if await storage.exists(key):
            extracted_file = json.loads(await storage.load(key))
        else:
            extracted_file = {
                "recording_id": recording_id,
                "active_version": None,
                "versions": [],
            }

        if is_active:
            versions = extracted_file.get("versions", [])
            if isinstance(versions, list):
                for v in versions:
                    if isinstance(v, dict):
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
            "questions": questions or [],
            "_metadata": usage_metadata or {},
            **meta,
        }

        versions_list = extracted_file.get("versions")
        if not isinstance(versions_list, list):
            versions_list = []
            extracted_file["versions"] = versions_list
        versions_list.append(version_data)

        payload = json.dumps(extracted_file, ensure_ascii=False, indent=2).encode("utf-8")
        await storage.save(key, payload)

        logger.info(
            f"Added extracted version {version_id} for recording {recording_id}: "
            f"topics={len(topic_timestamps)}, model={model}"
        )
        return key

    async def load_extracted(self, recording_id: int, user_slug: int) -> dict:
        """Load extraction data from extracted.json."""
        key = self._extracted_key(recording_id, user_slug)
        storage = get_storage_backend()
        if not await storage.exists(key):
            raise FileNotFoundError(f"extracted.json not found for recording {recording_id}: {key}")
        return json.loads(await storage.load(key))

    async def get_active_extracted(self, recording_id: int, user_slug: int) -> dict | None:
        """Return active extraction version (topics, summary) or None if not found."""
        try:
            extracted_data = await self.load_extracted(recording_id, user_slug)
        except FileNotFoundError:
            return None

        active_version_id = extracted_data.get("active_version")
        if not active_version_id:
            return None

        for version in extracted_data.get("versions", []):
            if version.get("id") == active_version_id:
                return version
        return None

    async def generate_version_id(self, recording_id: int, user_slug: int) -> str:
        """Generate next version ID (v1, v2, ...) for extracted.json."""
        try:
            extracted_data = await self.load_extracted(recording_id, user_slug)
            version_count = len(extracted_data.get("versions", []))
            return f"v{version_count + 1}"
        except FileNotFoundError:
            return "v1"

    # ----------------------------------------------------------- cache (text files)
    async def generate_cache_files(self, recording_id: int, user_slug: int) -> dict[str, str]:
        """Generate cache files (segments.txt, words.txt) from master.json.

        Returns a dict of logical name → storage key.
        """
        master = await self.load_master(recording_id, user_slug)
        cache_key_dir = self._cache_dir_key(recording_id, user_slug)
        storage = get_storage_backend()

        files: dict[str, str] = {}

        segments_key = f"{cache_key_dir}/segments.txt"
        await storage.save(segments_key, self._format_segments(master["segments"]).encode("utf-8"))
        files["segments_txt"] = segments_key

        words_key = f"{cache_key_dir}/words.txt"
        await storage.save(words_key, self._format_words(master["words"]).encode("utf-8"))
        files["words_txt"] = words_key

        logger.info(f"Generated cache files for recording {recording_id}: {list(files.keys())}")
        return files

    async def ensure_segments_txt(self, recording_id: int, user_slug: int) -> str:
        """Ensure segments.txt exists, generating it from master.json if needed.

        Returns the storage key (not a local Path — callers must use the storage
        backend or download to a temp file).
        """
        segments_key = f"{self._cache_dir_key(recording_id, user_slug)}/segments.txt"
        storage = get_storage_backend()
        if not await storage.exists(segments_key):
            master = await self.load_master(recording_id, user_slug)
            await storage.save(segments_key, self._format_segments(master["segments"]).encode("utf-8"))
        return segments_key

    async def generate_subtitles(self, recording_id: int, formats: list[str], user_slug: int) -> dict[str, str]:
        """Generate subtitle files in requested formats. Returns dict of format → storage key."""
        from subtitle_module import SubtitleGenerator

        segments_key = await self.ensure_segments_txt(recording_id, user_slug)
        cache_dir_key = self._cache_dir_key(recording_id, user_slug)

        generator = SubtitleGenerator()
        result = await generator.generate_from_transcription(
            transcription_key=segments_key,
            output_dir_key=cache_dir_key,
            formats=formats,
        )

        logger.info(f"Generated subtitles for recording {recording_id}: {formats}")
        return result

    # ------------------------------------------------------------ formatters
    @classmethod
    def _format_segments(cls, segments: list[dict]) -> str:
        """Render segments to ``[HH:MM:SS.mmm - HH:MM:SS.mmm] text\\n`` lines."""
        lines = []
        for seg in segments:
            start = cls._format_time_ms(seg["start"])
            end = cls._format_time_ms(seg["end"])
            lines.append(f"[{start} - {end}] {seg['text']}\n")
        return "".join(lines)

    @classmethod
    def _format_words(cls, words: list[dict]) -> str:
        """Render words to ``[HH:MM:SS.mmm - HH:MM:SS.mmm] word\\n`` lines."""
        lines = []
        for word in words:
            start = cls._format_time_ms(word["start"])
            end = cls._format_time_ms(word["end"])
            lines.append(f"[{start} - {end}] {word['word']}\n")
        return "".join(lines)

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
