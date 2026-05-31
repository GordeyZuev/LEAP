"""Unit tests for path_builder helpers."""

from pathlib import Path

import pytest

from file_storage.path_builder import StoragePathBuilder, to_storage_key


@pytest.mark.unit
class TestToStorageKey:
    """Tests for to_storage_key helper."""

    def test_strips_storage_prefix(self):
        assert to_storage_key("storage/users/000001/video.mp4") == "users/000001/video.mp4"

    def test_path_object(self):
        p = Path("storage") / "users" / "000001" / "video.mp4"
        assert to_storage_key(p) == "users/000001/video.mp4"

    def test_already_a_key(self):
        assert to_storage_key("users/000001/video.mp4") == "users/000001/video.mp4"

    def test_idempotent(self):
        once = to_storage_key("storage/users/000001/x.mp4")
        twice = to_storage_key(once)
        assert once == twice

    def test_custom_base(self):
        assert to_storage_key("media/users/x.mp4", base="media") == "users/x.mp4"

    def test_leading_slash_stripped(self):
        assert to_storage_key("/storage/users/x.mp4") == "users/x.mp4"


@pytest.mark.unit
class TestStoragePathBuilder:
    """Tests for StoragePathBuilder paths produce expected keys."""

    def test_recording_paths(self):
        b = StoragePathBuilder()
        assert to_storage_key(b.recording_source(1, 42)) == "users/user_000001/recordings/42/source.mp4"
        assert to_storage_key(b.recording_video(1, 42)) == "users/user_000001/recordings/42/video.mp4"
        assert to_storage_key(b.recording_audio(1, 42)) == "users/user_000001/recordings/42/audio.mp3"

    def test_transcription_paths(self):
        b = StoragePathBuilder()
        assert (
            to_storage_key(b.transcription_master(1, 42))
            == "users/user_000001/recordings/42/transcriptions/master.json"
        )
        assert (
            to_storage_key(b.transcription_extracted(1, 42))
            == "users/user_000001/recordings/42/transcriptions/extracted.json"
        )
