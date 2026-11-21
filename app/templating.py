"""Шаблоны Jinja2 с автоматическим экранированием."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup, escape
from starlette.requests import Request
from starlette.responses import HTMLResponse

from app.clock import current_zone
from app.news_html import sanitize_news
from app.news_images import cover_kind

TEMPLATES = Environment(
    loader=FileSystemLoader(Path(__file__).parent / "templates"),
    autoescape=select_autoescape(["html"]),
    auto_reload=True,
)
TEMPLATES.globals["mode_label"] = {
    "vs_computer": "С компьютером",
    "free": "Свободная доска",
    "analysis": "Анализ",
    "lesson": "Разбор партии",
    "online": "С человеком онлайн",
}
TEMPLATES.globals["type_label"] = {
    "chess": "Шахматы",
    "checkers": "Русские шашки",
    "go": "Го",
    "poker": "Покер",
    "uno": "Уно",
    "durak": "Дурак",
    "blackjack": "Блэкджек",
    "preferans": "Преферанс",
    "domino": "Домино",
    "nardy": "Нарды",
}
TEMPLATES.globals["result_label"] = {
    "white_win": "Победа белых",
    "black_win": "Победа чёрных",
    "draw": "Ничья",
    None: "Идёт",
    **{f"p{index}_win": "Победа за столом" for index in range(6)},
}


def _as_local(value: datetime) -> datetime:
    moment = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    return moment.astimezone(current_zone())


def _format_dt(value: object) -> str:
    if isinstance(value, datetime):
        return _as_local(value).strftime("%d.%m.%Y %H:%M")
    if hasattr(value, "strftime"):
        return value.strftime("%d.%m.%Y %H:%M")  # type: ignore[no-any-return]
    return "" if value is None else str(value)


_MONTHS = (
    "января",
    "февраля",
    "марта",
    "апреля",
    "мая",
    "июня",
    "июля",
    "августа",
    "сентября",
    "октября",
    "ноября",
    "декабря",
)


def _format_when(value: object) -> str:
    if not isinstance(value, datetime):
        return "" if value is None else str(value)
    moment = _as_local(value)
    now = datetime.now(current_zone())
    clock = moment.strftime("%H:%M")
    if moment.date() == now.date():
        return f"Сегодня, {clock}"
    if moment.date() == now.date() - timedelta(days=1):
        return f"Вчера, {clock}"
    return f"{moment.day} {_MONTHS[moment.month - 1]}, {clock}"


def _grouped(value: object) -> str:
    if value is None or value is False:
        return ""
    try:
        number = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return str(value)
    return f"{number:,}".replace(",", " ")


def _tone(value: object) -> int:
    text = str(value or "")
    return sum(ord(char) for char in text) % 6


def _story(value: object) -> Markup:
    return Markup(sanitize_news("" if value is None else str(value)))


def _cover_kind(value: object) -> str:
    return cover_kind(value)


_LOGIN = re.compile(r"^[a-z0-9_-]{3,32}$")
_AVATAR = re.compile(r"^[0-9a-f]{32}\.(jpg|png|webp)$")


def _chip(name: str, avatar: object) -> str:
    file_name = str(avatar or "")
    if _AVATAR.fullmatch(file_name):
        return f'<img class="avatar" src="/avatars/{file_name}" alt="" />'
    letter = escape((name[:1] or "?").upper())
    return f'<span class="avatar tone-{_tone(name)}">{letter}</span>'


def player_link(
    name: object,
    username: object = "",
    avatar: object = "",
    blank: bool = False,
    handle: bool = False,
    plain: bool = False,
    linked: bool = True,
) -> Markup:
    label = str(name or username or "").strip()
    login = str(username or "").strip().lower()
    shown = escape(label or login)
    text = f"<span>{shown}</span>" if plain else f"<strong>{shown}</strong>"
    if handle and login:
        text += f'<span class="handle">@{escape(login)}</span>'
    inner = f'{_chip(label or login, avatar)}<span class="person-copy">{text}</span>'
    if not linked or not _LOGIN.fullmatch(login):
        return Markup(f'<span class="person-link">{inner}</span>')
    target = ' target="_blank" rel="noopener"' if blank else ""
    return Markup(f'<a class="person-link" href="/players/{escape(login)}"{target}>{inner}</a>')


TEMPLATES.filters["dt"] = _format_dt
TEMPLATES.filters["when"] = _format_when
TEMPLATES.filters["grouped"] = _grouped
TEMPLATES.filters["tone"] = _tone
TEMPLATES.filters["story"] = _story
TEMPLATES.filters["cover_kind"] = _cover_kind
TEMPLATES.globals["player_link"] = player_link


def safe_json(data: object) -> str:
    return json.dumps(data, ensure_ascii=False, default=str).replace("<", "\\u003c")


def _asset_version(request: Request) -> str:
    settings = request.app.state.settings
    if settings.env != "local":
        return settings.asset_version
    latest = 0
    root = Path(__file__).parent / "static"
    for path in root.rglob("*"):
        if path.is_file():
            latest = max(latest, path.stat().st_mtime_ns)
    return str(latest or settings.asset_version)


def render(request: Request, name: str, context: dict[str, object] | None = None, status: int = 200) -> HTMLResponse:
    payload = dict(context or {})
    user = getattr(request.state, "user", None)
    saved = getattr(request.state, "theme", None)
    payload.setdefault("theme", saved if saved in {"light", "dark", "system"} else "dark")
    payload.setdefault("age_block", "")
    html = TEMPLATES.get_template(name).render(
        {
            **payload,
            "user": user,
            "chips": getattr(request.state, "chips", None),
            "csrf_token": getattr(request.state, "csrf", ""),
            "asset_version": _asset_version(request),
            "path": request.url.path,
            "site": getattr(request.state, "site", None),
            "can_register": bool(getattr(request.state, "can_register", False)),
            "nav_requests": int(getattr(request.state, "nav_counts", {}).get("requests", 0)),
            "nav_chats": int(getattr(request.state, "nav_counts", {}).get("chats", 0)),
            "nav_live": int(getattr(request.state, "nav_counts", {}).get("live", 0)),
        }
    )
    return HTMLResponse(html, status_code=status, media_type="text/html; charset=utf-8")
