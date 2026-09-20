"""Torn Prometheus mmap files must not 500 GET /metrics."""

from __future__ import annotations

import struct
from pathlib import Path

import pytest
from prometheus_client.mmap_dict import MmapedDict, mmap_key

from api.observability.metrics import _build_metrics_response, _merge_multiproc_files


def _write_corrupt_utf8_mmap(path: Path) -> None:
    encoded = b"a" * 167 + bytes([0x98]) + b"b" * 32
    encoded_len = len(encoded)
    pad = 8 - (encoded_len + 4) % 8
    padded_len = encoded_len + pad
    used = 8 + 4 + padded_len + 16
    buf = bytearray(used)
    struct.pack_into("i", buf, 0, used)
    struct.pack_into("i", buf, 8, encoded_len)
    buf[12 : 12 + encoded_len] = encoded
    struct.pack_into("dd", buf, 12 + padded_len, 1.0, 0.0)
    path.write_bytes(buf)


@pytest.mark.unit
def test_merge_skips_corrupt_mmap_and_keeps_good_file(tmp_path: Path) -> None:
    store = MmapedDict(str(tmp_path / "counter_1.db"))
    store.write_value(mmap_key("leap_test_total", "leap_test_total", [], [], "help"), 3.0, 0.0)
    store.close()
    _write_corrupt_utf8_mmap(tmp_path / "counter_2.db")

    metrics = list(_merge_multiproc_files(str(tmp_path)))

    assert {metric.name for metric in metrics} == {"leap_test_total"}


@pytest.mark.unit
def test_metrics_response_200_when_render_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PROMETHEUS_MULTIPROC_DIR", raising=False)

    def _boom(_registry):
        raise UnicodeDecodeError("utf-8", b"a" * 168, 167, 168, "invalid start byte")

    monkeypatch.setattr("api.observability.metrics.generate_latest", _boom)

    response = _build_metrics_response()

    assert response.status_code == 200
    assert response.body == b""
