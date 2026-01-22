"""Abstract storage backend interface"""

from abc import ABC, abstractmethod


class StorageBackend(ABC):
    """Abstract storage backend interface for file operations"""

    @abstractmethod
    async def save(self, path: str, content: bytes) -> str:
        """
        Save file to storage.

        Args:
            path: Relative path within storage
            content: File content as bytes

        Returns:
            Full path to saved file

        Raises:
            StorageQuotaExceededError: If storage quota is exceeded
        """

    @abstractmethod
    async def load(self, path: str) -> bytes:
        """
        Load file from storage.

        Args:
            path: Relative path within storage

        Returns:
            File content as bytes

        Raises:
            FileNotFoundError: If file doesn't exist
        """

    @abstractmethod
    async def delete(self, path: str) -> bool:
        """
        Delete file from storage.

        Args:
            path: Relative path within storage

        Returns:
            True if file was deleted, False if not found
        """

    @abstractmethod
    async def exists(self, path: str) -> bool:
        """
        Check if file exists in storage.

        Args:
            path: Relative path within storage

        Returns:
            True if file exists, False otherwise
        """

    @abstractmethod
    async def get_size(self, path: str) -> int:
        """
        Get file size.

        Args:
            path: Relative path within storage

        Returns:
            File size in bytes

        Raises:
            FileNotFoundError: If file doesn't exist
        """


class StorageQuotaExceededError(Exception):
    """Raised when storage quota is exceeded"""

