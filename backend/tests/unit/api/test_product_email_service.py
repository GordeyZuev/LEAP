"""SMTP transport and product-news email rendering tests."""

from unittest.mock import AsyncMock, MagicMock, Mock

import pytest

from api.services.email_service import EmailService
from config.settings import EmailSettings


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("port", "start_tls", "use_tls"),
    [(587, True, False), (465, False, True), (2525, True, False)],
)
async def test_smtp_uses_the_expected_tls_mode(monkeypatch, port, start_tls, use_tls) -> None:
    settings = EmailSettings(
        enabled=True,
        smtp_host="smtp.example.test",
        smtp_port=port,
        smtp_user="mailer",
        smtp_password="secret",
        smtp_use_tls=True,
        from_email="news@example.test",
        base_url="https://leap.example.test",
    )
    service = EmailService(settings)
    smtp = AsyncMock()
    manager = MagicMock()
    manager.__aenter__ = AsyncMock(return_value=smtp)
    manager.__aexit__ = AsyncMock(return_value=False)
    smtp_factory = Mock(return_value=manager)
    monkeypatch.setattr("api.services.email_service.aiosmtplib.SMTP", smtp_factory)

    await service._send("reader@example.test", "Subject", "<p>News</p>", log_recipient=False)

    smtp_factory.assert_called_once_with(
        hostname="smtp.example.test",
        port=port,
        use_tls=use_tls,
        start_tls=start_tls,
    )
    smtp.login.assert_awaited_once_with("mailer", "secret")
    smtp.send_message.assert_awaited_once()


@pytest.mark.asyncio
async def test_product_update_email_contains_archive_and_subscription_links(monkeypatch) -> None:
    service = EmailService(
        EmailSettings(
            enabled=True,
            smtp_host="smtp.example.test",
            smtp_user="mailer",
            smtp_password="secret",
            from_email="news@example.test",
            base_url="https://leap.example.com",
        )
    )
    send = AsyncMock()
    monkeypatch.setattr(service, "_send", send)

    await service.send_product_update(
        "reader@example.test",
        "A clearer course workflow",
        "Help learners find the right material.",
        ["Keep your place when a video link refreshes."],
        ["Resume interrupted imports."],
        "https://leap.example/updates#release",
        "https://leap.example/updates/unsubscribe?token=unsubscribe",
        "https://leap.example/updates/preferences?token=preferences",
    )

    args, kwargs = send.await_args
    assert args[:2] == ("reader@example.test", "LEAP update: A clearer course workflow")
    assert "Help learners find the right material." in args[2]
    assert "Keep your place when a video link refreshes." in args[2]
    assert "Resume interrupted imports." in args[2]
    assert "https://leap.example/updates#release" in args[2]
    assert "https://leap.example/updates/unsubscribe?token=unsubscribe" in args[2]
    assert "https://leap.example/updates/preferences?token=preferences" in args[2]
    assert "https://leap.example.com/logo_symb_inverse.svg" in args[2]
    assert "You are receiving it because you subscribed" in args[2]
    assert kwargs == {"log_recipient": False}


def test_product_news_requires_public_https_frontend_links() -> None:
    settings = EmailSettings(
        enabled=True,
        smtp_host="smtp.example.test",
        smtp_user="mailer",
        smtp_password="secret",
        from_email="news@example.test",
        base_url="http://localhost:3000",
    )
    service = EmailService(settings)

    assert not service.product_news_ready

    settings.base_url = "https://news.leap.example.com"
    assert service.product_news_ready
