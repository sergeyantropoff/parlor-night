"""Как обращаться к гостю: фамилия, имя и отчество вместо логина."""

from __future__ import annotations

import re

from app.errors import AppError

_PART = re.compile(r"^[A-Za-zА-Яа-яЁё][A-Za-zА-Яа-яЁё'’-]{0,39}$")
_SEP = "\x1f"


def visible_name(value: object) -> str:
    raw = str(value or "")
    if _SEP in raw:
        parts = [part.strip() for part in raw.split(_SEP)]
        return " ".join(part for part in parts if part)
    return " ".join(raw.split())


def shown(full_name: object, username: object) -> str:
    return visible_name(full_name) or str(username or "")


def split_full_name(value: object) -> tuple[str, str, str]:
    raw = str(value or "")
    if _SEP in raw:
        parts = [part.strip() for part in raw.split(_SEP)]
        parts = (parts + ["", "", ""])[:3]
        return parts[0], parts[1], parts[2]
    words = raw.split()
    if len(words) >= 3:
        return words[0], words[1], " ".join(words[2:])
    if len(words) == 2:
        return words[0], words[1], ""
    if len(words) == 1:
        return words[0], "", ""
    return "", "", ""


def parse_full_name(family: object, given: object, patronymic: object) -> str:
    pieces = ["", "", ""]
    for label, index, raw in (
        ("Фамилию", 0, family),
        ("Имя", 1, given),
        ("Отчество", 2, patronymic),
    ):
        text = " ".join(str(raw or "").split())
        if not text:
            continue
        if not _PART.fullmatch(text):
            raise AppError(422, "bad_name", f"{label} пишется буквами, без цифр.")
        pieces[index] = text
    if not any(pieces):
        return ""
    return _SEP.join(pieces)
