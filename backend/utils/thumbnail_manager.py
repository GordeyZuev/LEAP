"""User thumbnails manager (storage-backed).

Thumbnails live in storage under two prefixes:
    users/{user_slug:06d}/thumbnails/  — user-specific
    shared/thumbnails/                 — global templates (read-only fallback)

All public methods are ``async`` because they hit the storage backend.
Synchronous path-building helpers remain for compatibility with code that only
needs a key (``get_user_thumbnails_dir``, ``get_global_templates_dir``).
"""

from pathlib import Path

from file_storage.factory import get_storage_backend
from file_storage.path_builder import get_path_builder, to_storage_key
from logger import get_logger

logger = get_logger()

SUPPORTED_IMAGE_FORMATS = (".png", ".jpg", ".jpeg")


class ThumbnailManager:
    """Thumbnail manager (global templates + user-specific)."""

    def __init__(self) -> None:
        self._builder = get_path_builder()

    # ------------------------------------------------------------ key helpers
    def get_user_thumbnails_dir(self, user_slug: int) -> Path:
        """Return a builder Path (callers can convert via ``to_storage_key``)."""
        return self._builder.user_thumbnails_dir(user_slug)

    def get_global_templates_dir(self) -> Path:
        return self._builder.shared_thumbnails_dir()

    def _user_key(self, user_slug: int, filename: str) -> str:
        return to_storage_key(self.get_user_thumbnails_dir(user_slug) / filename)

    def _shared_key(self, filename: str) -> str:
        return to_storage_key(self._builder.shared_thumbnail(filename))

    # ------------------------------------------------------------ initialization
    async def initialize_user_thumbnails(self, user_slug: int, copy_templates: bool = True) -> None:
        """For a new user, copy shared template thumbnails into their personal prefix.

        Existing user-side files are not overwritten.
        """
        if not copy_templates:
            logger.info(f"Skipped template copy for user {user_slug}")
            return

        storage = get_storage_backend()
        try:
            template_keys = await storage.list_keys(to_storage_key(self.get_global_templates_dir()))
        except NotImplementedError:
            logger.warning("Storage backend does not support list_keys; skipping template initialization")
            return

        copied = 0
        for template_key in template_keys:
            name = template_key.rsplit("/", 1)[-1]
            if Path(name).suffix.lower() not in SUPPORTED_IMAGE_FORMATS:
                continue
            user_key = self._user_key(user_slug, name)
            if await storage.exists(user_key):
                continue
            try:
                content = await storage.load(template_key)
                await storage.save(user_key, content)
                copied += 1
            except Exception as e:
                logger.warning(f"Copy failed for {name}: {e}")

        logger.info(f"Initialized user {user_slug}: copied {copied} templates")

    # ----------------------------------------------------------------- lookup
    async def get_thumbnail_key(
        self,
        user_slug: int,
        thumbnail_name: str,
        fallback_to_template: bool = True,
    ) -> str | None:
        """Resolve a thumbnail to a storage key (user first, then shared fallback)."""
        thumbnail_name = Path(thumbnail_name).name
        storage = get_storage_backend()

        user_key = self._user_key(user_slug, thumbnail_name)
        if await storage.exists(user_key):
            return user_key

        if fallback_to_template:
            shared_key = self._shared_key(thumbnail_name)
            if await storage.exists(shared_key):
                return shared_key

        logger.warning(f"Thumbnail not found: {thumbnail_name} for user {user_slug}")
        return None

    async def list_user_thumbnails(self, user_slug: int) -> list[str]:
        """Return storage keys of every supported-format thumbnail for ``user_slug``."""
        storage = get_storage_backend()
        try:
            keys = await storage.list_keys(to_storage_key(self.get_user_thumbnails_dir(user_slug)))
        except NotImplementedError:
            return []
        return sorted(k for k in keys if Path(k).suffix.lower() in SUPPORTED_IMAGE_FORMATS)

    # ----------------------------------------------------------------- writes
    async def write_user_thumbnail(self, user_slug: int, filename: str, content: bytes) -> str:
        """Write thumbnail bytes to storage. Returns the storage key."""
        if Path(filename).suffix.lower() not in SUPPORTED_IMAGE_FORMATS:
            supported = ", ".join(SUPPORTED_IMAGE_FORMATS)
            raise ValueError(f"Unsupported format: {Path(filename).suffix}. Supported: {supported}")
        key = self._user_key(user_slug, filename)
        await get_storage_backend().save(key, content)
        logger.info(f"Wrote thumbnail for user {user_slug}: {filename}")
        return key

    async def thumbnail_exists(self, user_slug: int, filename: str) -> bool:
        """True iff a user-specific thumbnail with this name is in storage."""
        return await get_storage_backend().exists(self._user_key(user_slug, filename))

    async def delete_user_thumbnail(self, user_slug: int, thumbnail_name: str) -> bool:
        """Delete a user-specific thumbnail. Returns False if it didn't exist."""
        thumbnail_name = Path(thumbnail_name).name
        return await get_storage_backend().delete(self._user_key(user_slug, thumbnail_name))

    # ------------------------------------------------------------------ info
    async def get_thumbnail_info(self, storage_key: str) -> dict[str, int | float]:
        """Return ``{size_bytes, size_kb}`` for a stored thumbnail key."""
        storage = get_storage_backend()
        if not await storage.exists(storage_key):
            return {"size_bytes": 0, "size_kb": 0.0}
        size = await storage.get_size(storage_key)
        return {"size_bytes": size, "size_kb": round(size / 1024, 2)}


# Global instance
_thumbnail_manager: ThumbnailManager | None = None


def get_thumbnail_manager() -> ThumbnailManager:
    """Get global thumbnail manager instance."""
    global _thumbnail_manager
    if _thumbnail_manager is None:
        _thumbnail_manager = ThumbnailManager()
    return _thumbnail_manager
