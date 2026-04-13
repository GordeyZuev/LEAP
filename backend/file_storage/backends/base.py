"""Abstract storage backend interface"""

from abc import ABC, abstractmethod


class StorageBackend(ABC):
    """Abstract storage backend for file operations"""

    @abstractmethod
    async def save(self, path: str, content: bytes) -> str:
        """Save file and return full path. Raises StorageQuotaExceededError if quota exceeded"""

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


class StorageQuotaExceededError(Exception):
    """Raised when storage quota is exceeded"""
