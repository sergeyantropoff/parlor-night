"""Часовой пояс гостя: из браузера, иначе Москва."""

from __future__ import annotations

import re
from contextvars import ContextVar
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

MOSCOW = ZoneInfo("Europe/Moscow")
_NAME = re.compile(r"^[A-Za-z0-9_+-]+(?:/[A-Za-z0-9_+-]+)+$")
_zone: ContextVar[ZoneInfo] = ContextVar("user_zone", default=MOSCOW)


def resolve_zone(value: object) -> ZoneInfo:
    name = str(value or "").strip()
    if not _NAME.fullmatch(name) or len(name) > 64:
        return MOSCOW
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError:
        return MOSCOW


def activate(value: object) -> ZoneInfo:
    zone = resolve_zone(value)
    _zone.set(zone)
    return zone


def current_zone() -> ZoneInfo:
    return _zone.get()
