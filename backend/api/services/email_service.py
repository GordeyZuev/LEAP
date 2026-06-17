"""Transactional email service (SMTP via aiosmtplib + Jinja2 templates)."""

from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any

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

    All public methods are safe to call even when email is disabled —
    they log a debug message and return without raising.
    """

    def __init__(self, settings: EmailSettings) -> None:
        self._s = settings
        self._jinja = jinja2.Environment(
            loader=jinja2.FileSystemLoader(str(_TEMPLATE_DIR)),
            autoescape=True,
        )

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

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _render(self, template_name: str, **ctx: Any) -> str:
        return self._jinja.get_template(template_name).render(**ctx)

    async def _send(self, to: str, subject: str, html: str) -> None:
        if not self._s.enabled:
            logger.debug(f"[email] disabled — skipping send to={to} subject={subject!r}")
            return

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"{self._s.from_name} <{self._s.from_email}>"
        msg["To"] = to
        msg.attach(MIMEText(html, "html", "utf-8"))

        try:
            async with aiosmtplib.SMTP(
                hostname=self._s.smtp_host,
                port=self._s.smtp_port,
                start_tls=self._s.smtp_use_tls,
            ) as smtp:
                await smtp.login(self._s.smtp_user, self._s.smtp_password)
                await smtp.send_message(msg)
            logger.info(f"[email] sent to={to} subject={subject!r}")
        except Exception as exc:
            logger.error(f"[email] failed to send to={to} subject={subject!r}: {exc}")
            raise
