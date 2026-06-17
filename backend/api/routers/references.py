"""Reference data endpoints: static enumerations exposed to the frontend."""

import datetime
import zoneinfo

from fastapi import APIRouter, Depends

from api.auth.dependencies import get_current_user
from api.schemas.auth import UserInDB
from api.schemas.template.preset_metadata import display_config_defaults_payload

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


def _build_timezones() -> list[dict]:
    # Use a fixed reference date (northern-hemisphere winter) so offsets reflect
    # standard time, not DST, giving stable sort order year-round.
    ref = datetime.datetime(2024, 1, 15, tzinfo=datetime.UTC)
    rows = []
    for name in zoneinfo.available_timezones():
        try:
            tz = zoneinfo.ZoneInfo(name)
        except zoneinfo.ZoneInfoNotFoundError:
            continue
        offset = ref.astimezone(tz).utcoffset()
        if offset is None:
            continue
        total_minutes = int(offset.total_seconds() // 60)
        h, m = divmod(abs(total_minutes), 60)
        sign = "+" if total_minutes >= 0 else "−"
        offset_str = f"UTC{sign}{h}" if m == 0 else f"UTC{sign}{h}:{m:02d}"
        rows.append((total_minutes, name, {"value": name, "label": f"{offset_str} {name}"}))
    rows.sort(key=lambda x: (x[0], x[1]))
    return [r[2] for r in rows]


_TIMEZONES = _build_timezones()


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


@router.get("/display-config-defaults")
async def get_display_config_defaults(
    _: UserInDB = Depends(get_current_user),
) -> dict:
    """Effective defaults and validation bounds for topics_display / questions_display editors."""
    return display_config_defaults_payload()
