"""Точка входа FastAPI."""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse, Response

from app.admin.routes import router as admin_router
from app.api.mobile import router as mobile_router
from app.auth.passwords import Passwords
from app.auth.routes import router as auth_router
from app.config import Settings, get_settings
from app.db.pool import create_pool
from app.dev_accounts import ensure_local_accounts
from app.errors import AppError
from app.errors_page import error_response, wants_html
from app.games.routes import router as api_router
from app.games.service import GameService
from app.gate import Gate
from app.logging_config import configure_logging
from app.middleware import RequestMiddleware
from app.realtime import TableHub
from app.realtime import router as realtime_router
from app.social.routes import router as social_router
from app.templating import render
from app.web.routes import router as page_router
from app.workers.engines import EngineRuntime

os.environ.setdefault("OTEL_SDK_DISABLED", "true")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings: Settings = app.state.settings
    pool = await create_pool(settings.database_url)
    engines = EngineRuntime(settings)
    await engines.start()
    app.state.pool = pool
    app.state.engines = engines
    app.state.passwords = Passwords(settings)
    app.state.service = GameService(pool, engines, settings)
    app.state.hub = TableHub()
    gate = Gate()
    try:
        await gate.start(settings.valkey_url)
    except Exception:
        logging.getLogger(__name__).warning("valkey is unavailable, counters stay in process memory")
    app.state.gate = gate
    app.state.service.gate = gate
    app.state.site_policy = None
    app.state.site_policy_until = 0.0
    if settings.env == "local":
        await ensure_local_accounts(pool, app.state.passwords)
    try:
        yield
    finally:
        await gate.close()
        await engines.shutdown()
        await pool.close()


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)
    app = FastAPI(
        title="Parlor Night",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.settings = settings
    app.add_exception_handler(AppError, _app_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(HTTPException, _http_error)
    app.add_exception_handler(Exception, _unexpected)
    app.include_router(auth_router)
    app.include_router(admin_router)
    app.include_router(page_router)
    app.include_router(social_router)
    app.include_router(api_router)
    app.include_router(mobile_router)
    app.include_router(realtime_router)
    app.add_api_route("/health/live", _live, methods=["GET"])
    app.add_api_route("/health/ready", _ready, methods=["GET"])
    app.mount("/static", StaticFiles(directory="app/static"), name="static")
    app.add_middleware(RequestMiddleware)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.trusted_host_list)
    return app


async def _live() -> dict[str, str]:
    return {"status": "ok"}


async def _ready(request: Request) -> JSONResponse:
    pool = getattr(request.app.state, "pool", None)
    if pool is None:
        return JSONResponse({"status": "unavailable", "database": "down"}, status_code=503)
    try:
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
    except Exception:
        return JSONResponse({"status": "unavailable", "database": "down"}, status_code=503)
    chess_state = "ok" if request.app.state.engines.stockfish.available else "unavailable"
    gate = getattr(request.app.state, "gate", None)
    valkey_state = await gate.healthy() if gate is not None else "memory"
    return JSONResponse(
        {
            "status": "ok",
            "database": "ok",
            "chess_engine": chess_state,
            "checkers_engine": "ok",
            "valkey": valkey_state,
        }
    )


def _error_body(code: str, message: str, details: dict[str, object] | None = None) -> dict[str, object]:
    return {"error": {"code": code, "message": message, "details": details or {}}}


async def _app_error(request: Request, exc: AppError) -> JSONResponse | RedirectResponse | Response:
    if request.url.path.startswith("/api/") or "application/json" in request.headers.get("accept", ""):
        return JSONResponse(_error_body(exc.code, exc.message, exc.details), status_code=exc.status)
    if exc.status == 401:
        return RedirectResponse("/login", status_code=303)
    if exc.code == "adult_only":
        return render(request, "games/blocked.html", {"age_block": exc.message}, status=403)
    if wants_html(request):
        return error_response(request, exc.status, note=exc.message)
    return JSONResponse(_error_body(exc.code, exc.message, exc.details), status_code=exc.status)


async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    fields = []
    for item in exc.errors():
        location = item.get("loc") or ()
        fields.append(str(location[-1]) if location else "body")
    return JSONResponse(
        _error_body("invalid_body", "Проверьте введённые данные.", {"fields": fields}),
        status_code=422,
    )


def _http_headers(exc: HTTPException) -> dict[str, str]:
    raw = exc.headers or {}
    return {str(key): str(value) for key, value in raw.items()}


async def _http_error(request: Request, exc: HTTPException) -> JSONResponse | Response:
    headers = _http_headers(exc)
    path = request.url.path
    if path.startswith(("/static/", "/avatars/", "/news-images/")):
        return Response(status_code=exc.status_code, headers=headers or None)
    if wants_html(request):
        return error_response(request, exc.status_code, headers=headers)
    return JSONResponse(
        _error_body("http_error", "Запрос не выполнен."),
        status_code=exc.status_code,
        headers=headers or None,
    )


async def _unexpected(request: Request, exc: Exception) -> JSONResponse | Response:
    logging.getLogger(__name__).exception("unhandled error")
    if wants_html(request):
        return error_response(request, 500)
    return JSONResponse(
        _error_body("internal", "Внутренняя ошибка. Повторите действие позже."),
        status_code=500,
    )


app = create_app()
