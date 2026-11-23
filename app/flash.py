"""Короткое подтверждение после сохранения. Текст показывает toast на следующей странице."""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import Response

FLASHES = {
    "settings": "Настройки сохранены.",
    "password": "Пароль изменён.",
    "avatar": "Портрет сохранён.",
    "avatar-off": "Портрет убран.",
    "site": "Настройки сохранены.",
    "mail-test": "Проверочное письмо отправлено.",
    "terms": "Условия игр сохранены.",
    "sessions": "Все сессии, кроме вашей, завершены.",
    "lockouts": "Блокировки входа сняты.",
    "wiped-messages": "Все сообщения удалены.",
    "wiped-games": "Партии очищены. Гости и фишки не изменены.",
    "wiped-stats": "Статистика игр очищена.",
    "keys": "Все ключи очищены. Войдите снова.",
    "news-created": "Новость опубликована.",
    "news-saved": "Новость сохранена.",
    "news-removed": "Новость убрана.",
    "game": "Партия создана.",
    "chips": "Фишки начислены.",
    "contact": "Сообщение отправлено администратору.",
    "broadcast": "Сообщение показано всем.",
    "broadcast-off": "Сообщение убрано.",
}


def pin(response: Response, request: Request, code: str) -> Response:
    if code not in FLASHES:
        return response
    response.set_cookie(
        "pn_flash",
        code,
        max_age=30,
        path="/",
        httponly=False,
        secure=bool(request.app.state.settings.cookie_secure),
        samesite="lax",
    )
    return response
