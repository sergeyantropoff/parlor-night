"""JSON, который умеет отдавать даты и UUID так, как их ждёт мобильное приложение."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from enum import Enum

import asyncpg


def dump(value: object) -> object:
    if isinstance(value, asyncpg.Record):
        return dump(dict(value))
    if isinstance(value, dict):
        return {str(key): dump(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [dump(item) for item in value]
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    return value
