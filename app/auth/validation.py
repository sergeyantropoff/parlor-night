"""Проверка логина, пароля и имени пользователя."""

from __future__ import annotations

import re


def normalize_username(value: str) -> str:
    return value.strip().lower()


def validate_username(value: str, *, minimum: int = 3, maximum: int = 32) -> str | None:
    if not 3 <= minimum <= maximum <= 32 or not re.fullmatch(rf"[a-z0-9_-]{{{minimum},{maximum}}}", value):
        return f"Логин: {minimum}–{maximum} символов, латиница, цифры, _ и -."
    return None


def password_requirements(*, minimum: int, letter: bool, digit: bool) -> str:
    parts = [f"не меньше {minimum} символов"]
    if letter:
        parts.append("хотя бы одна буква")
    if digit:
        parts.append("хотя бы одна цифра")
    parts.append("не длиннее 128 символов")
    sentence = ", ".join(parts)
    return sentence[0].upper() + sentence[1:] + "."


def validate_password(
    password: str,
    *,
    relaxed: bool = False,
    minimum: int | None = None,
    letter: bool | None = None,
    digit: bool | None = None,
) -> str | None:
    if minimum is None:
        minimum = 4 if relaxed else 10
    if letter is None:
        letter = not relaxed
    if digit is None:
        digit = not relaxed
    if len(password) < minimum:
        return f"Пароль должен содержать не меньше {minimum} символов."
    if len(password) > 128:
        return "Пароль слишком длинный."
    if letter and not any(character.isalpha() for character in password):
        return "В пароле нужна хотя бы одна буква."
    if digit and not any(character.isdigit() for character in password):
        return "В пароле нужна хотя бы одна цифра."
    return None
