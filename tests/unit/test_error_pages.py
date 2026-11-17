"""Каталог страниц ошибок и безопасные ссылки."""

from starlette.requests import Request

from app.errors_page import _actions, _internal_url, get_error_page, safe_note


def _request(path: str = "/missing", method: str = "GET", referer: str = "") -> Request:
    headers = []
    if referer:
        headers.append((b"referer", referer.encode()))
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": headers,
        "client": ("127.0.0.1", 1234),
        "server": ("127.0.0.1", 8010),
    }
    request = Request(scope)
    request.state.user = None
    return request


def test_known_pages_keep_their_picture() -> None:
    assert get_error_page(404)["art"] == "lost"
    assert get_error_page(401)["art"] == "access"
    assert get_error_page(403)["primary"] == "home"
    assert get_error_page(500)["art"] == "service"
    assert get_error_page(502)["art"] == "service"
    assert get_error_page(429)["art"] == "wait"


def test_unknown_codes_use_the_group_screen() -> None:
    missing = get_error_page(418)
    assert missing["title"] == "Необычный поворот"
    other = get_error_page(499)
    assert other["code"] == 499
    unknown = get_error_page(470)
    assert unknown["kind"] == "fallback"
    assert unknown["code"] == 470
    assert unknown["art"] == "request"
    down = get_error_page(599)
    assert down["code"] == 599
    assert get_error_page(True)["code"] == 500  # type: ignore[arg-type]


def test_retry_is_only_a_safe_get() -> None:
    page = get_error_page(408)
    href, label, _secondary = _actions(_request("/lobby"), page)
    assert href == "/lobby"
    assert label == "Открыть ещё раз"
    href, label, _secondary = _actions(_request("/lobby", method="POST"), page)
    assert href == "/"
    assert label == "На главную"


def test_login_page_does_not_point_at_itself() -> None:
    href, label, _secondary = _actions(_request("/login"), get_error_page(401))
    assert href == "/"
    assert label == "На главную"


def test_referer_must_stay_inside_the_site() -> None:
    request = _request("/missing", referer="https://evil.example/steal")
    assert _internal_url(request, "https://evil.example/steal") == ""
    assert _internal_url(request, "http://127.0.0.1:8010/lobby") == "/lobby"
    assert _internal_url(request, "/api/v1/games") == ""


def test_notes_drop_internals() -> None:
    assert safe_note("Партия не найдена.") == "Партия не найдена."
    assert safe_note("traceback in /app/main.py") is None
    assert safe_note("a\nb") is None
