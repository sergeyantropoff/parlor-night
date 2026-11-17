"""Страница ошибки для обычной навигации. API остаётся на JSON."""

from __future__ import annotations

import json
import logging
import re
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

from starlette.requests import Request
from starlette.responses import HTMLResponse, Response

from app.templating import render

logger = logging.getLogger(__name__)
_CATALOG = Path(__file__).resolve().parent / "errors" / "errors.ru.json"
_REQUEST_ID = re.compile(r"^[a-f0-9]{12}$")
_ARTS = {"access", "conflict", "lost", "request", "service", "wait"}
_EYEBROWS = {
    "lost": "Страница не найдена",
    "access": "Нужен доступ",
    "wait": "Нужно подождать",
    "request": "Запрос не выполнен",
    "conflict": "Состояние изменилось",
    "service": "Пауза в гостиной",
}
_LABELS = {
    "login": "Войти",
    "home": "На главную",
    "lounge": "В гостиную",
    "retry": "Открыть ещё раз",
    "back": "Вернуться",
}


@lru_cache(maxsize=1)
def load_catalog() -> dict[str, object]:
    return json.loads(_CATALOG.read_text(encoding="utf-8"))


def get_error_page(status_code: int) -> dict[str, object]:
    if isinstance(status_code, bool) or not isinstance(status_code, int) or not 400 <= status_code <= 599:
        status_code = 500
    data = load_catalog()
    codes = data["codes"]
    row = codes.get(str(status_code)) if isinstance(codes, dict) else None
    if row is None:
        fallbacks = data["fallbacks"]
        group = "5xx" if status_code >= 500 else "4xx"
        source = fallbacks[group] if isinstance(fallbacks, dict) else {}
        row = dict(source)
        row["code"] = status_code
        row["kind"] = "fallback"
    page = dict(row)
    page["code"] = int(page.get("code") or status_code)
    art = str(page.get("art") or "")
    if art not in _ARTS:
        page["art"] = "service" if page["code"] >= 500 else "request"
        art = str(page["art"])
    page["eyebrow"] = _EYEBROWS[art]
    return page


def wants_html(request: Request) -> bool:
    path = request.url.path
    if path.startswith(("/api/", "/health", "/static/", "/avatars/", "/news-images/")):
        return False
    accept = request.headers.get("accept", "")
    if "text/html" in accept:
        return True
    if "application/json" in accept:
        return False
    return request.method in {"GET", "HEAD"}


def safe_note(text: str | None) -> str | None:
    if not text:
        return None
    if len(text) > 240 or any(mark in text for mark in "\r\n<>\\"):
        return None
    lowered = text.lower()
    if any(token in lowered for token in ("traceback", "select ", "password", "cookie", "token", "/app/", ".py")):
        return None
    return text


def _internal_url(request: Request, value: str) -> str:
    parts = urlsplit(value)
    if parts.scheme not in {"", "http", "https"}:
        return ""
    if parts.netloc and parts.netloc != request.url.netloc:
        return ""
    path = parts.path or ""
    if not path.startswith("/") or path.startswith("//") or "\\" in path:
        return ""
    if path.startswith(("/api/", "/static/", "/avatars/", "/news-images/")):
        return ""
    query = parts.query
    if len(query) > 240 or any(mark in query for mark in "\r\n"):
        return ""
    return path + (f"?{query}" if query else "")


def _actions(request: Request, page: dict[str, object]) -> tuple[str, str, bool]:
    kind = str(page.get("primary") or "home")
    home = "/"
    user = getattr(request.state, "user", None)
    lounge = "/lobby" if user is not None else home
    here = _internal_url(request, str(request.url.replace(fragment="")))
    if kind == "login" and request.url.path != "/login":
        return "/login", _LABELS["login"], True
    if kind == "lounge":
        return lounge, _LABELS["lounge"], lounge != home
    if kind == "retry" and request.method in {"GET", "HEAD"} and here:
        return here, _LABELS["retry"], here != home
    if kind == "back":
        back = _internal_url(request, request.headers.get("referer", ""))
        if back and back != request.url.path:
            return back, _LABELS["back"], back != home
    return home, _LABELS["home"], False


def _request_id(request: Request) -> str:
    value = str(getattr(request.state, "request_id", "") or "")
    return value if _REQUEST_ID.fullmatch(value) else ""


def error_response(
    request: Request,
    status: int,
    *,
    note: str | None = None,
    headers: dict[str, str] | None = None,
) -> Response:
    try:
        page = get_error_page(status)
        message = safe_note(note) or str(page.get("message") or "")
        retry_after = (headers or {}).get("retry-after", "")
        if status == 429 and retry_after.isdigit():
            message = f"{message} Подождите {int(retry_after)} с."
        href, label, secondary = _actions(request, page)
        response = render(
            request,
            "errors/page.html",
            {
                "page": page,
                "message": message,
                "primary_href": href,
                "primary_label": label,
                "show_secondary": secondary,
                "request_id": _request_id(request),
                "public_page": True,
            },
            status=status,
        )
    except Exception:
        logger.exception("error page failed")
        response = HTMLResponse(
            "<!DOCTYPE html><html lang=\"ru\"><meta charset=\"utf-8\"><title>Ошибка</title>"
            "<body><h1>Не удалось открыть страницу</h1><p><a href=\"/\">На главную</a></p></body></html>",
            status_code=status if isinstance(status, int) and 400 <= status <= 599 else 500,
        )
    response.headers["cache-control"] = "no-store"
    for key, value in (headers or {}).items():
        if key.lower() in {"content-length", "content-type"}:
            continue
        response.headers[key] = value
    return response
