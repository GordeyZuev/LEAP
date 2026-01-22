"""Storage backend factory"""

from config.settings import get_settings
from file_storage.backends.base import StorageBackend
from file_storage.backends.local import LocalStorageBackend
from logger import get_logger

logger = get_logger(__name__)


def create_storage_backend() -> StorageBackend:
    """
    Create storage backend based on settings.

    Returns:
        StorageBackend instance configured based on STORAGE_TYPE setting
    """
    settings = get_settings()
    storage_type = settings.storage.storage_type.upper()

    logger.info(f"Creating storage backend: type={storage_type}")

    if storage_type == "LOCAL":
        from pathlib import Path

        base_path = Path(settings.storage.local_path)
        max_size_gb = settings.storage.local_max_size_gb

        backend = LocalStorageBackend(
            base_path=base_path,
            max_size_gb=max_size_gb,
        )

        logger.info(f"LOCAL storage backend created: path={base_path} | max_size={max_size_gb}GB")
        return backend

    if storage_type == "S3":
        # S3 backend will be implemented in future iteration
        raise NotImplementedError(
            "S3 storage backend is not implemented yet. "
            "Please use STORAGE_TYPE=LOCAL or implement S3StorageBackend."
        )

    raise ValueError(f"Unknown storage type: {storage_type}. Supported types: LOCAL, S3")


# Singleton instance
_backend_instance: StorageBackend | None = None


def get_storage_backend() -> StorageBackend:
    """Get the global storage backend instance (singleton)"""
    global _backend_instance
    if _backend_instance is None:
        _backend_instance = create_storage_backend()
    return _backend_instance
