"""Tests for Yandex Disk path normalization."""

import pytest

from yandex_disk_module.paths import normalize_disk_path


@pytest.mark.unit
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("disk:/Video/Lectures", "/Video/Lectures"),
        ("/Video/Lectures", "/Video/Lectures"),
        ("Video/Lectures", "/Video/Lectures"),
        ("disk:/", "/"),
        ("/", "/"),
        ("/Video/", "/Video"),
        ("  /Video/Lectures  ", "/Video/Lectures"),
        ("disk:/Video/", "/Video"),
    ],
)
def test_normalize_disk_path(raw: str, expected: str) -> None:
    assert normalize_disk_path(raw) == expected
