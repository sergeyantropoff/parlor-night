import pytest

from app.errors import AppError
from app.mail_templates import TEMPLATES, clean_template, fill_template, present


def test_letters_cover_registration_invite_and_chat() -> None:
    titles = [item.title for item in TEMPLATES]
    assert "Письмо после регистрации" in titles
    assert "Подтверждение почты при регистрации" in titles
    assert "Восстановление пароля" in titles
    assert "Приглашение на игру" in titles
    assert "Личное сообщение" in titles
    assert all("{site}" in item.body or "{site}" in item.subject for item in TEMPLATES)


def test_unknown_parameter_is_rejected() -> None:
    with pytest.raises(AppError) as error:
        clean_template("confirm", "Код", "Ваш код {password}")
    assert "{password}" in error.value.message
    subject, body = clean_template("confirm", "  Код   почты ", "Код {code}\n{link}")
    assert subject == "Код почты"
    assert "{code}" in body


def test_parameters_are_filled_and_unknown_ones_stay() -> None:
    subject, body = fill_template("Код {code}", "Ссылка {link}", {"code": "4815"})
    assert subject == "Код 4815"
    assert body == "Ссылка {link}"


def test_missing_row_uses_the_default_text() -> None:
    rows = present({})
    confirm = next(row for row in rows if row["key"] == "confirm")
    assert confirm["subject"] == confirm["default_subject"]
    assert "код {code}" in str(confirm["body"])
