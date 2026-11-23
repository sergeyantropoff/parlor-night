"""Почта гостиной. Письма уходят только через сервер, который указал администратор."""

from __future__ import annotations

import logging
import re
import smtplib
from collections.abc import Mapping
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr

import asyncpg

from app.auth.validation import clean_email
from app.config import Settings
from app.errors import AppError

log = logging.getLogger(__name__)

_HOST = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?$")
_SECURITIES = ("none", "starttls", "ssl")
PROBE_SUBJECT = "Проверка почты Parlor Night"
PROBE_BODY = "Это проверочное письмо из настроек Parlor Night. Если вы его видите, почта настроена."


@dataclass(frozen=True, slots=True)
class Mailbox:
    enabled: bool
    host: str
    port: int
    security: str
    username: str
    password: str
    sender_name: str
    sender: str

    @property
    def from_header(self) -> str:
        if self.sender_name and self.sender:
            return formataddr((self.sender_name, self.sender))
        return self.sender


def empty_mailbox() -> Mailbox:
    return Mailbox(
        enabled=False,
        host="",
        port=587,
        security="starttls",
        username="",
        password="",
        sender_name="",
        sender="",
    )


def mailbox_from_settings(settings: Settings) -> Mailbox:
    if settings.smtp_ssl:
        security = "ssl"
    elif settings.smtp_tls:
        security = "starttls"
    else:
        security = "none"
    sender = settings.smtp_from.strip() or settings.smtp_user.strip()
    return Mailbox(
        enabled=bool(settings.smtp_host.strip()),
        host=settings.smtp_host.strip(),
        port=int(settings.smtp_port),
        security=security,
        username=settings.smtp_user,
        password=settings.smtp_password,
        sender_name="Parlor Night" if sender else "",
        sender=sender,
    )


def _flag(value: object) -> bool:
    return str(value or "").lower() in {"1", "on", "true", "yes"}


def _line(value: object, *, limit: int) -> str:
    return " ".join(str(value or "").split())[:limit]


def read_mail(data: Mapping[str, object], *, stored: Mailbox) -> Mailbox:
    enabled = _flag(data.get("mail_enabled"))
    host = _line(data.get("mail_host"), limit=253)
    if host and (_HOST.fullmatch(host) is None or ".." in host):
        raise AppError(422, "bad_mail", "Адрес сервера похож на ошибку. Нужен адрес вроде smtp.example.com.")
    if enabled and not host:
        raise AppError(422, "bad_mail", "Укажите сервер SMTP.")
    try:
        port = int(str(data.get("mail_port") or ""))
    except (TypeError, ValueError):
        raise AppError(422, "bad_mail", "Порт должен быть числом.") from None
    if not 1 <= port <= 65535:
        raise AppError(422, "bad_mail", "Порт: допустимо от 1 до 65535.")
    security = str(data.get("mail_security") or "starttls")
    if security not in _SECURITIES:
        security = "starttls"
    username = str(data.get("mail_username") or "").strip()
    if len(username) > 200:
        raise AppError(422, "bad_mail", "Имя пользователя длиннее 200 символов.")
    typed = str(data.get("mail_password") or "")
    if len(typed) > 200:
        raise AppError(422, "bad_mail", "Пароль длиннее 200 символов.")
    if typed:
        password = typed
    elif _flag(data.get("mail_password_clear")):
        password = ""
    else:
        password = stored.password
    sender_name = _line(data.get("mail_from_name"), limit=80)
    raw_from = str(data.get("mail_from") or "").strip()
    sender = ""
    if raw_from:
        try:
            sender = clean_email(raw_from)
        except ValueError as exc:
            raise AppError(422, "bad_mail", str(exc)) from exc
    elif enabled:
        raise AppError(422, "bad_mail", "Укажите адрес отправителя.")
    return Mailbox(
        enabled=enabled,
        host=host,
        port=port,
        security=security,
        username=username,
        password=password,
        sender_name=sender_name,
        sender=sender,
    )


def from_row(row: asyncpg.Record | None) -> Mailbox:
    if row is None:
        return empty_mailbox()
    security = str(row["mail_security"] or "starttls")
    if security not in _SECURITIES:
        security = "starttls"
    return Mailbox(
        enabled=bool(row["mail_enabled"]),
        host=str(row["mail_host"] or ""),
        port=int(row["mail_port"] or 587),
        security=security,
        username=str(row["mail_username"] or ""),
        password=str(row["mail_password"] or ""),
        sender_name=str(row["mail_from_name"] or ""),
        sender=str(row["mail_from"] or ""),
    )


async def load_mail(conn: asyncpg.Connection) -> Mailbox:
    row = await conn.fetchrow(
        """
        SELECT mail_enabled, mail_host, mail_port, mail_security,
               mail_username, mail_password, mail_from_name, mail_from
        FROM site_settings
        WHERE id = TRUE
        """
    )
    return from_row(row)


async def save_mail(conn: asyncpg.Connection, mail: Mailbox) -> None:
    await conn.execute(
        """
        UPDATE site_settings
        SET mail_enabled = $1,
            mail_host = $2,
            mail_port = $3,
            mail_security = $4,
            mail_username = $5,
            mail_password = $6,
            mail_from_name = $7,
            mail_from = $8,
            updated_at = now()
        WHERE id = TRUE
        """,
        mail.enabled,
        mail.host,
        mail.port,
        mail.security,
        mail.username,
        mail.password,
        mail.sender_name,
        mail.sender,
    )


def deliver(mail: Mailbox, *, recipient: str, reply_to: str, subject: str, body: str) -> None:
    if not mail.host or not mail.sender:
        raise AppError(422, "mail_off", "Укажите сервер SMTP и адрес отправителя.")
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = mail.from_header
    message["To"] = recipient
    if reply_to:
        message["Reply-To"] = reply_to
    message.set_content(body)
    try:
        if mail.security == "ssl":
            server = smtplib.SMTP_SSL(mail.host, mail.port, timeout=12)
        else:
            server = smtplib.SMTP(mail.host, mail.port, timeout=12)
        with server:
            server.ehlo()
            if mail.security == "starttls":
                server.starttls()
                server.ehlo()
            if mail.username:
                server.login(mail.username, mail.password)
            server.send_message(message)
    except smtplib.SMTPAuthenticationError:
        log.warning("smtp login was rejected")
        raise AppError(502, "mail_failed", "Сервер не принял имя или пароль.") from None
    except (TimeoutError, ConnectionError, OSError):
        log.warning("smtp connection failed")
        raise AppError(
            502,
            "mail_failed",
            "Не удалось соединиться с сервером. Проверьте адрес, порт и шифрование.",
        ) from None
    except smtplib.SMTPException:
        log.exception("smtp send failed")
        raise AppError(502, "mail_failed", "Сервер не принял письмо.") from None


def send_letter(settings: Settings, *, recipient: str, reply_to: str, subject: str, body: str) -> None:
    mail = mailbox_from_settings(settings)
    if not mail.host:
        raise AppError(503, "mail_off", "Почта гостиной не настроена. Письмо не отправлено.")
    deliver(mail, recipient=recipient, reply_to=reply_to, subject=subject, body=body)
