"""Tests for device-label parser and IP hashing helpers."""

import pytest

from api.auth.device import hash_ip, parse_device_label


@pytest.mark.unit
class TestParseDeviceLabel:
    """Heuristic UA → ``Browser · OS`` rendering."""

    def test_empty_ua_returns_unknown(self):
        assert parse_device_label(None) == "Unknown device"
        assert parse_device_label("") == "Unknown device"

    def test_safari_macos(self):
        ua = (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"
        )
        assert parse_device_label(ua) == "Safari · macOS"

    def test_chrome_windows(self):
        ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36"
        # Chrome must win over Safari token (Chromium advertises both).
        assert parse_device_label(ua) == "Chrome · Windows"

    def test_edge_takes_priority_over_chrome(self):
        ua = "Mozilla/5.0 Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0"
        assert parse_device_label(ua) == "Edge · Unknown device" or parse_device_label(ua).startswith("Edge")

    def test_firefox_linux(self):
        ua = "Mozilla/5.0 (X11; Linux x86_64; rv:121.0) Gecko/20100101 Firefox/121.0"
        assert parse_device_label(ua) == "Firefox · Linux"

    def test_ios_iphone(self):
        ua = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) Safari/604.1"
        # iPhone wins because we check more-specific OS tokens first.
        label = parse_device_label(ua)
        assert "iOS" in label and "Safari" in label


@pytest.mark.unit
class TestHashIp:
    """sha256-with-pepper of the client IP."""

    def test_empty_returns_none(self):
        assert hash_ip(None) is None
        assert hash_ip("") is None

    def test_deterministic(self):
        assert hash_ip("203.0.113.7") == hash_ip("203.0.113.7")

    def test_different_ips_differ(self):
        assert hash_ip("203.0.113.7") != hash_ip("203.0.113.8")

    def test_64_hex_chars(self):
        h = hash_ip("203.0.113.7")
        assert h is not None and len(h) == 64 and all(c in "0123456789abcdef" for c in h)
