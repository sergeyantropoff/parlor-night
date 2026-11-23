"""Тексты писем. Параметры в фигурных скобках гостиная подставит при отправке."""

from __future__ import annotations

import re
from dataclasses import dataclass

import asyncpg

from app.errors import AppError

_TOKEN = re.compile(r"\{([a-z_]+)\}")


@dataclass(frozen=True, slots=True)
class Field:
    token: str
    label: str


@dataclass(frozen=True, slots=True)
class Template:
    key: str
    title: str
    subject: str
    body: str
    fields: tuple[Field, ...]

    @property
    def tokens(self) -> frozenset[str]:
        return frozenset(field.token for field in self.fields)


_SITE = Field("site", "адрес гостиной")
_NAME = Field("name", "имя игрока")
_LOGIN = Field("login", "логин")
_CODE = Field("code", "код")
_LINK = Field("link", "ссылка из письма")

TEMPLATES: tuple[Template, ...] = (
    Template(
        key="registered",
        title="Письмо после регистрации",
        subject="Добро пожаловать в Parlor Night",
        body=(
            "Здравствуйте, {name}.\n\n"
            "Учётная запись {login} создана. Гостиная открыта по адресу {site}\n\n"
            "Если регистрировались не вы, ничего делать не нужно: без пароля войти нельзя."
        ),
        fields=(_SITE, _NAME, _LOGIN),
    ),
    Template(
        key="confirm",
        title="Подтверждение почты при регистрации",
        subject="Код подтверждения почты",
        body=(
            "Здравствуйте, {name}.\n\n"
            "Чтобы подтвердить почту, введите код {code}\n"
            "или откройте ссылку: {link}\n\n"
            "Код действует недолго. Если вы не регистрировались в Parlor Night, пропустите это письмо.\n\n"
            "Гостиная: {site}"
        ),
        fields=(_SITE, _NAME, _CODE, _LINK),
    ),
    Template(
        key="reset",
        title="Восстановление пароля",
        subject="Восстановление пароля",
        body=(
            "Здравствуйте, {name}.\n\n"
            "Чтобы задать новый пароль для {login}, откройте ссылку: {link}\n"
            "Код: {code}\n\n"
            "Если вы не просили восстановить пароль, не переходите по ссылке. Прежний пароль останется в силе.\n\n"
            "Гостиная: {site}"
        ),
        fields=(_SITE, _NAME, _LOGIN, _LINK, _CODE),
    ),
    Template(
        key="invite",
        title="Приглашение на игру",
        subject="{host} зовёт сыграть в {game}",
        body=(
            "Здравствуйте, {name}.\n\n"
            "{host} приглашает вас за стол. Игра: {game}.\n"
            "Сесть можно по ссылке: {link}\n\n"
            "Гостиная: {site}"
        ),
        fields=(_SITE, _NAME, Field("host", "кто пригласил"), Field("game", "название игры"), _LINK),
    ),
    Template(
        key="message",
        title="Личное сообщение",
        subject="Новое сообщение от {sender}",
        body=(
            "Здравствуйте, {name}.\n\n"
            "{sender} написал вам:\n"
            "{text}\n\n"
            "Открыть беседу: {link}\n\n"
            "Гостиная: {site}"
        ),
        fields=(_SITE, _NAME, Field("sender", "кто написал"), Field("text", "текст сообщения"), _LINK),
    ),
    Template(
        key="referral",
        title="Друг зарегистрировался по ссылке",
        subject="По вашей ссылке зарегистрировался {friend}",
        body=(
            "Здравствуйте, {name}.\n\n"
            "По вашей ссылке в гостиной появился {friend}. Вам начислено {chips} фишек.\n\n"
            "Гостиная: {site}"
        ),
        fields=(_SITE, _NAME, Field("friend", "кто зарегистрировался"), Field("chips", "сколько фишек"),),
    ),
    Template(
        key="created",
        title="Учётную запись создал администратор",
        subject="Для вас открыта гостиная Parlor Night",
        body=(
            "Здравствуйте, {name}.\n\n"
            "Администратор создал учётную запись {login}. Войти можно здесь: {link}\n"
            "Пароль вам передадут отдельно. После входа его стоит сменить.\n\n"
            "Гостиная: {site}"
        ),
        fields=(_SITE, _NAME, _LOGIN, _LINK),
    ),
    Template(
        key="password",
        title="Пароль изменён",
        subject="Пароль в Parlor Night изменён",
        body=(
            "Здравствуйте, {name}.\n\n"
            "Пароль учётной записи {login} только что изменён. "
            "Если это были не вы, напишите администратору гостиной.\n\n"
            "Гостиная: {site}"
        ),
        fields=(_SITE, _NAME, _LOGIN),
    ),
)

_BY_KEY = {item.key: item for item in TEMPLATES}


def find_template(key: str) -> Template:
    item = _BY_KEY.get(key)
    if item is None:
        raise AppError(422, "bad_template", "Такого шаблона письма нет.")
    return item


def clean_template(key: str, subject: object, body: object) -> tuple[str, str]:
    item = find_template(key)
    title = " ".join(str(subject or "").split())
    text = str(body or "").strip()
    if not title:
        raise AppError(422, "bad_template", "Укажите тему письма.")
    if len(title) > 120:
        raise AppError(422, "bad_template", "Тема длиннее 120 символов.")
    if not text:
        raise AppError(422, "bad_template", "Укажите текст письма.")
    if len(text) > 4000:
        raise AppError(422, "bad_template", "Текст длиннее 4000 символов.")
    for piece in (title, text):
        for token in _TOKEN.findall(piece):
            if token not in item.tokens:
                allowed = ", ".join("{" + field.token + "}" for field in item.fields)
                raise AppError(
                    422,
                    "bad_template",
                    f"Параметр {{{token}}} в этом шаблоне не используется. Можно: {allowed}.",
                )
    return title, text


def fill_template(subject: str, body: str, values: dict[str, object]) -> tuple[str, str]:
    def paint(text: str) -> str:
        return _TOKEN.sub(lambda match: str(values.get(match.group(1), match.group(0))), text)

    return paint(subject), paint(body)


def present(saved: dict[str, tuple[str, str]]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for item in TEMPLATES:
        subject, body = saved.get(item.key, (item.subject, item.body))
        rows.append(
            {
                "key": item.key,
                "title": item.title,
                "subject": subject,
                "body": body,
                "default_subject": item.subject,
                "default_body": item.body,
                "fields": [{"token": field.token, "label": field.label} for field in item.fields],
            }
        )
    return rows


async def load_templates(conn: asyncpg.Connection) -> list[dict[str, object]]:
    rows = await conn.fetch("SELECT key, subject, body FROM mail_templates")
    saved = {str(row["key"]): (str(row["subject"]), str(row["body"])) for row in rows}
    return present(saved)


async def save_template(conn: asyncpg.Connection, key: str, subject: str, body: str) -> None:
    await conn.execute(
        """
        INSERT INTO mail_templates (key, subject, body)
        VALUES ($1, $2, $3)
        ON CONFLICT (key) DO UPDATE
        SET subject = EXCLUDED.subject, body = EXCLUDED.body, updated_at = now()
        """,
        key,
        subject,
        body,
    )
