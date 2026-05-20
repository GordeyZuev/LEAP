"""Reference data endpoints: static enumerations exposed to the frontend."""

from fastapi import APIRouter, Depends

from api.auth.dependencies import get_current_user
from api.schemas.auth import UserInDB

router = APIRouter(prefix="/api/v1/references", tags=["References"])

_LANGUAGES = [
    {"value": "ru", "label": "Русский"},
    {"value": "en", "label": "English"},
    {"value": "auto", "label": "Auto"},
]

_GRANULARITIES = [
    {"value": "short", "label": "Short"},
    {"value": "medium", "label": "Medium"},
    {"value": "long", "label": "Long"},
]

_QUALITIES = [
    {"value": "high", "label": "High"},
    {"value": "medium", "label": "Medium"},
    {"value": "low", "label": "Low"},
]

_PLATFORMS = [
    {"value": "youtube", "label": "YouTube"},
    {"value": "vk_video", "label": "VK Video"},
    {"value": "yandex_disk", "label": "Yandex Disk"},
    {"value": "zoom", "label": "Zoom"},
]

_TIMEZONES = [
    {"value": "Pacific/Honolulu", "label": "UTC−10  Pacific/Honolulu"},
    {"value": "America/Anchorage", "label": "UTC−9   America/Anchorage"},
    {"value": "America/Los_Angeles", "label": "UTC−8   America/Los_Angeles"},
    {"value": "America/Denver", "label": "UTC−7   America/Denver"},
    {"value": "America/Chicago", "label": "UTC−6   America/Chicago"},
    {"value": "America/New_York", "label": "UTC−5   America/New_York"},
    {"value": "America/Sao_Paulo", "label": "UTC−3   America/Sao_Paulo"},
    {"value": "Europe/London", "label": "UTC+0   Europe/London"},
    {"value": "Europe/Berlin", "label": "UTC+1   Europe/Berlin"},
    {"value": "Europe/Helsinki", "label": "UTC+2   Europe/Helsinki"},
    {"value": "Europe/Moscow", "label": "UTC+3   Europe/Moscow"},
    {"value": "Asia/Dubai", "label": "UTC+4   Asia/Dubai"},
    {"value": "Asia/Tashkent", "label": "UTC+5   Asia/Tashkent"},
    {"value": "Asia/Kolkata", "label": "UTC+5:30 Asia/Kolkata"},
    {"value": "Asia/Almaty", "label": "UTC+6   Asia/Almaty"},
    {"value": "Asia/Bangkok", "label": "UTC+7   Asia/Bangkok"},
    {"value": "Asia/Shanghai", "label": "UTC+8   Asia/Shanghai"},
    {"value": "Asia/Tokyo", "label": "UTC+9   Asia/Tokyo"},
    {"value": "Australia/Sydney", "label": "UTC+10  Australia/Sydney"},
    {"value": "Pacific/Auckland", "label": "UTC+12  Pacific/Auckland"},
]


@router.get("/languages")
async def get_languages(_: UserInDB = Depends(get_current_user)) -> list[dict]:
    """Supported transcription languages."""
    return _LANGUAGES


@router.get("/granularities")
async def get_granularities(_: UserInDB = Depends(get_current_user)) -> list[dict]:
    """Topic segmentation granularity options."""
    return _GRANULARITIES


@router.get("/qualities")
async def get_qualities(_: UserInDB = Depends(get_current_user)) -> list[dict]:
    """Video download quality options."""
    return _QUALITIES


@router.get("/platforms")
async def get_platforms(_: UserInDB = Depends(get_current_user)) -> list[dict]:
    """Supported upload platforms."""
    return _PLATFORMS


@router.get("/timezones")
async def get_timezones(_: UserInDB = Depends(get_current_user)) -> list[dict]:
    """Supported timezones."""
    return _TIMEZONES
