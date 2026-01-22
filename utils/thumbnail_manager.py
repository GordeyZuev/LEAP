"""User thumbnails manager"""

import shutil
from pathlib import Path

from logger import get_logger

logger = get_logger()


class ThumbnailManager:
    """Thumbnail manager (global templates + user-specific)"""

    def __init__(self, base_media_dir: str = "media"):
        """
        Thumbnail manager initialization.

        Args:
            base_media_dir: Base directory for media files
        """
        self.base_media_dir = Path(base_media_dir)
        self.templates_dir = self.base_media_dir / "templates" / "thumbnails"

    def get_user_thumbnails_dir(self, user_id: int) -> Path:
        """Get user thumbnails directory."""
        return self.base_media_dir / f"user_{user_id}" / "thumbnails"

    def get_global_templates_dir(self) -> Path:
        """Get global template thumbnails directory."""
        return self.templates_dir

    def ensure_user_thumbnails_dir(self, user_id: int) -> None:
        """Create user thumbnails directory."""
        user_thumbs_dir = self.get_user_thumbnails_dir(user_id)
        user_thumbs_dir.mkdir(parents=True, exist_ok=True)

    def initialize_user_thumbnails(self, user_id: int, copy_templates: bool = True) -> None:
        """
        Initialize thumbnails for a new user.

        Args:
            user_id: User ID
            copy_templates: Copy global templates to user folder
        """
        user_thumbs_dir = self.get_user_thumbnails_dir(user_id)

        # Create directory
        self.ensure_user_thumbnails_dir(user_id)

        # Copy templates if needed
        if copy_templates and self.templates_dir.exists():
            copied_count = 0
            for template_file in self.templates_dir.glob("*.png"):
                target_file = user_thumbs_dir / template_file.name

                if not target_file.exists():
                    try:
                        shutil.copy2(template_file, target_file)
                        copied_count += 1
                    except Exception as e:
                        logger.warning(f"Failed to copy template {template_file.name}: {e}")

            logger.info(f"Initialized thumbnails for user {user_id}: {copied_count} templates copied.")
        else:
            logger.info(f"Created empty thumbnails directory for user {user_id}.")

    def get_thumbnail_path(
        self,
        user_id: int,
        thumbnail_name: str,
        fallback_to_template: bool = True,
    ) -> Path | None:
        """
        Get path to thumbnail (first check user, then templates).

        Args:
            user_id: User ID
            thumbnail_name: Thumbnail file name (e.g. "ml_extra.png")
            fallback_to_template: Search in global templates if not found in user folder

        Returns:
            Path to thumbnail or None if not found
        """
        # Normalize file name (remove path prefixes if any)
        thumbnail_name = Path(thumbnail_name).name

        # 1. Check user folder
        user_thumbnail = self.get_user_thumbnails_dir(user_id) / thumbnail_name
        if user_thumbnail.exists():
            logger.debug(f"Found user thumbnail: {user_thumbnail}")
            return user_thumbnail

        # 2. Fallback to global templates
        if fallback_to_template:
            template_thumbnail = self.templates_dir / thumbnail_name
            if template_thumbnail.exists():
                logger.debug(f"Using template thumbnail: {template_thumbnail}")
                return template_thumbnail

        logger.warning(f"Thumbnail not found: {thumbnail_name} for user {user_id}")
        return None

    def list_user_thumbnails(self, user_id: int) -> list[Path]:
        """
        Get list of all user thumbnails.

        Args:
            user_id: User ID

        Returns:
            List of thumbnail paths
        """
        user_thumbs_dir = self.get_user_thumbnails_dir(user_id)

        if not user_thumbs_dir.exists():
            return []

        return sorted(user_thumbs_dir.glob("*.png"))

    def list_template_thumbnails(self) -> list[Path]:
        """
        Get list of all global template thumbnails.

        Returns:
            List of template paths
        """
        if not self.templates_dir.exists():
            return []

        return sorted(self.templates_dir.glob("*.png"))

    def upload_user_thumbnail(
        self,
        user_id: int,
        source_path: Path | str,
        thumbnail_name: str | None = None,
    ) -> Path:
        """
        Upload user thumbnail.

        Args:
            user_id: User ID
            source_path: Path to source file
            thumbnail_name: Name to save (if None - use original)

        Returns:
            Path to saved thumbnail

        Raises:
            FileNotFoundError: If source file not found
            ValueError: If format not supported
        """
        source_path = Path(source_path)

        if not source_path.exists():
            raise FileNotFoundError(f"Source thumbnail not found: {source_path}")

        # Check format
        if source_path.suffix.lower() not in [".png", ".jpg", ".jpeg"]:
            raise ValueError(f"Unsupported thumbnail format: {source_path.suffix}")

        # Define file name
        if thumbnail_name is None:
            thumbnail_name = source_path.name

        # Ensure directory exists
        self.ensure_user_thumbnails_dir(user_id)

        # Save file
        target_path = self.get_user_thumbnails_dir(user_id) / thumbnail_name
        shutil.copy2(source_path, target_path)

        logger.info(f"Uploaded thumbnail for user {user_id}: {thumbnail_name}")
        return target_path

    def delete_user_thumbnail(self, user_id: int, thumbnail_name: str) -> bool:
        """
        Delete user thumbnail.

        Args:
            user_id: User ID
            thumbnail_name: Thumbnail file name

        Returns:
            True if deleted successfully, False if not found
        """
        thumbnail_name = Path(thumbnail_name).name
        thumbnail_path = self.get_user_thumbnails_dir(user_id) / thumbnail_name

        if not thumbnail_path.exists():
            logger.warning(f"Thumbnail not found for deletion: {thumbnail_path}")
            return False

        try:
            thumbnail_path.unlink()
            logger.info(f"Deleted thumbnail for user {user_id}: {thumbnail_name}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete thumbnail {thumbnail_path}: {e}")
            return False

    def get_thumbnail_info(self, thumbnail_path: Path) -> dict:
        """
        Get thumbnail information (size and modification date).

        Args:
            thumbnail_path: Path to thumbnail

        Returns:
            Dictionary with information (size_bytes, size_kb, modified_at)
        """
        if not thumbnail_path.exists():
            return {
                "size_bytes": 0,
                "size_kb": 0.0,
                "modified_at": 0.0,
            }

        stat = thumbnail_path.stat()

        return {
            "size_bytes": stat.st_size,
            "size_kb": round(stat.st_size / 1024, 2),
            "modified_at": stat.st_mtime,
        }


# Global instance
_thumbnail_manager: ThumbnailManager | None = None


def get_thumbnail_manager(base_media_dir: str = "media") -> ThumbnailManager:
    """Get global thumbnail manager instance."""
    global _thumbnail_manager
    if _thumbnail_manager is None:
        _thumbnail_manager = ThumbnailManager(base_media_dir)
    return _thumbnail_manager
