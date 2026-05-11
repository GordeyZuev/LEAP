#!/usr/bin/env -S uv run python
"""
End-to-end media check: ffprobe metadata vs. ffmpeg decode, plus common failure signatures.

Helps tell apart:
  - A short *valid* output (e.g. pipeline trim) vs. a *truncated* source (ffprobe overstates duration)
  - VP9+Opus muxed in .mp4 (may confuse desktop players even when ffmpeg decodes clean)

Usage (from backend/):
  uv run python scripts/diagnose_video_file.py /path/to/video.mp4
  uv run python scripts/diagnose_video_file.py /path/to/video.mp4 --full-decode

Requires ffmpeg and ffprobe on PATH.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path


def _ffprobe(path: Path) -> dict:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        raise RuntimeError("ffprobe not found in PATH")
    r = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if r.returncode != 0:
        raise RuntimeError(r.stderr or "ffprobe failed")
    return json.loads(r.stdout)


def _format_duration_s(seconds: float | None) -> str:
    if seconds is None:
        return "?"
    m, s = divmod(round(seconds), 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}h{m:02d}m{s:02d}s"
    return f"{m}m{s:02d}s"


def _last_time_from_ffmpeg_stats(stderr: str) -> float | None:
    """Parse last 'time=HH:MM:SS.xx' from ffmpeg stats output (best-effort)."""
    last: float | None = None
    for m in re.finditer(r"time=(\d+):(\d+):(\d+\.\d+)", stderr):
        h, mnt, s = m.group(1), m.group(2), m.group(3)
        last = int(h) * 3600 + int(mnt) * 60 + float(s)
    return last


def _decode_test(path: Path, full_decode: bool) -> tuple[int, str]:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg not found in PATH")
    if full_decode:
        # Stats in stderr show time= for last decoded frame (useful when mux breaks mid-file)
        args = [ffmpeg, "-hide_banner", "-i", str(path), "-f", "null", "-"]
    else:
        # Faster: decode first 60s only (misses late corruption)
        args = [ffmpeg, "-hide_banner", "-i", str(path), "-t", "60", "-f", "null", "-"]
    p = subprocess.run(
        args,
        capture_output=True,
        text=True,
        check=False,
    )
    return p.returncode, p.stderr


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    p.add_argument("file", type=Path, help="Video or audio file to check")
    p.add_argument(
        "--full-decode",
        action="store_true",
        help="Decode entire file (slow for large files; needed to detect late truncation)",
    )
    a = p.parse_args()
    path: Path = a.file
    if not path.is_file():
        print(f"Not a file: {path}", file=sys.stderr)
        return 2

    data = _ffprobe(path)
    fmt = data.get("format", {})
    dur = float(fmt["duration"]) if fmt.get("duration") else None
    size = int(fmt["size"]) if fmt.get("size") else None

    print(f"File: {path.resolve()}")
    print(f"Size: {size} bytes" if size is not None else "Size: ?")
    print(f"ffprobe format.duration: {dur:.3f}s ({_format_duration_s(dur)})" if dur else "ffprobe format.duration: ?")
    for s in data.get("streams", []):
        if s.get("codec_type") in ("video", "audio"):
            print(
                f"  stream {s.get('index')}: {s.get('codec_type')} "
                f"{s.get('codec_name', '?')} "
                f"duration={s.get('duration', 'n/a')}"
            )

    # Compatibility hint
    vcodecs = {s.get("codec_name") for s in data.get("streams", []) if s.get("codec_type") == "video"}
    if path.suffix.lower() == ".mp4" and vcodecs & {"vp8", "vp9", "av1"}:
        print(
            "\nNote: .mp4 with VP8/VP9/AV1 is valid for ffmpeg but some desktop players (e.g. QuickTime) "
            "handle it poorly; use VLC/IINA or re-encode to H.264/AAC for broad compatibility."
        )

    # Decode test
    print("\n--- ffmpeg decode (stderr highlights) ---")
    rc, err = _decode_test(path, full_decode=a.full_decode)
    if not a.full_decode:
        print("Mode: first 60s only (use --full-decode to scan the whole file)")

    err_lower = err.lower()
    red_flags = [
        "file ended prematurely",
        "error parsing",
        "invalid data found",
        "corrupt",
        "partial file",
    ]
    found = [x for x in red_flags if x in err_lower]

    last_t = _last_time_from_ffmpeg_stats(err) if a.full_decode else None
    if last_t is not None and dur:
        gap = abs(dur - last_t)
        print(f"Last time= in stats (approx. decode position): {last_t:.1f}s ({_format_duration_s(last_t)})")
        print(f"Delta vs. ffprobe duration: {gap:.1f}s")

    for line in err.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if any(
            w in stripped.lower()
            for w in (
                "error",
                "invalid",
                "prematurely",
                "corrupt",
                "failed",
                "truncat",
            )
        ):
            print(stripped)

    if found:
        print(f"\n*** Red-flag phrases in stderr: {', '.join(found)}")
    else:
        print("\nNo common truncation/corrupt phrases in stderr (still inspect lines above if any).")

    print(f"\nffmpeg exit code: {rc}")
    if a.full_decode and dur and last_t and (dur - last_t) > 5:
        print(
            f"\n*** Mismatch: header duration ~{dur:.0f}s but last decoded frame time ~{last_t:.0f}s — "
            "source may be truncated or mux is broken (browser may still play via range/adaptive behavior)."
        )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, json.JSONDecodeError) as e:
        print(f"Error: {e}", file=sys.stderr)
        raise SystemExit(1)
