"""Credential schemas for validation."""

from .platform_credentials import (
    VKCredentialsManual,
    YandexDiskCredentialsManual,
    YouTubeCredentialsManual,
    ZoomCredentialsManual,
)
from .request import CredentialCreateRequest, CredentialUpdateRequest
from .response import CredentialListItem, CredentialListResponse, CredentialResponse, CredentialStatusResponse
from .yandex_disk_browse import YandexDiskBrowseItem, YandexDiskBrowseResponse

__all__ = [
    "CredentialCreateRequest",
    "CredentialListItem",
    "CredentialListResponse",
    "CredentialResponse",
    "CredentialStatusResponse",
    "CredentialUpdateRequest",
    "VKCredentialsManual",
    "YandexDiskBrowseItem",
    "YandexDiskBrowseResponse",
    "YandexDiskCredentialsManual",
    "YouTubeCredentialsManual",
    "ZoomCredentialsManual",
]
