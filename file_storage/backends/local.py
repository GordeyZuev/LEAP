"""Local filesystem storage backend"""

from pathlib import Path

import aiofiles

from file_storage.backends.base import StorageBackend, StorageQuotaExceededError
from logger import get_logger

logger = get_logger(__name__)


class LocalStorageBackend(StorageBackend):
    """Local filesystem storage backend implementation"""

    def __init__(self, base_path: str = "storage", max_size_gb: int | None = None):
        """
        Initialize local storage backend.

        Args:
            base_path: Base directory for storage
            max_size_gb: Maximum storage size in GB (None = unlimited)
        """
        self.base = Path(base_path)
        self.max_size_gb = max_size_gb

        # Ensure base directory exists
        self.base.mkdir(parents=True, exist_ok=True)
        logger.debug(f"Initialized LocalStorageBackend: base={self.base}, max_size_gb={max_size_gb}")

    async def save(self, path: str, content: bytes) -> str:
        """Save file to local filesystem"""
        # Check quota if configured
        if self.max_size_gb:
            current_size = self._get_total_size()
            content_size = len(content)
            max_bytes = self.max_size_gb * (1024**3)

            if current_size + content_size > max_bytes:
                raise StorageQuotaExceededError(
                    f"Storage quota exceeded: current={current_size / (1024**3):.2f}GB, "
                    f"adding={content_size / (1024**3):.2f}GB, max={self.max_size_gb}GB"
                )

        full_path = self.base / path
        full_path.parent.mkdir(parents=True, exist_ok=True)

        # Use aiofiles for async file operations
        async with aiofiles.open(full_path, "wb") as f:
            await f.write(content)

        logger.debug(f"Saved file: {full_path} ({len(content)} bytes)")
        return str(full_path)

    async def load(self, path: str) -> bytes:
        """Load file from local filesystem"""
        full_path = self.base / path

        if not full_path.exists():
            raise FileNotFoundError(f"File not found: {full_path}")

        async with aiofiles.open(full_path, "rb") as f:
            content = await f.read()

        logger.debug(f"Loaded file: {full_path} ({len(content)} bytes)")
        return content

    async def delete(self, path: str) -> bool:
        """Delete file from local filesystem"""
        full_path = self.base / path

        if not full_path.exists():
            return False

        full_path.unlink()
        logger.debug(f"Deleted file: {full_path}")
        return True

    async def exists(self, path: str) -> bool:
        """Check if file exists in local filesystem"""
        full_path = self.base / path
        return full_path.exists()

    async def get_size(self, path: str) -> int:
        """Get file size from local filesystem"""
        full_path = self.base / path

        if not full_path.exists():
            raise FileNotFoundError(f"File not found: {full_path}")

        return full_path.stat().st_size

    def _get_total_size(self) -> int:
        """Calculate total size of all files in storage"""
        total_size = 0

        for file_path in self.base.rglob("*"):
            if file_path.is_file():
                try:
                    total_size += file_path.stat().st_size
                except (OSError, FileNotFoundError):
                    # Skip files that can't be accessed
                    continue

        return total_size
