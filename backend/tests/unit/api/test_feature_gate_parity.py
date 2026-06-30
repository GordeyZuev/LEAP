"""Guard: a bulk endpoint must enforce the same feature flag as its single variant."""

import inspect
import re

import pytest


def _flags(src: str, func_name: str) -> set[str]:
    m = re.search(rf"async def {func_name}\((.*?)\)\s*->", src, re.S)
    assert m, f"function {func_name} not found"
    return set(re.findall(r'require_feature\("([^"]+)"\)', m.group(1)))


@pytest.mark.unit
@pytest.mark.parametrize(
    "single,bulk",
    [
        ("run_recording", "bulk_run_recordings"),
        ("transcribe_recording", "bulk_transcribe_recordings"),
        ("download_recording", "bulk_download_recordings"),
        ("trim_recording", "bulk_trim_recordings"),
        ("extract_topics", "bulk_extract_topics"),
        ("generate_subtitles", "bulk_generate_subtitles"),
        ("upload_recording", "bulk_upload_recordings"),
        ("delete_recording", "bulk_delete_recordings"),
    ],
)
def test_single_and_bulk_enforce_same_flag(single, bulk):
    from api.routers import recordings

    src = inspect.getsource(recordings)
    assert _flags(src, single) == _flags(src, bulk), f"{single} vs {bulk} feature-flag mismatch"
