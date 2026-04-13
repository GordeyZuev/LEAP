"""Replace legacy ``| leap_dt(...)`` fragments in template strings (migration 019 + unit tests).

Only ``record_time`` and ``publish_time`` bases are rewritten; other uses are left unchanged
so operators can grep remaining ``leap_dt`` after upgrade.
"""

from __future__ import annotations

import json
import re
from typing import Any, Final

# ``record_time`` / ``publish_time`` then ``|`` then ``leap_dt``; capture quote char and format body.
_LEAP_DT_SUB: Final[re.Pattern[str]] = re.compile(
    r"\{\{\s*(record_time|publish_time)\s*\|\s*leap_dt\s*\(\s*(['\"])(.*?)\2\s*\)\s*\}\}",
    re.DOTALL,
)


def _normalize_fmt(fmt: str) -> str:
    s = fmt.strip()
    low = s.lower()
    if low in ("date", "time", "datetime"):
        return low
    return re.sub(r"\s+", " ", s)


def _map_leap_fmt_to_var(base: str, fmt: str) -> str | None:
    """Map legacy leap_dt format string to a canonical context variable name."""
    f = _normalize_fmt(fmt)
    prefix = "record" if base == "record_time" else "publish"

    if f == "date":
        return f"{prefix}_date_iso"
    if f == "time":
        return f"{prefix}_time_hm"
    if f == "datetime":
        return f"{prefix}_datetime_iso"
    if f == "DD.MM.YY":
        return f"{prefix}_date_short"
    if f == "DD.MM.YYYY":
        return f"{prefix}_date"
    if f in ("DD.MM.YYYY hh:mm", "DD.MM.YYYY HH:mm"):
        return f"{prefix}_datetime"
    if f == "YYYY-MM-DD":
        return f"{prefix}_date_iso"
    return None


def replace_leap_dt_in_string(template: str) -> tuple[str, int, int]:
    """
    Replace ``{{ record_time|leap_dt('...') }}`` / ``publish_time`` with canonical variables.

    Returns:
        (new_string, n_replaced, n_unmapped) where n_unmapped counts matches with unknown format.
    """
    if not template or "leap_dt" not in template:
        return template, 0, 0

    replaced = 0
    unmapped = 0

    def _repl(m: re.Match[str]) -> str:
        nonlocal replaced, unmapped
        base = m.group(1)
        fmt_raw = m.group(3)
        target = _map_leap_fmt_to_var(base, fmt_raw)
        if target is None:
            unmapped += 1
            return m.group(0)
        replaced += 1
        return f"{{{{ {target} }}}}"

    out = _LEAP_DT_SUB.sub(_repl, template)
    return out, replaced, unmapped


def migrate_json_template_strings(obj: Any) -> tuple[Any, int, int]:
    """
    Recursively walk JSON-like structures; transform template strings containing leap_dt.

    Returns:
        (migrated_obj, total_replaced, total_unmapped)
    """
    total_r = 0
    total_u = 0

    def walk(x: Any) -> Any:
        nonlocal total_r, total_u
        if isinstance(x, dict):
            return {k: walk(v) for k, v in x.items()}
        if isinstance(x, list):
            return [walk(i) for i in x]
        if isinstance(x, str) and "leap_dt" in x:
            new_s, r, u = replace_leap_dt_in_string(x)
            total_r += r
            total_u += u
            return new_s
        return x

    return walk(obj), total_r, total_u


def json_equal(a: Any, b: Any) -> bool:
    """Stable JSON equality for migration idempotency checks."""
    return json.dumps(a, sort_keys=True, default=str) == json.dumps(b, sort_keys=True, default=str)
