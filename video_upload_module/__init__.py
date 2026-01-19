"""Video upload module for YouTube and VK platforms."""

from .core import BaseUploader, UploadManager, UploadResult
from .platforms import VKUploader, YouTubeUploader

__all__ = [
    # Core classes
    "BaseUploader",
    "UploadManager",
    "UploadResult",
    # Platform uploaders
    "VKUploader",
    "YouTubeUploader",
]
