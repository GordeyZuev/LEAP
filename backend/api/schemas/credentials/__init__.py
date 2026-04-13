"""Credential schemas for validation."""

from .platform_credentials import (
    VKCredentialsManual,
    YouTubeCredentialsManual,
    ZoomCredentialsManual,
)
from .request import CredentialCreateRequest, CredentialUpdateRequest
from .response import CredentialListItem, CredentialListResponse, CredentialResponse, CredentialStatusResponse

__all__ = [
    "CredentialCreateRequest",
    "CredentialListItem",
    "CredentialListResponse",
    "CredentialResponse",
    "CredentialStatusResponse",
    "CredentialUpdateRequest",
    "VKCredentialsManual",
    "YouTubeCredentialsManual",
    "ZoomCredentialsManual",
]
