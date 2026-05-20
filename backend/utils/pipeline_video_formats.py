"""Pipeline ingress: allowed container suffixes + magic-byte sniff helpers (download validation)."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from config.settings import STORAGE_DEFAULT_VIDEO_FORMATS
from logger import get_logger

_logger = get_logger(__name__)

EBML_MAGIC = b"\x1a\x45\xdf\xa3"

ContainerSniffKind = Literal["ebml", "iso_bmff", "unknown"]


def format_strings_to_suffix_set(formats: list[str]) -> frozenset[str]:
    parts: set[str] = set()
    for raw in formats:
        s = raw.strip().lower().lstrip(".")
        if s:
            parts.add(f".{s}")
    return frozenset(parts)


def pipeline_ingress_suffixes_from_settings_formats(formats: list[str]) -> frozenset[str]:
    """Map ``storage.supported_video_formats`` (or []) to normalized ``frozenset`` of suffixes."""
    if not formats:
        return format_strings_to_suffix_set(list(STORAGE_DEFAULT_VIDEO_FORMATS))
    return format_strings_to_suffix_set(formats)


def sniff_container_kind(first_chunk: bytes) -> ContainerSniffKind:
    if len(first_chunk) < 8:
        return "unknown"
    if first_chunk[:4] == EBML_MAGIC:
        return "ebml"
    # ISO BMFF: the ftyp box type is at bytes [4:8] in well-formed files.
    # Substring fallback covers rare encoders that prepend extra bytes.
    if first_chunk[4:8] == b"ftyp" or b"ftyp" in first_chunk[8:4096]:
        return "iso_bmff"
    return "unknown"


def strict_suffix_from_source_name(name: str | None, allowed: frozenset[str]) -> str:
    """Return normalized suffix (.mp4, .webm, …). Missing name/ZOOM-style → `.mp4`. Unknown ext → ValueError."""
    if not name:
        return ".mp4"
    suf = Path(name).suffix.lower()
    if not suf:
        return ".mp4"
    if suf not in allowed:
        msg = f"Ingress extension {suf!r} is not allowed (pipeline whitelist: {sorted(allowed)})"
        raise ValueError(msg)
    return suf


def ingress_suffix_from_zoom_video_file_type(file_type: str | None, allowed: frozenset[str]) -> str:
    """Zoom API ``file_type`` values look like ``MP4``; normalize to a pipeline suffix when allowed."""

    if not file_type or not str(file_type).strip():
        return ".mp4"
    ext = "." + str(file_type).strip().lower().lstrip(".")
    return ext if ext in allowed else ".mp4"


def find_source_video_in_recording_dir(recording_root: Path, ingress_suffixes: frozenset[str]) -> Path | None:
    """Pick first existing ``source.<ext>`` for known ingress suffixes; fall back to legacy ``source.mp4``."""
    for suf in ingress_suffixes:
        candidate = recording_root / f"source{suf}"
        if candidate.is_file():
            return candidate
    legacy = recording_root / "source.mp4"
    if legacy.is_file():
        return legacy
    return None


def ingress_validate_saved_media(
    filepath: Path,
    expected_size: int | None,
    total_size: int | None,
    source_name: str | None,
    ingress_format_strings: list[str],
) -> bool:
    """
    Size + sniff + whitelist checks after a download/upload save (same rules as ``BaseDownloader._validate_file``).
    """

    allowed_suffixes = pipeline_ingress_suffixes_from_settings_formats(ingress_format_strings)

    if not filepath.exists():
        return False

    file_size = filepath.stat().st_size
    if file_size < 1024:
        return False

    reference_size = total_size or expected_size
    if reference_size:
        if file_size < reference_size:
            _logger.warning(f"Incomplete: {(file_size / reference_size * 100):.1f}%")
            return False
        if file_size > reference_size * 1.1:
            _logger.warning("File size exceeds expected by >10%")

    try:
        with filepath.open("rb") as handle:
            first_chunk = handle.read(4096)

        lc = first_chunk.lower()
        if b"<html" in lc or b"<!doctype html" in lc:
            _logger.error("Downloaded HTML instead of media file")
            return False

        sniff_kind = sniff_container_kind(first_chunk)
        if sniff_kind == "unknown":
            _logger.error(
                "Unsupported or unknown binary container signature (pipeline ingress whitelist applies)",
            )
            return False

        if source_name:
            src_suffix = Path(source_name).suffix.lower()
            if src_suffix and src_suffix not in allowed_suffixes:
                _logger.error(
                    "Ingress rejected: extension %r not in pipeline whitelist %s",
                    src_suffix,
                    sorted(allowed_suffixes),
                )
                return False
            if src_suffix in {".webm", ".mkv"}:
                if sniff_kind != "ebml":
                    _logger.error(
                        "Ingress rejected: claimed %r but body is not EBML (got %r)",
                        src_suffix,
                        sniff_kind,
                    )
                    return False
            if src_suffix in {".mp4", ".mov"}:
                if sniff_kind == "ebml":
                    _logger.error(
                        "Ingress rejected: claimed %r but payload is EBML/WebM — extension and container mismatch",
                        src_suffix,
                    )
                    return False
                if sniff_kind != "iso_bmff":
                    _logger.error(
                        "Ingress rejected: expected ISO-like container for %s, got %s",
                        src_suffix,
                        sniff_kind,
                    )
                    return False
        elif sniff_kind not in {"ebml", "iso_bmff"}:
            return False

        return True
    except Exception as e:
        _logger.error(f"Validation error: {e}")
        return False
