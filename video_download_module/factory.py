"""Downloader factory -- creates the right downloader based on source type."""

from file_storage.path_builder import StoragePathBuilder
from models.recording import SourceType

from .core.base import BaseDownloader


def create_downloader(
    source_type: str,
    user_slug: int,
    storage_builder: StoragePathBuilder | None = None,
    **kwargs,
) -> BaseDownloader:
    """Create a downloader instance for the given source type."""
    match source_type:
        case SourceType.ZOOM:
            from .downloader import ZoomDownloader

            return ZoomDownloader(user_slug=user_slug, storage_builder=storage_builder)

        case SourceType.EXTERNAL_URL | SourceType.YOUTUBE:
            from .platforms.ytdlp.downloader import YtDlpDownloader

            return YtDlpDownloader(user_slug=user_slug, storage_builder=storage_builder, **kwargs)

        case SourceType.YANDEX_DISK:
            from .platforms.yadisk.downloader import YandexDiskDownloader

            return YandexDiskDownloader(user_slug=user_slug, storage_builder=storage_builder, **kwargs)

        case _:
            raise ValueError(f"Unsupported source type for download: {source_type}")
