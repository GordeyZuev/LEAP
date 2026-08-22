"""Single deep-merge implementation for configuration dicts."""

from __future__ import annotations

import copy
from typing import Any


def deep_merge(base: dict[str, Any], override: dict[str, Any], *, skip_none: bool = False) -> dict[str, Any]:
    """Deep merge ``override`` into ``base``.

    When ``skip_none`` is True, None values in override are ignored (template merge semantics).
    """
    result = copy.deepcopy(base)
    for key, value in override.items():
        if skip_none and value is None:
            continue
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value, skip_none=skip_none)
        else:
            result[key] = copy.deepcopy(value)
    return result
