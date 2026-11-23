"""Ящик формы «Связаться с нами». В этот диалог ответить нельзя."""

from __future__ import annotations

import uuid

DESK_ID = uuid.UUID("c0ffee00-0000-4000-8000-0000000000f1")
DESK_USERNAME = "contact.desk"
MARKER = "Сообщение из формы обратной связи."


def feedback_text(name: str, email: str, account: str, message: str) -> str:
    return (
        f"{MARKER}\n"
        "Ответить в этом диалоге нельзя — только на почту.\n\n"
        f"От: {name}\n"
        f"Почта для ответа: {email}\n"
        f"Учётка: {account}\n\n"
        f"{message}"
    )
