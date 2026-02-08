from enum import StrEnum


class InputPlatform(StrEnum):
    ZOOM = "zoom"
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
    YOUTUBE = "youtube"
    VK_VIDEO = "vk_video"
    YANDEX_DISK = "yandex_disk"
    FIREWORKS = "fireworks"
    DEEPSEEK = "deepseek"
