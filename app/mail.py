"""Письмо администратору. Отправка только через настроенный SMTP."""

from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

from app.config import Settings
from app.errors import AppError

log = logging.getLogger(__name__)


def send_letter(settings: Settings, *, recipient: str, reply_to: str, subject: str, body: str) -> None:
    host = settings.smtp_host.strip()
    if not host:
        raise AppError(503, "mail_off", "Почта гостиной не настроена. Письмо не отправлено.")
    sender = settings.smtp_from.strip() or settings.smtp_user.strip() or "parlor-night@localhost"
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = sender
    message["To"] = recipient
    message["Reply-To"] = reply_to
    message.set_content(body)
    try:
        if settings.smtp_ssl:
            server = smtplib.SMTP_SSL(host, settings.smtp_port, timeout=12)
        else:
            server = smtplib.SMTP(host, settings.smtp_port, timeout=12)
        with server:
            server.ehlo()
            if settings.smtp_tls and not settings.smtp_ssl:
                server.starttls()
                server.ehlo()
            if settings.smtp_user:
                server.login(settings.smtp_user, settings.smtp_password)
            server.send_message(message)
    except (OSError, smtplib.SMTPException):
        log.exception("contact mail failed")
        raise AppError(502, "mail_failed", "Письмо не ушло. Попробуйте ещё раз чуть позже.") from None
