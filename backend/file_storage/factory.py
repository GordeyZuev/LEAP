"""Storage backend factory"""

from pathlib import Path

from config.settings import get_settings
from file_storage.backends.base import StorageBackend
from file_storage.backends.local import LocalStorageBackend
from file_storage.backends.s3 import S3StorageBackend
from logger import get_logger

logger = get_logger(__name__)


def create_storage_backend() -> StorageBackend:
    """Create storage backend based on STORAGE_TYPE setting"""
    settings = get_settings()
    storage_type = settings.storage.type.upper()

    if storage_type == "LOCAL":
        backend = LocalStorageBackend(
            base_path=Path(settings.storage.local_path),
            max_size_gb=settings.storage.local_max_size_gb,
        )
        logger.info(f"Storage backend initialized: LOCAL | {settings.storage.local_path}")
        return backend

    if storage_type == "S3":
        backend = S3StorageBackend(
            bucket=settings.storage.s3_bucket or "",
            prefix=settings.storage.s3_prefix or "",
            region=settings.storage.s3_region,
            access_key_id=settings.storage.s3_access_key_id,
            secret_access_key=settings.storage.s3_secret_access_key,
            endpoint_url=settings.storage.s3_endpoint_url,
        )
        endpoint = settings.storage.s3_endpoint_url or "AWS"
        logger.info(
            f"Storage backend initialized: S3 | bucket={settings.storage.s3_bucket} "
            f"prefix={settings.storage.s3_prefix!r} endpoint={endpoint}"
        )
        return backend

    raise ValueError(f"Unknown storage type: {storage_type}")


# Singleton instance
_backend_instance: StorageBackend | None = None


def get_storage_backend() -> StorageBackend:
    """Get global storage backend singleton"""
    global _backend_instance
    if _backend_instance is None:
        _backend_instance = create_storage_backend()
    return _backend_instance
