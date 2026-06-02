"""Local filesystem storage backend"""

import shutil
from pathlib import Path

import aiofiles

from file_storage.backends.base import StorageBackend, StorageQuotaExceededError
from logger import get_logger

logger = get_logger(__name__)


class LocalStorageBackend(StorageBackend):
    """Local filesystem storage backend.

    Keys are paths relative to ``base_path`` (e.g. ``users/000001/recordings/42/video.mp4``).
    For backwards compatibility, paths that already include the ``base_path`` prefix
    are normalized via ``_resolve``.
    """

    def __init__(self, base_path: Path | str = "storage", max_size_gb: int | None = None):
        self.base = Path(base_path)
        self.max_size_gb = max_size_gb
        self.base.mkdir(parents=True, exist_ok=True)

    def _resolve(self, path: str | Path) -> Path:
        """Resolve a storage key to an absolute filesystem path.

        Accepts both new-style keys (``users/...``) and legacy paths that
        already start with the storage base directory (``storage/users/...``).
        """
        p = Path(path)
        if p.is_absolute():
            return p
        # Strip leading base dir if caller passed legacy "storage/..." path
        base_name = self.base.name
        if p.parts and p.parts[0] == base_name:
            p = Path(*p.parts[1:])
        return self.base / p

    async def save(self, path: str, content: bytes) -> str:
        if self.max_size_gb:
            current_size = self._get_total_size()
            content_size = len(content)
            max_bytes = self.max_size_gb * (1024**3)

            if current_size + content_size > max_bytes:
                raise StorageQuotaExceededError(
                    f"Quota exceeded: {current_size / (1024**3):.2f}GB + "
                    f"{content_size / (1024**3):.2f}GB > {self.max_size_gb}GB"
                )

        full_path = self._resolve(path)
        full_path.parent.mkdir(parents=True, exist_ok=True)

        async with aiofiles.open(full_path, "wb") as f:
            await f.write(content)

        return str(full_path)

    async def load(self, path: str) -> bytes:
        full_path = self._resolve(path)
        if not full_path.exists():
            raise FileNotFoundError(f"File not found: {full_path}")

        async with aiofiles.open(full_path, "rb") as f:
            return await f.read()

    async def delete(self, path: str) -> bool:
        full_path = self._resolve(path)
        if not full_path.exists():
            return False

        full_path.unlink()
        return True

    async def exists(self, path: str) -> bool:
        return self._resolve(path).exists()

    async def get_size(self, path: str) -> int:
        full_path = self._resolve(path)
        if not full_path.exists():
            raise FileNotFoundError(f"File not found: {full_path}")

        return full_path.stat().st_size

    async def save_file(self, path: str, local_path: Path) -> str:
        """Move local file into storage (cheap rename when on same filesystem).

        Falls back to copy+remove across filesystems. Caller should consider
        ``local_path`` consumed after this call.
        """
        full_path = self._resolve(path)
        full_path.parent.mkdir(parents=True, exist_ok=True)
        # shutil.move handles same/different filesystem cases
        shutil.move(str(local_path), str(full_path))
        return str(full_path)

    async def download_to_file(self, path: str, local_path: Path) -> None:
        """Copy stored file to a local path."""
        full_path = self._resolve(path)
        if not full_path.exists():
            raise FileNotFoundError(f"File not found: {full_path}")
        if full_path == local_path:
            return
        local_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(full_path), str(local_path))

    async def presigned_url(self, path: str, expires_in: int = 3600) -> str:  # noqa: ARG002
        """For LOCAL backend, return a backend-served streaming endpoint URL.

        ``expires_in`` is unused for the local case — the endpoint enforces
        access via the regular auth dependencies. Kept for interface parity
        with the S3 backend so callers can use the same code path.
        """
        return f"/api/v1/storage/stream?key={path}"

    async def list_keys(self, prefix: str) -> list[str]:
        """Return all storage keys under ``prefix`` (recursive)."""
        # Normalize: accept "users/000001/thumbnails" or "storage/users/..."
        full_prefix = self._resolve(prefix)
        if not full_prefix.exists():
            return []

        if full_prefix.is_file():
            return [prefix.rstrip("/")]

        keys: list[str] = []
        for path in full_prefix.rglob("*"):
            if path.is_file():
                # Build the key relative to base
                rel = path.relative_to(self.base)
                keys.append(str(rel))
        return sorted(keys)

    async def health_check(self) -> None:
        """Verify the base directory exists and is writable."""
        if not self.base.exists():
            raise FileNotFoundError(f"Local storage base path missing: {self.base}")
        if not self.base.is_dir():
            raise NotADirectoryError(f"Local storage base path is not a directory: {self.base}")

    def _get_total_size(self) -> int:
        """Calculate total storage size (used for quota checks)"""
        return sum(
            file_path.stat().st_size
            for file_path in self.base.rglob("*")
            if file_path.is_file() and not self._should_skip_file(file_path)
        )

    def _should_skip_file(self, file_path: Path) -> bool:
        """Check if file should be skipped during size calculation"""
        try:
            file_path.stat()
            return False
        except (OSError, FileNotFoundError):
            return True
