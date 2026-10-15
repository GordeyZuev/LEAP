"""Source companion files: manifest parsing and download URLs (mocked storage)."""

import asyncio
import json
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from api.helpers.source_extras import list_source_extras
from api.routers.recordings import get_recording_source_extras


def _ctx():
    return SimpleNamespace(session=AsyncMock(), user_id="user-1")


def _recording():
    return SimpleNamespace(id=42, owner=SimpleNamespace(user_slug=1))


CHAT_KEY = "users/user_000001/recordings/42/source_extras/chat.json"
MANIFEST_KEY = "users/user_000001/recordings/42/source_extras/files_manifest.json"
SLIDES_KEY = "users/user_000001/recordings/42/source_extras/files/Лекция_1.pdf"


class _FakeStorage:
    """Storage stub: only the given keys exist."""

    def __init__(self, present: dict[str, bytes]):
        self.present = present
        self.signed: list[tuple[str, str | None]] = []
        self.heads: list[str] = []

    @asynccontextmanager
    async def shared_operations(self):
        yield

    async def exists(self, key: str) -> bool:
        self.heads.append(key)
        return key in self.present

    async def load(self, key: str) -> bytes:
        try:
            return self.present[key]
        except KeyError as exc:
            raise FileNotFoundError(key) from exc

    async def presigned_url(self, key: str, expires_in: int = 3600, *, download_filename: str | None = None) -> str:
        self.signed.append((key, download_filename))
        return f"https://storage.test/{key}?dl={download_filename}&exp={expires_in}"


def _run(storage: _FakeStorage, recording=None):
    repo = AsyncMock()
    repo.get_by_id.return_value = _recording() if recording is None else recording

    return (
        patch("api.routers.recordings.RecordingRepository", return_value=repo),
        patch("file_storage.factory.get_storage_backend", return_value=storage),
    )


@pytest.mark.unit
class TestSourceExtrasEndpoint:
    @pytest.mark.asyncio
    async def test_manifest_lookups_are_bounded_and_keep_order(self):
        keys = [f"users/user_000001/recordings/42/source_extras/files/{i}.pdf" for i in range(12)]
        manifest = [{"storage_key": key, "name": f"{i}.pdf"} for i, key in enumerate(keys)]

        class TrackingStorage(_FakeStorage):
            active = 0
            max_active = 0

            async def exists(self, key: str) -> bool:
                if key in keys:
                    self.active += 1
                    self.max_active = max(self.max_active, self.active)
                    try:
                        await asyncio.sleep(0.001)
                    finally:
                        self.active -= 1
                return await super().exists(key)

        storage = TrackingStorage({MANIFEST_KEY: json.dumps(manifest).encode(), **dict.fromkeys(keys, b"pdf")})
        with patch("file_storage.factory.get_storage_backend", return_value=storage):
            result = await list_source_extras(_recording())

        assert [file.name for file in result.files] == [f"{i}.pdf" for i in range(12)]
        assert 1 < storage.max_active <= 8
        assert MANIFEST_KEY not in storage.heads

    @pytest.mark.asyncio
    async def test_missing_recording_is_404(self):
        repo = AsyncMock()
        repo.get_by_id.return_value = None
        with patch("api.routers.recordings.RecordingRepository", return_value=repo):
            with pytest.raises(HTTPException) as exc:
                await get_recording_source_extras(42, ctx=_ctx())

        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_no_companions_returns_empty_payload(self):
        storage = _FakeStorage({})
        repo_patch, storage_patch = _run(storage)
        with repo_patch, storage_patch:
            result = await get_recording_source_extras(42, ctx=_ctx())

        assert result.chat is None
        assert result.files == []
        assert MANIFEST_KEY not in storage.heads

    @pytest.mark.asyncio
    async def test_chat_and_manifest_files_get_download_urls(self):
        manifest = [
            {"name": "Лекция 1 (итог).pdf", "stored_as": "Лекция_1.pdf", "size": 2048, "storage_key": SLIDES_KEY},
        ]
        storage = _FakeStorage(
            {
                CHAT_KEY: b"{}",
                MANIFEST_KEY: json.dumps(manifest, ensure_ascii=False).encode(),
                SLIDES_KEY: b"%PDF",
            }
        )
        repo_patch, storage_patch = _run(storage)
        with repo_patch, storage_patch:
            result = await get_recording_source_extras(42, ctx=_ctx())

        assert result.chat is not None
        assert result.chat.extension == "json"
        assert len(result.files) == 1
        # The original name is what the user sees and what the file is saved as.
        assert result.files[0].name == "Лекция 1 (итог).pdf"
        assert result.files[0].extension == "pdf"
        assert result.files[0].size == 2048
        assert (SLIDES_KEY, "Лекция 1 (итог).pdf") in storage.signed

    @pytest.mark.asyncio
    async def test_manifest_row_whose_file_vanished_is_skipped(self):
        manifest = [{"name": "gone.pdf", "storage_key": "users/user_000001/recordings/42/source_extras/files/gone.pdf"}]
        storage = _FakeStorage({MANIFEST_KEY: json.dumps(manifest).encode()})
        repo_patch, storage_patch = _run(storage)
        with repo_patch, storage_patch:
            result = await get_recording_source_extras(42, ctx=_ctx())

        assert result.files == []

    @pytest.mark.asyncio
    async def test_unreadable_manifest_does_not_break_the_response(self):
        storage = _FakeStorage({CHAT_KEY: b"{}", MANIFEST_KEY: b"not json at all"})
        repo_patch, storage_patch = _run(storage)
        with repo_patch, storage_patch:
            result = await get_recording_source_extras(42, ctx=_ctx())

        assert result.chat is not None
        assert result.files == []

    @pytest.mark.asyncio
    async def test_malformed_manifest_rows_are_ignored(self):
        storage = _FakeStorage({MANIFEST_KEY: json.dumps(["nonsense", {"name": "no key"}, {}]).encode()})
        repo_patch, storage_patch = _run(storage)
        with repo_patch, storage_patch:
            result = await get_recording_source_extras(42, ctx=_ctx())

        assert result.files == []
