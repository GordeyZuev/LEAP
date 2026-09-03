"""Shared enums: input/output platforms, credential types, topic granularity."""

from enum import StrEnum


class Granularity(StrEnum):
    """Topic extraction granularity: fewer/longer (short) vs more/shorter (long)."""

    SHORT = "short"
    MEDIUM = "medium"
    LONG = "long"


class InputPlatform(StrEnum):
    ZOOM = "zoom"
    MTS_LINK = "mts_link"
    YANDEX_DISK = "yandex_disk"
    VIDEO_URL = "video_url"
    LOCAL = "local"


class OutputPlatform(StrEnum):
    YOUTUBE = "youtube"
    VK_VIDEO = "vk_video"
    YANDEX_DISK = "yandex_disk"
    LOCAL = "local"


class CredentialPlatform(StrEnum):
    ZOOM = "zoom"
    MTS_LINK = "mts_link"
    YOUTUBE = "youtube"
    VK_VIDEO = "vk_video"
    YANDEX_DISK = "yandex_disk"
    ASSEMBLYAI = "assemblyai"
    DEEPSEEK = "deepseek"
