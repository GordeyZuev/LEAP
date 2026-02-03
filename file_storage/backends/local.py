"""Local filesystem storage backend"""

from pathlib import Path

import aiofiles

from file_storage.backends.base import StorageBackend, StorageQuotaExceededError
from logger import get_logger

logger = get_logger(__name__)


class LocalStorageBackend(StorageBackend):
    """Local filesystem storage backend"""

    def __init__(self, base_path: Path | str = "storage", max_size_gb: int | None = None):
        self.base = Path(base_path)
        self.max_size_gb = max_size_gb
        self.base.mkdir(parents=True, exist_ok=True)

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

        full_path = self.base / path
        full_path.parent.mkdir(parents=True, exist_ok=True)

        async with aiofiles.open(full_path, "wb") as f:
            await f.write(content)

        return str(full_path)

    async def load(self, path: str) -> bytes:
        full_path = self.base / path
        if not full_path.exists():
            raise FileNotFoundError(f"File not found: {full_path}")

        async with aiofiles.open(full_path, "rb") as f:
            return await f.read()

    async def delete(self, path: str) -> bool:
        full_path = self.base / path
        if not full_path.exists():
            return False

        full_path.unlink()
        return True

    async def exists(self, path: str) -> bool:
        return (self.base / path).exists()

    async def get_size(self, path: str) -> int:
        full_path = self.base / path
        if not full_path.exists():
            raise FileNotFoundError(f"File not found: {full_path}")

        return full_path.stat().st_size

    def _get_total_size(self) -> int:
        """Calculate total storage size (used for quota checks)"""
        return sum(
            file_path.stat().st_size
            for file_path in self.base.rglob("*")
            if file_path.is_file()
            and not self._should_skip_file(file_path)
        )

    def _should_skip_file(self, file_path: Path) -> bool:
        """Check if file should be skipped during size calculation"""
        try:
            file_path.stat()
            return False
        except (OSError, FileNotFoundError):
            return True
