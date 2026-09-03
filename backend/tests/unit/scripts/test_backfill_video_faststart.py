from pathlib import Path

import pytest

from scripts.backfill_video_faststart import faststart_key, top_level_atoms

pytestmark = pytest.mark.unit


def _atom(kind: bytes, payload: bytes = b"") -> bytes:
    return (8 + len(payload)).to_bytes(4, "big") + kind + payload


def test_faststart_key_preserves_parent_and_suffix() -> None:
    assert faststart_key("users/u/recordings/4/video.mp4") == "users/u/recordings/4/video.faststart.mp4"


def test_top_level_atoms_reads_mp4_layout(tmp_path: Path) -> None:
    media = tmp_path / "video.mp4"
    media.write_bytes(_atom(b"ftyp") + _atom(b"moov", b"index") + _atom(b"mdat", b"content"))
    assert top_level_atoms(media) == ["ftyp", "moov", "mdat"]


def test_top_level_atoms_rejects_broken_size(tmp_path: Path) -> None:
    media = tmp_path / "video.mp4"
    media.write_bytes((100).to_bytes(4, "big") + b"moov")
    with pytest.raises(ValueError, match="Invalid MP4 atom"):
        top_level_atoms(media)
