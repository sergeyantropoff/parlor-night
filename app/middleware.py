"""Контекст запроса, сессия и CSRF. Тело небезопасного запроса можно прочитать повторно."""

from __future__ import annotations

import hashlib
import logging
import time
import urllib.parse
import uuid
from collections.abc import Awaitable, Callable

from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.auth.csrf import tokens_match, verify_login_csrf
from app.clock import activate
from app.db.repositories import api_access
from app.db.repositories import sessions as session_repo
from app.errors_page import error_response, wants_html
from app.geo import country_for
from app.site_policy import current, visitor_may_register
from app.social.notices import nav_counts
from app.templating import render
from app.terms import current as current_terms
from app.wallet import balance

logger = logging.getLogger(__name__)
UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}
_ASSET_TYPES = (
    b"image/",
    b"font/",
    b"audio/",
    b"video/",
    b"text/css",
    b"text/javascript",
    b"application/javascript",
    b"application/wasm",
    b"application/octet-stream",
    b"application/pdf",
)


def _maintenance_keeps(message: Message) -> bool:
    for key, value in message.get("headers", []):
        if key.lower() != b"content-type":
            continue
        kind = value.split(b";", 1)[0].strip().lower()
        return kind.startswith(_ASSET_TYPES)
    return False


def _client_ip(request: Request) -> str:
    settings = request.app.state.settings
    if settings.trust_proxy:
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded:
            return forwarded.split(",")[0].strip()[:64]
    if request.client is not None:
        return request.client.host
    return "unknown"


def _content_length(scope: Scope) -> int | None:
    for key, value in scope.get("headers") or []:
        if key.lower() == b"content-length":
            try:
                return int(value)
            except ValueError:
                return None
    return None


async def _buffer(receive: Receive, limit: int) -> tuple[bytes | None, Receive]:
    chunks: list[bytes] = []
    size = 0
    while True:
        message = await receive()
        if message["type"] != "http.request":
            continue
        chunk = message.get("body", b"")
        size += len(chunk)
        if size > limit:
            return None, receive
        chunks.append(chunk)
        if not message.get("more_body", False):
            break
    body = b"".join(chunks)

    async def replay() -> Message:
        return {"type": "http.request", "body": body, "more_body": False}

    return body, replay


class RequestMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request_id = uuid.uuid4().hex[:12]
        method = scope.get("method", "GET")
        path = scope.get("path", "")
        started = time.perf_counter()
        settings = scope["app"].state.settings
        if method in UNSAFE:
            body_limit = settings.max_body_bytes
            if path == "/admin/news/images":
                body_limit = settings.news_image_bytes + 65_536
            elif path == "/settings/avatar" or path == "/api/v1/account/avatar":
                body_limit = settings.avatar_bytes + 65_536
            declared = _content_length(scope)
            if declared is not None and declared > body_limit:
                await _too_large(scope, send, request_id)
                return
            body, receive = await _buffer(receive, body_limit)
            if body is None:
                await _too_large(scope, send, request_id)
                return
        else:
            body = b""
        request = Request(scope, receive)
        activate(request.cookies.get("pn_tz"))
        request.state.request_id = request_id
        request.state.user = None
        request.state.csrf = ""
        request.state.chips = None
        request.state.bearer = False
        request.state.auth_failed = False
        request.state.api_family = None
        request.state.api_client = None
        request.state.client_ip = _client_ip(request)
        request.state.hold_maintenance = False
        if not path.startswith("/static") and not path.startswith("/health"):
            limited = await self._pace(request)
            if limited is not None:
                await limited(scope, receive, send)
                return
            await self._session(request)
            if request.state.auth_failed and path not in {"/api/v1/auth/refresh", "/api/v1/auth/logout"}:
                denied = self._denied(request, missing_user=True)
                await denied(scope, receive, send)
                return
            if request.state.auth_failed:
                request.state.bearer = False
                request.state.user = None
            request.state.site = await current(request)
            request.state.terms = await current_terms(request)
            request.state.can_register = await visitor_may_register(request, request.state.site)
            staff = request.state.user
            if staff is not None and staff.is_admin:
                request.state.site = request.state.site.for_staff()
            closed = self._maintenance(request)
            if closed is not None:
                await closed(scope, receive, send)
                return
            if method in UNSAFE:
                denied = self._csrf(request, body)
                if denied is not None:
                    await denied(scope, receive, send)
                    return
        status = 500
        held = False

        async def send_secured(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                extra = {
                    "x-content-type-options": "nosniff",
                    "x-frame-options": "DENY",
                    "referrer-policy": "same-origin",
                    "content-security-policy": (
                        "default-src 'self'; img-src 'self' data:; style-src 'self'; "
                        "script-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
                    ),
                    "permissions-policy": "camera=(self), microphone=(self), geolocation=()",
                    "cross-origin-opener-policy": "same-origin",
                    "cross-origin-resource-policy": "same-origin",
                    "x-permitted-cross-domain-policies": "none",
                    "x-request-id": request_id,
                    "server": "parlor-night",
                }
                if request.app.state.settings.cookie_secure:
                    extra["strict-transport-security"] = "max-age=31536000; includeSubDomains"
                existing = {key.decode().lower() for key, _value in headers}
                for key, value in extra.items():
                    if key not in existing:
                        headers.append((key.encode(), value.encode()))
                if request.state.user is not None and "cache-control" not in existing:
                    headers.append((b"cache-control", b"no-store"))
                message["headers"] = headers
            await send(message)

        async def send_wrapper(message: Message) -> None:
            nonlocal status, held
            if held:
                return
            if message["type"] == "http.response.start":
                status = int(message["status"])
                if request.state.hold_maintenance and status < 400 and not _maintenance_keeps(message):
                    held = True
                    status = 503
                    closed_page = render(request, "closed.html", status=503)
                    await closed_page(scope, receive, send_secured)
                    return
            await send_secured(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            if not path.startswith("/health"):
                duration_ms = int((time.perf_counter() - started) * 1000)
                logger.info(
                    "http %s %s -> %s %sms",
                    method,
                    path,
                    status,
                    duration_ms,
                    extra={"request_id": request_id},
                )

    async def _session(self, request: Request) -> None:
        header = request.headers.get("authorization", "")
        pool = getattr(request.app.state, "pool", None)
        if header.lower().startswith("bearer "):
            token = header.split(" ", 1)[1].strip()
            if not token or pool is None:
                request.state.auth_failed = True
                return
            digest = hashlib.sha256(token.encode()).hexdigest()
            async with pool.acquire() as conn:
                found = await api_access.find_access(conn, digest)
                if found is None:
                    request.state.auth_failed = True
                    return
                await self._attach(request, conn, found.user)
            request.state.bearer = True
            request.state.api_family = found.family_id
            request.state.api_client = found.client_id
            return
        token = request.cookies.get("bm_session")
        if not token or pool is None:
            return
        digest = hashlib.sha256(token.encode()).hexdigest()
        async with pool.acquire() as conn:
            found_session = await session_repo.find_session(conn, digest)
            if found_session is None:
                return
            await self._attach(request, conn, found_session.user)
            request.state.csrf = found_session.csrf_token
            request.state.session_hash = digest

    async def _attach(self, request: Request, conn, user) -> None:
        gate = request.app.state.gate
        user_key = str(user.id)
        if await gate.once(f"seen:{user_key}", 30):
            agent = request.headers.get("user-agent", "")[:400]
            ip = request.state.client_ip
            await conn.execute(
                """
                UPDATE users
                SET last_seen = now(), last_ip = $2, last_country = $3, last_user_agent = $4, updated_at = now()
                WHERE id = $1
                """,
                user.id,
                ip[:64],
                country_for(ip),
                agent,
            )
            request.state.chips = await balance(conn, user.id)
            gate.remember_chips(user_key, int(request.state.chips))
        else:
            remembered = gate.chips.get(user_key)
            request.state.chips = remembered if remembered is not None else await balance(conn, user.id)
            if remembered is None:
                gate.remember_chips(user_key, int(request.state.chips))
        request.state.nav_counts = await nav_counts(conn, user.id)
        theme = await conn.fetchval(
            "SELECT theme FROM user_settings WHERE user_id = $1",
            user.id,
        )
        request.state.theme = theme if theme in {"light", "dark", "system"} else "dark"
        request.state.user = user

    async def _pace(self, request: Request) -> Response | None:
        settings = request.app.state.settings
        allowed = await request.app.state.gate.allow(
            f"ip:{request.state.client_ip}",
            settings.request_limit,
            settings.request_window_seconds,
        )
        if allowed:
            return None
        retry = str(settings.request_window_seconds)
        if request.url.path.startswith("/api/") or not wants_html(request):
            body = {
                "error": {
                    "code": "rate_limited",
                    "message": "Слишком много запросов. Подождите немного.",
                    "details": {},
                }
            }
            return JSONResponse(body, status_code=429, headers={"retry-after": retry})
        return error_response(request, 429, headers={"retry-after": retry})

    def _csrf(self, request: Request, body: bytes) -> Response | None:
        path = request.url.path
        if request.state.bearer:
            return None
        if path in {
            "/api/v1/auth/login",
            "/api/v1/auth/refresh",
            "/api/v1/auth/token",
            "/api/v1/auth/logout",
            "/api/v1/auth/register",
        }:
            return None
        settings = request.app.state.settings
        supplied = request.headers.get("x-csrf-token", "")
        content_type = request.headers.get("content-type", "")
        if "application/x-www-form-urlencoded" in content_type or not supplied:
            parsed = urllib.parse.parse_qs(body.decode("utf-8", errors="ignore"))
            if not supplied:
                supplied = parsed.get("csrf_token", [""])[0]
        if path in {"/register", "/register/welcome"} and request.state.user is None:
            cookie = request.cookies.get("bm_login_csrf", "")
            if verify_login_csrf(settings.secret_key, supplied, cookie):
                return None
            return self._denied(request)
        if path == "/contact" and request.state.user is None:
            cookie = request.cookies.get("bm_login_csrf", "")
            if verify_login_csrf(settings.secret_key, supplied, cookie):
                return None
            return self._denied(request)
        if path == "/login":
            cookie = request.cookies.get("bm_login_csrf", "")
            if verify_login_csrf(settings.secret_key, supplied, cookie):
                return None
            return self._denied(request)
        user = request.state.user
        if user is None or not tokens_match(supplied, request.state.csrf):
            return self._denied(request, missing_user=user is None)
        return None

    def _maintenance(self, request: Request) -> Response | None:
        site = request.state.site
        if not site.maintenance:
            return None
        path = request.url.path
        user = request.state.user
        if user is not None and user.is_admin:
            return None
        if path in {
            "/login",
            "/login/captcha",
            "/logout",
            "/register",
            "/register/captcha",
            "/register/welcome",
            "/api/v1/auth/login",
            "/api/v1/auth/refresh",
            "/api/v1/auth/logout",
            "/api/v1/auth/token",
        }:
            return None
        if request.method == "GET" and user is None and (path == "/" or path.startswith("/news")):
            return None
        if path == "/api/v1/maintenance" and request.method == "GET":
            return None
        if path.startswith("/api/"):
            body = {
                "error": {
                    "code": "maintenance",
                    "message": site.maintenance_text,
                    "details": {},
                }
            }
            return JSONResponse(body, status_code=503)
        if request.method not in {"GET", "HEAD"}:
            return render(request, "closed.html", status=503)
        request.state.hold_maintenance = True
        return None

    def _denied(self, request: Request, missing_user: bool = False) -> Response:
        path = request.url.path
        if path.startswith("/api/"):
            code = "unauthorized" if missing_user else "csrf"
            message = "Нужно войти в систему." if missing_user else "Запрос отклонён: не совпал защитный токен."
            status = 401 if missing_user else 403
            return JSONResponse(
                {"error": {"code": code, "message": message, "details": {}}},
                status_code=status,
            )
        if wants_html(request):
            status = 401 if missing_user else 403
            note = "Нужно войти в систему." if missing_user else "Обновите страницу и повторите действие."
            return error_response(request, status, note=note)
        text = "Обновите страницу и повторите действие."
        return Response(text, status_code=403, media_type="text/plain; charset=utf-8")


async def _too_large(scope: Scope, send: Send, request_id: str) -> None:
    path = str(scope.get("path") or "")
    if path.startswith("/api/"):
        body = "Слишком большой запрос.".encode()
        content_type = b"text/plain; charset=utf-8"
    else:
        request = Request(scope)
        request.state.request_id = request_id
        request.state.user = None
        request.state.theme = "dark"
        page = error_response(request, 413)
        body = page.body
        content_type = b"text/html; charset=utf-8"
    await send(
        {
            "type": "http.response.start",
            "status": 413,
            "headers": [
                (b"content-type", content_type),
                (b"content-length", str(len(body)).encode()),
                (b"cache-control", b"no-store"),
                (b"x-request-id", request_id.encode()),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


Handler = Callable[[Request], Awaitable[Response]]
