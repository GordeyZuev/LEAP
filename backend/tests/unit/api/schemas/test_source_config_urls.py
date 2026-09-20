"""Input source URL configs reject SSRF / off-allowlist hosts at 422 time."""

import pytest
from pydantic import ValidationError

from api.schemas.template.input_source import InputSourceCreate
from api.schemas.template.source_config import VideoUrlSourceConfig, YandexDiskSourceConfig


@pytest.mark.unit
class TestYandexDiskSourcePublicUrl:
    def test_accepts_disk_share(self) -> None:
        cfg = YandexDiskSourceConfig(public_url="https://disk.yandex.ru/d/AbCdEf123")
        assert cfg.public_url == "https://disk.yandex.ru/d/AbCdEf123"

    def test_accepts_yadi_sk(self) -> None:
        cfg = YandexDiskSourceConfig(public_url="https://yadi.sk/d/AbCdEf123")
        assert cfg.public_url is not None

    def test_rejects_generic_yandex_property(self) -> None:
        with pytest.raises(ValidationError):
            YandexDiskSourceConfig(public_url="https://mail.yandex.ru/inbox")

    def test_rejects_loopback(self) -> None:
        with pytest.raises(ValidationError):
            YandexDiskSourceConfig(public_url="https://127.0.0.1/d/x")


@pytest.mark.unit
class TestVideoUrlSourceConfig:
    def test_accepts_youtube(self) -> None:
        cfg = VideoUrlSourceConfig(url="https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        assert "youtube.com" in cfg.url

    def test_rejects_arbitrary_host(self) -> None:
        with pytest.raises(ValidationError):
            VideoUrlSourceConfig(url="https://evil.example/watch")

    def test_rejects_http(self) -> None:
        with pytest.raises(ValidationError):
            VideoUrlSourceConfig(url="http://youtube.com/watch?v=x")


@pytest.mark.unit
class TestInputSourceCreateBindsPlatformSchema:
    def test_video_url_keeps_youtube(self) -> None:
        src = InputSourceCreate.model_validate(
            {
                "name": "yt-src",
                "platform": "VIDEO_URL",
                "config": {"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"},
            }
        )
        assert isinstance(src.config, VideoUrlSourceConfig)
        assert src.config.url == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

    def test_video_url_rejects_ssrf_host(self) -> None:
        with pytest.raises(ValidationError):
            InputSourceCreate.model_validate(
                {
                    "name": "evil-src",
                    "platform": "VIDEO_URL",
                    "config": {"url": "https://evil.example/watch"},
                }
            )

    def test_yandex_rejects_mail_property(self) -> None:
        with pytest.raises(ValidationError):
            InputSourceCreate.model_validate(
                {
                    "name": "yd-src",
                    "platform": "YANDEX_DISK",
                    "config": {"public_url": "https://mail.yandex.ru/inbox"},
                }
            )
