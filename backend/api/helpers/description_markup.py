"""Description markup: storage markers → plain text for platform uploads.

Markers (not shown as UX): **bold** *italic* ++underline++ ~~strike~~ [label](url).
Jinja ``{{ var }}`` is left untouched (render Jinja first, then strip).
"""

from __future__ import annotations

import re
from typing import Final

_JINJA_RE: Final[re.Pattern[str]] = re.compile(r"\{\{[^{}]*\}\}")
_BOLD_RE: Final[re.Pattern[str]] = re.compile(r"\*\*(.+?)\*\*", re.DOTALL)
_UNDER_RE: Final[re.Pattern[str]] = re.compile(r"\+\+(.+?)\+\+", re.DOTALL)
_STRIKE_RE: Final[re.Pattern[str]] = re.compile(r"~~(.+?)~~", re.DOTALL)
_ITALIC_RE: Final[re.Pattern[str]] = re.compile(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", re.DOTALL)
_LINK_RE: Final[re.Pattern[str]] = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")


def _strip_line_markers(text: str) -> str:
    """Strip marks that must not span newlines, per line."""
    parts: list[str] = []
    for line in text.split("\n"):
        prev = None
        cur = line
        while prev != cur:
            prev = cur
            cur = _BOLD_RE.sub(r"\1", cur)
            cur = _UNDER_RE.sub(r"\1", cur)
            cur = _STRIKE_RE.sub(r"\1", cur)
            cur = _LINK_RE.sub(lambda m: m.group(1) if m.group(1) == m.group(2) else f"{m.group(1)} {m.group(2)}", cur)
            cur = _ITALIC_RE.sub(r"\1", cur)
        parts.append(cur)
    return "\n".join(parts)


def markup_to_plain(src: str) -> str:
    """Remove description markers; keep whitespace, autolinks, and Jinja tokens."""
    if not src:
        return src
    chunks: list[str] = []
    last = 0
    for m in _JINJA_RE.finditer(src):
        if m.start() > last:
            chunks.append(_strip_line_markers(src[last : m.start()]))
        chunks.append(m.group(0))
        last = m.end()
    if last < len(src):
        chunks.append(_strip_line_markers(src[last:]))
    return "".join(chunks)
