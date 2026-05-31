"""Unit tests for LocalStorageBackend."""

import pytest

from file_storage.backends.base import StorageQuotaExceededError
from file_storage.backends.local import LocalStorageBackend


@pytest.mark.unit
@pytest.mark.asyncio
class TestLocalStorageBackend:
    """Tests for LocalStorageBackend."""

    async def test_save_and_load(self, tmp_path):
        backend = LocalStorageBackend(base_path=tmp_path)
        full = await backend.save("users/000001/test.json", b'{"k": "v"}')

        assert (tmp_path / "users/000001/test.json").exists()
        assert full.endswith("users/000001/test.json")
        assert await backend.load("users/000001/test.json") == b'{"k": "v"}'

    async def test_exists(self, tmp_path):
        backend = LocalStorageBackend(base_path=tmp_path)
        assert not await backend.exists("missing.txt")
        await backend.save("there.txt", b"hi")
        assert await backend.exists("there.txt")

    async def test_get_size(self, tmp_path):
        backend = LocalStorageBackend(base_path=tmp_path)
        await backend.save("size.bin", b"123456789")
        assert await backend.get_size("size.bin") == 9

    async def test_get_size_missing(self, tmp_path):
        backend = LocalStorageBackend(base_path=tmp_path)
        with pytest.raises(FileNotFoundError):
            await backend.get_size("nope.bin")

    async def test_delete(self, tmp_path):
        backend = LocalStorageBackend(base_path=tmp_path)
        await backend.save("kill.me", b"x")
        assert await backend.delete("kill.me") is True
        assert await backend.delete("kill.me") is False

    async def test_save_file_moves(self, tmp_path):
        """save_file should move, not copy — the source temp is consumed."""
        backend = LocalStorageBackend(base_path=tmp_path / "storage")
        src = tmp_path / "source_temp.mp4"
        src.write_bytes(b"video data" * 1024)

        await backend.save_file("users/000001/video.mp4", src)

        assert not src.exists(), "save_file should consume source"
        assert (tmp_path / "storage/users/000001/video.mp4").exists()

    async def test_download_to_file_copies(self, tmp_path):
        backend = LocalStorageBackend(base_path=tmp_path / "storage")
        await backend.save("users/000001/audio.mp3", b"audio bytes")

        dst = tmp_path / "local_temp.mp3"
        await backend.download_to_file("users/000001/audio.mp3", dst)

        assert dst.exists()
        assert dst.read_bytes() == b"audio bytes"
        # Source key should still exist
        assert await backend.exists("users/000001/audio.mp3")

    async def test_download_to_file_missing(self, tmp_path):
        backend = LocalStorageBackend(base_path=tmp_path)
        with pytest.raises(FileNotFoundError):
            await backend.download_to_file("missing.bin", tmp_path / "out.bin")

    async def test_resolve_strips_legacy_storage_prefix(self, tmp_path):
        """Legacy DB rows store paths like 'storage/users/...'; backend should handle them
        when base_path is literally named 'storage'."""
        storage_dir = tmp_path / "storage"
        backend = LocalStorageBackend(base_path=storage_dir)
        await backend.save("users/000001/x.txt", b"data")

        # Same file accessed via legacy prefix
        assert await backend.exists("storage/users/000001/x.txt")
        assert await backend.load("storage/users/000001/x.txt") == b"data"

    async def test_quota_enforced(self, tmp_path, monkeypatch):
        """Quota check should raise when exceeded."""
        backend = LocalStorageBackend(base_path=tmp_path, max_size_gb=1)

        # Stub out _get_total_size to simulate near-full storage (>=1 GB used).
        monkeypatch.setattr(backend, "_get_total_size", lambda: 1024**3)

        with pytest.raises(StorageQuotaExceededError):
            await backend.save("big.bin", b"x" * 100)

    async def test_presigned_url_returns_internal_endpoint(self, tmp_path):
        backend = LocalStorageBackend(base_path=tmp_path)
        url = await backend.presigned_url("users/000001/video.mp4")
        assert "users/000001/video.mp4" in url
        assert url.startswith("/api/")
