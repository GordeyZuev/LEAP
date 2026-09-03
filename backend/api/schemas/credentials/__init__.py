"""Credential schemas for validation."""

from .platform_credentials import (
    MtsLinkCredentialsManual,
    VKCredentialsManual,
    YandexDiskCredentialsManual,
    YouTubeCredentialsManual,
    ZoomCredentialsManual,
)
from .request import CredentialCreateRequest, CredentialUpdateRequest
from .response import (
    CredentialCheckResponse,
    CredentialListItem,
    CredentialListResponse,
    CredentialResponse,
    CredentialStatusResponse,
)
from .yandex_disk_browse import YandexDiskBrowseItem, YandexDiskBrowseResponse

__all__ = [
    "CredentialCheckResponse",
    "CredentialCreateRequest",
    "CredentialListItem",
    "CredentialListResponse",
    "CredentialResponse",
    "CredentialStatusResponse",
    "CredentialUpdateRequest",
    "MtsLinkCredentialsManual",
    "VKCredentialsManual",
    "YandexDiskBrowseItem",
    "YandexDiskBrowseResponse",
    "YandexDiskCredentialsManual",
    "YouTubeCredentialsManual",
    "ZoomCredentialsManual",
]
