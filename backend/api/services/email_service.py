"""Transactional email service (SMTP via aiosmtplib + Jinja2 templates)."""

from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from ipaddress import ip_address
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import aiosmtplib
import jinja2

from config.settings import EmailSettings
from logger import get_logger

logger = get_logger()

_TEMPLATE_DIR = Path(__file__).parent.parent.parent / "templates" / "email"

# Token TTL constants (also documented in auth.py comments)
RESET_TOKEN_TTL_HOURS = 1
VERIFY_TOKEN_TTL_HOURS = 24
RESEND_COOLDOWN_SECONDS = 60


class EmailService:
    """Sends transactional emails via SMTP.

    Account-notification methods safely no-op when email is disabled. Product-news
    methods raise instead, so opt-in requests and queued campaigns cannot look sent.
    """

    def __init__(self, settings: EmailSettings) -> None:
        self._s = settings
        self._jinja = jinja2.Environment(
            loader=jinja2.FileSystemLoader(str(_TEMPLATE_DIR)),
            autoescape=True,
        )

    @property
    def product_news_ready(self) -> bool:
        """Whether SMTP is configured and email links point to a public frontend host."""
        has_smtp = bool(
            self._s.enabled and self._s.smtp_host and self._s.smtp_user and self._s.smtp_password and self._s.from_email
        )
        parsed = urlsplit(self._s.base_url)
        hostname = parsed.hostname
        if not has_smtp or parsed.scheme != "https" or not hostname:
            return False
        hostname = hostname.rstrip(".")
        if hostname == "localhost" or hostname.endswith((".localhost", ".local", ".test", ".invalid")):
            return False
        try:
            address = ip_address(hostname)
        except ValueError:
            return True
        return not (address.is_loopback or address.is_private or address.is_link_local or address.is_unspecified)

    async def send_password_reset(self, to: str, reset_url: str, full_name: str | None = None) -> None:
        """Send a password-reset link to ``to``."""
        html = self._render(
            "password_reset.html",
            reset_url=reset_url,
            full_name=full_name,
            ttl_hours=RESET_TOKEN_TTL_HOURS,
        )
        await self._send(to, "Сброс пароля — LEAP", html)

    async def send_email_verification(self, to: str, verify_url: str, full_name: str | None = None) -> None:
        """Send an email-verification link to ``to``."""
        html = self._render(
            "email_verification.html",
            verify_url=verify_url,
            full_name=full_name,
            ttl_hours=VERIFY_TOKEN_TTL_HOURS,
        )
        await self._send(to, "Подтвердите ваш email — LEAP", html)

    async def send_email_changed_notice(self, to: str, new_email: str, full_name: str | None = None) -> None:
        """Notify the previous address that the account email was changed."""
        from html import escape

        greeting = escape(full_name) if full_name else "Здравствуйте"
        html = (
            f"<p>{greeting},</p>"
            f"<p>Email вашего аккаунта LEAP был изменён на <strong>{escape(new_email)}</strong>.</p>"
            f"<p>Если это были не вы, немедленно смените пароль и напишите в поддержку.</p>"
        )
        await self._send(to, "Ваш email в LEAP был изменён", html)

    async def send_product_news_confirmation(self, to: str, confirm_url: str) -> None:
        """Ask a visitor to confirm an optional product-news subscription."""
        if not self.product_news_ready:
            raise RuntimeError("Product-news email needs SMTP settings and a public EMAIL_BASE_URL")
        html = self._render("product_news_confirmation.html", confirm_url=confirm_url)
        await self._send(to, "Подтвердите подписку на новости LEAP", html, log_recipient=False)

    async def send_product_update(
        self,
        to: str,
        title: str,
        summary: str,
        audience_bullets: list[str],
        creator_bullets: list[str],
        update_url: str,
        unsubscribe_url: str,
        preferences_url: str,
    ) -> None:
        """Send one product update; do not put subscriber addresses in application logs."""
        if not self.product_news_ready:
            raise RuntimeError("Product-news email needs SMTP settings and a public EMAIL_BASE_URL")
        html = self._render(
            "product_update.html",
            title=title,
            summary=summary,
            audience_bullets=audience_bullets,
            creator_bullets=creator_bullets,
            update_url=update_url,
            unsubscribe_url=unsubscribe_url,
            preferences_url=preferences_url,
        )
        await self._send(to, f"LEAP update: {title}", html, log_recipient=False)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _render(self, template_name: str, **ctx: Any) -> str:
        return self._jinja.get_template(template_name).render(
            frontend_base_url=self._s.base_url.rstrip("/"),
            **ctx,
        )

    async def _send(self, to: str, subject: str, html: str, *, log_recipient: bool = True) -> None:
        if not self._s.enabled:
            recipient = f" to={to}" if log_recipient else ""
            logger.warning(f"[email] disabled — skipping send{recipient} subject={subject!r}")
            return
        if not self._s.smtp_host or not self._s.smtp_user or not self._s.smtp_password or not self._s.from_email:
            logger.error(
                "[email] enabled but SMTP config incomplete (need EMAIL_SMTP_HOST, EMAIL_SMTP_USER, "
                "EMAIL_SMTP_PASSWORD, EMAIL_FROM_EMAIL)"
            )
            raise RuntimeError("Email is enabled but SMTP host/user/from is incomplete")

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"{self._s.from_name} <{self._s.from_email}>"
        msg["To"] = to
        msg.attach(MIMEText(html, "html", "utf-8"))

        try:
            implicit_tls = self._s.smtp_port == 465
            async with aiosmtplib.SMTP(
                hostname=self._s.smtp_host,
                port=self._s.smtp_port,
                use_tls=implicit_tls,
                start_tls=self._s.smtp_use_tls and not implicit_tls,
            ) as smtp:
                await smtp.login(self._s.smtp_user, self._s.smtp_password)
                await smtp.send_message(msg)
            recipient = f" to={to}" if log_recipient else ""
            logger.info(f"[email] sent{recipient} subject={subject!r}")
        except Exception as exc:
            recipient = f" to={to}" if log_recipient else ""
            error = str(exc) if log_recipient else type(exc).__name__
            logger.error(f"[email] failed to send{recipient} subject={subject!r}: {error}")
            raise
