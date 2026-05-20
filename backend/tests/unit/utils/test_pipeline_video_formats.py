"""Pipeline ingress sniff + whitelist helpers."""

from pathlib import Path

import pytest

from utils.pipeline_video_formats import (
    EBML_MAGIC,
    ingress_suffix_from_zoom_video_file_type,
    ingress_validate_saved_media,
    pipeline_ingress_suffixes_from_settings_formats,
    sniff_container_kind,
    strict_suffix_from_source_name,
)


@pytest.mark.unit
class TestSniffContainerKind:
    def test_detects_ebml(self) -> None:
        """EBML magic maps to ebml."""
        blob = EBML_MAGIC + b"\xff" * 100
        assert sniff_container_kind(blob) == "ebml"

    def test_detects_iso_bmff_via_ftyp_at_offset_4(self) -> None:
        """Standard MP4: ftyp box type at bytes [4:8]."""
        blob = b"\x00\x00\x00\x18ftypisom\x00\x00\x00\x00iso6mp41" + b"\x00" * 4000
        assert sniff_container_kind(blob) == "iso_bmff"

    def test_detects_iso_bmff_via_ftyp_fallback_substring(self) -> None:
        """ftyp found elsewhere in first 4096 bytes still detected."""
        blob = b"\x00" * 16 + b"ftypisom" + b"\x00" * 4000
        assert sniff_container_kind(blob) == "iso_bmff"

    def test_unknown_too_short(self) -> None:
        """Input shorter than 8 bytes returns unknown."""
        assert sniff_container_kind(b"abcdefg") == "unknown"


@pytest.mark.unit
class TestIngressValidateSavedMedia:
    def test_accepts_webm_bytes_with_matching_suffix(self, tmp_path: Path) -> None:
        """WebM bytes with matching filename pass."""
        vp = tmp_path / "blob.webm"
        vp.write_bytes(EBML_MAGIC + b"z" * 2000)
        allowed = ["mp4", "webm", "mkv", "mov"]
        assert ingress_validate_saved_media(vp, None, None, "file.webm", allowed) is True

    def test_rejects_html(self, tmp_path: Path) -> None:
        """HTML payload fails."""
        vp = tmp_path / "bad.mp4"
        vp.write_bytes(b"<!DOCTYPE html><title>x</title>" + b"z" * 2000)
        assert ingress_validate_saved_media(vp, None, None, "file.mp4", ["mp4", "webm"]) is False

    def test_rejects_webm_filename_when_body_is_not_ebml(self, tmp_path: Path) -> None:
        """Webm name with ISO BMFF body fails EBML rule."""
        vp = tmp_path / "x.webm"
        isoish = b"\x00\x00\x00\x18ftypisom\x00\x00\x00\x00iso6mp41" + b"\x00" * 2000
        vp.write_bytes(isoish)
        assert ingress_validate_saved_media(vp, None, None, "file.webm", ["mp4", "webm", "mov"]) is False

    def test_rejects_mp4_name_with_ebml_body(self, tmp_path: Path) -> None:
        """EBML payload named .mp4 must be rejected — container/extension mismatch."""
        vp = tmp_path / "source.mp4"
        vp.write_bytes(EBML_MAGIC + b"z" * 2000)
        ok = ingress_validate_saved_media(vp, None, None, "remote.mp4", ["mp4", "webm", "mkv", "mov"])
        assert ok is False

    def test_rejects_mov_name_with_ebml_body(self, tmp_path: Path) -> None:
        """EBML payload named .mov must be rejected — container/extension mismatch."""
        vp = tmp_path / "source.mov"
        vp.write_bytes(EBML_MAGIC + b"z" * 2000)
        ok = ingress_validate_saved_media(vp, None, None, "remote.mov", ["mp4", "webm", "mkv", "mov"])
        assert ok is False


@pytest.mark.unit
def test_strict_suffix_from_source_name_raises_on_unknown_extension() -> None:
    """Unknown extension raises ValueError."""
    allowed = frozenset({".mp4"})
    with pytest.raises(ValueError):
        strict_suffix_from_source_name("x.webm", allowed)


@pytest.mark.unit
def test_zoom_video_file_type_mapping() -> None:
    """Zoom file_type MP4 maps to allowed suffix."""
    allowed = frozenset({".mp4"})
    assert ingress_suffix_from_zoom_video_file_type("MP4", allowed) == ".mp4"


@pytest.mark.unit
def test_formats_list_empty_fallback() -> None:
    """Empty format list uses storage default video formats."""
    s = pipeline_ingress_suffixes_from_settings_formats([])
    assert ".mp4" in s and ".webm" in s
