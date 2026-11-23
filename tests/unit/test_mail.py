import pytest

from app.errors import AppError
from app.mail import empty_mailbox, read_mail


def _form(**overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "mail_enabled": "",
        "mail_host": "smtp.example.com",
        "mail_port": "587",
        "mail_security": "starttls",
        "mail_username": "parlor",
        "mail_password": "",
        "mail_from_name": "Parlor Night",
        "mail_from": "Parlor@Example.com",
    }
    data.update(overrides)
    return data


def test_blank_password_keeps_the_saved_one() -> None:
    stored = empty_mailbox()
    stored = type(stored)(
        enabled=False,
        host="smtp.example.com",
        port=587,
        security="starttls",
        username="parlor",
        password="secret",
        sender_name="Parlor Night",
        sender="parlor@example.com",
    )
    mail = read_mail(_form(), stored=stored)
    assert mail.password == "secret"
    assert mail.sender == "parlor@example.com"
    assert mail.enabled is False


def test_new_password_replaces_the_saved_one() -> None:
    stored = empty_mailbox()
    mail = read_mail(_form(mail_password="newer", mail_enabled="on"), stored=stored)
    assert mail.password == "newer"
    assert mail.enabled is True


def test_clear_removes_the_saved_password() -> None:
    stored = empty_mailbox()
    stored = type(stored)(
        enabled=False,
        host="",
        port=587,
        security="starttls",
        username="",
        password="secret",
        sender_name="",
        sender="",
    )
    mail = read_mail(_form(mail_host="", mail_password_clear="on"), stored=stored)
    assert mail.password == ""


def test_enabled_mail_needs_a_server_and_a_sender() -> None:
    with pytest.raises(AppError) as error:
        read_mail(_form(mail_enabled="on", mail_host=""), stored=empty_mailbox())
    assert error.value.message == "Укажите сервер SMTP."
    with pytest.raises(AppError) as missing:
        read_mail(_form(mail_enabled="on", mail_from=""), stored=empty_mailbox())
    assert missing.value.message == "Укажите адрес отправителя."
