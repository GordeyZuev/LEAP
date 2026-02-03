"""Storage backend factory"""

from pathlib import Path

from config.settings import get_settings
from file_storage.backends.base import StorageBackend
from file_storage.backends.local import LocalStorageBackend
from logger import get_logger

logger = get_logger(__name__)


def create_storage_backend() -> StorageBackend:
    """Create storage backend based on STORAGE_TYPE setting"""
    settings = get_settings()
    storage_type = settings.storage.storage_type.upper()

    if storage_type == "LOCAL":
        backend = LocalStorageBackend(
            base_path=Path(settings.storage.local_path),
            max_size_gb=settings.storage.local_max_size_gb,
        )
        logger.info(f"Storage backend initialized: {storage_type} | {settings.storage.local_path}")
        return backend

    if storage_type == "S3":
        raise NotImplementedError("S3 storage not implemented. Use STORAGE_TYPE=LOCAL")

    raise ValueError(f"Unknown storage type: {storage_type}")


# Singleton instance
_backend_instance: StorageBackend | None = None


def get_storage_backend() -> StorageBackend:
    """Get global storage backend singleton"""
    global _backend_instance
    if _backend_instance is None:
        _backend_instance = create_storage_backend()
    return _backend_instance
