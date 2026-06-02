"""Abstract storage backend interface"""

from abc import ABC, abstractmethod
from pathlib import Path

import aiofiles


class StorageBackend(ABC):
    """Abstract storage backend for file operations.

    Small artifacts (JSON, text, thumbnails) use ``save``/``load`` (bytes in memory).
    Large artifacts (video, audio) use ``save_file``/``download_to_file`` to stream
    via local temp files — these have default impls but should be overridden by
    storage backends that support native streaming (e.g. S3 multipart).
    """

    @abstractmethod
    async def save(self, path: str, content: bytes) -> str:
        """Save file and return full path/key. Raises StorageQuotaExceededError if quota exceeded"""

    @abstractmethod
    async def load(self, path: str) -> bytes:
        """Load file content. Raises FileNotFoundError if not exists"""

    @abstractmethod
    async def delete(self, path: str) -> bool:
        """Delete file. Returns True if deleted, False if not found"""

    @abstractmethod
    async def exists(self, path: str) -> bool:
        """Check if file exists"""

    @abstractmethod
    async def get_size(self, path: str) -> int:
        """Get file size in bytes. Raises FileNotFoundError if not exists"""

    async def save_file(self, path: str, local_path: Path) -> str:
        """Upload a local file to storage. Default impl reads bytes in memory;
        override for streaming (S3 multipart, local move).
        """
        async with aiofiles.open(local_path, "rb") as f:
            content = await f.read()
        return await self.save(path, content)

    async def download_to_file(self, path: str, local_path: Path) -> None:
        """Download a stored object to a local file. Default impl loads bytes in memory;
        override for streaming (S3 download_file, local copy).
        """
        local_path.parent.mkdir(parents=True, exist_ok=True)
        content = await self.load(path)
        async with aiofiles.open(local_path, "wb") as f:
            await f.write(content)

    async def presigned_url(self, path: str, expires_in: int = 3600) -> str:
        """Generate a time-limited URL for direct client access.

        S3 backends return a real presigned URL. LOCAL backend returns an internal
        backend-served URL (frontend code stays identical).
        """
        raise NotImplementedError("This backend does not support presigned URLs")

    async def list_keys(self, prefix: str) -> list[str]:
        """List all storage keys under a prefix.

        Default impl raises NotImplementedError; concrete backends implement it
        in a way that's appropriate for their storage (filesystem rglob vs. S3
        list_objects_v2 pagination).
        """
        raise NotImplementedError("This backend does not implement list_keys")

    async def health_check(self) -> None:
        """Verify the backend is reachable. Raises on failure."""
        raise NotImplementedError("This backend does not implement health_check")


class StorageQuotaExceededError(Exception):
    """Raised when storage quota is exceeded"""
