"""Приветствие кабинета по времени суток."""

from __future__ import annotations

from datetime import datetime

from app.clock import current_zone


def day_part(hour: int) -> str:
    if hour < 5 or hour >= 23:
        return "Доброй ночи"
    if hour < 12:
        return "Доброе утро"
    if hour < 17:
        return "Добрый день"
    return "Добрый вечер"


def greeting(name: str, moment: datetime | None = None) -> str:
    current = moment or datetime.now(current_zone())
    return f"{day_part(current.hour)}, {name}"
