"""JSON API версии v1."""

from __future__ import annotations

import re
import uuid

from fastapi import APIRouter, Request
from starlette.responses import JSONResponse, Response

from app.auth.validation import normalize_username, validate_username
from app.catalog import GAMES
from app.db.repositories import settings as settings_repo
from app.db.repositories.settings import as_preferences
from app.errors import AppError
from app.games.schemas import (
    CreateGameBody,
    GoCommandBody,
    InviteBody,
    JoinBody,
    MoveBody,
    SettingsBody,
    ThemeBody,
    VersionBody,
)
from app.names import shown
from app.web.routes import _store_settings

router = APIRouter(prefix="/api/v1")


def _user(request: Request) -> object:
    if request.state.user is None:
        raise AppError(401, "unauthorized", "Нужно войти в систему.")
    return request.state.user


def _game_id(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise AppError(404, "not_found", "Партия не найдена.") from exc


@router.post("/games", status_code=201)
async def create_game(request: Request, body: CreateGameBody) -> JSONResponse:
    user = _user(request)
    state = await request.app.state.service.create(user, body.model_dump())
    return JSONResponse(state, status_code=201)


@router.post("/games/join")
async def join_game(request: Request, body: JoinBody) -> JSONResponse:
    user = _user(request)
    game_id = await request.app.state.service.join(user, body.code)
    state = await request.app.state.service.view(user, game_id)
    return JSONResponse(state)


@router.post("/games/watch")
async def watch_game(request: Request, body: JoinBody) -> JSONResponse:
    user = _user(request)
    game_id = await request.app.state.service.watch(user, body.code)
    state = await request.app.state.service.view(user, game_id)
    return JSONResponse(state)


@router.post("/games/{game_id}/watch/arrive")
async def watch_arrive(request: Request, game_id: uuid.UUID) -> JSONResponse:
    user = _user(request)
    await request.app.state.service.arrive_watch(user, game_id)
    return JSONResponse({"ok": True})


@router.post("/games/{game_id}/watch/here")
async def watch_here(request: Request, game_id: uuid.UUID) -> JSONResponse:
    user = _user(request)
    await request.app.state.service.touch_watch(user, game_id)
    return JSONResponse({"ok": True})


@router.post("/games/{game_id}/watch/leave")
async def watch_leave(request: Request, game_id: uuid.UUID) -> JSONResponse:
    user = _user(request)
    await request.app.state.service.leave_watch(user, game_id)
    return JSONResponse({"ok": True})


@router.get("/games/{game_id}/watchers")
async def game_watchers(request: Request, game_id: uuid.UUID) -> JSONResponse:
    user = _user(request)
    return JSONResponse({"watchers": await request.app.state.service.watcher_list(user, game_id)})


@router.get("/games/{game_id}")
async def get_game(request: Request, game_id: uuid.UUID) -> JSONResponse:
    user = _user(request)
    return JSONResponse(await request.app.state.service.view(user, game_id))


@router.get("/games/{game_id}/legal-moves")
async def legal_moves(request: Request, game_id: uuid.UUID) -> JSONResponse:
    user = _user(request)
    return JSONResponse(await request.app.state.service.legal(user, game_id))


@router.get("/games/{game_id}/history")
async def history(request: Request, game_id: uuid.UUID) -> JSONResponse:
    user = _user(request)
    return JSONResponse(await request.app.state.service.history(user, game_id))


@router.post("/games/{game_id}/go")
async def go_command(request: Request, game_id: uuid.UUID, body: GoCommandBody) -> JSONResponse:
    user = _user(request)
    state = await request.app.state.service.go_command(
        user,
        game_id,
        body.command_id,
        body.version,
        body.action,
        body.col,
        body.row,
    )
    return JSONResponse(state)


@router.post("/games/{game_id}/moves")
async def move(request: Request, game_id: uuid.UUID, body: MoveBody) -> JSONResponse:
    user = _user(request)
    state, engine_error = await request.app.state.service.move(
        user, game_id, body.path, body.promotion, body.version
    )
    return JSONResponse({"state": state, "engine_error": engine_error})


@router.post("/games/{game_id}/undo")
async def undo(request: Request, game_id: uuid.UUID, body: VersionBody) -> JSONResponse:
    user = _user(request)
    return JSONResponse(await request.app.state.service.undo(user, game_id, body.version))


@router.post("/games/{game_id}/rematch")
async def rematch(request: Request, game_id: uuid.UUID) -> JSONResponse:
    user = _user(request)
    return JSONResponse(await request.app.state.service.rematch(user, game_id))


@router.post("/games/{game_id}/rematch/decline")
async def decline_rematch(request: Request, game_id: uuid.UUID) -> JSONResponse:
    user = _user(request)
    return JSONResponse(await request.app.state.service.decline_rematch(user, game_id))


@router.post("/games/{game_id}/stop")
async def stop_game(request: Request, game_id: uuid.UUID, body: VersionBody) -> JSONResponse:
    user = _user(request)
    return JSONResponse(await request.app.state.service.stop(user, game_id, body.version))


@router.post("/games/{game_id}/resign")
async def resign(request: Request, game_id: uuid.UUID, body: VersionBody) -> JSONResponse:
    user = _user(request)
    return JSONResponse(await request.app.state.service.resign(user, game_id, body.version))


@router.post("/games/{game_id}/engine-move")
async def engine_move(request: Request, game_id: uuid.UUID, body: VersionBody) -> JSONResponse:
    user = _user(request)
    return JSONResponse(await request.app.state.service.engine_move(user, game_id, body.version))


@router.post("/games/{game_id}/hint")
async def hint(request: Request, game_id: uuid.UUID, body: VersionBody) -> JSONResponse:
    user = _user(request)
    return JSONResponse(await request.app.state.service.hint(user, game_id, body.version))


@router.post("/games/{game_id}/orientation")
async def orientation(request: Request, game_id: uuid.UUID) -> JSONResponse:
    user = _user(request)
    return JSONResponse(await request.app.state.service.flip(user, game_id))


@router.post("/games/{game_id}/save")
async def save(request: Request, game_id: uuid.UUID) -> JSONResponse:
    user = _user(request)
    return JSONResponse(await request.app.state.service.save(user, game_id))


@router.get("/games/{game_id}/export")
async def export_game(request: Request, game_id: uuid.UUID) -> Response:
    user = _user(request)
    text, media, filename = await request.app.state.service.export(user, game_id)
    return Response(
        text,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/players")
async def search_players(request: Request, q: str = "") -> JSONResponse:
    user = _user(request)
    query = normalize_username(q)[:32]
    if not re.fullmatch(r"[a-z0-9_-]{1,32}", query):
        return JSONResponse({"players": []})
    like = query.replace("\\", "").replace("%", "\\%").replace("_", "\\_")
    async with request.app.state.pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT username, full_name, last_seen > now() - interval '2 minutes' AS live
            FROM users
            WHERE is_active = TRUE
              AND id <> $1
              AND username LIKE $2 ESCAPE '\\'
            ORDER BY CASE WHEN username LIKE $3 ESCAPE '\\' THEN 0 ELSE 1 END, username
            LIMIT 8
            """,
            user.id,
            f"%{like}%",
            f"{like}%",
        )
    return JSONResponse(
        {
            "players": [
                {
                    "username": row["username"],
                    "name": shown(row["full_name"], row["username"]),
                    "live": bool(row["live"]),
                }
                for row in rows
            ]
        }
    )


@router.post("/games/{game_id}/invite")
async def invite_player(request: Request, game_id: uuid.UUID, body: InviteBody) -> JSONResponse:
    user = _user(request)
    username = normalize_username(body.username)
    if validate_username(username):
        raise AppError(422, "bad_account", "Укажите логин игрока.")
    if not await request.app.state.gate.allow(f"invite:{user.id}", 20, 60):
        raise AppError(429, "rate_limited", "Слишком много приглашений. Подождите минуту.")
    async with request.app.state.pool.acquire() as conn:
        game = await conn.fetchrow(
            """
            SELECT g.user_id, g.join_code, g.game_type, g.status, g.mode,
                   EXISTS (
                       SELECT 1 FROM game_seats AS s
                       WHERE s.game_id = g.id AND s.user_id = $2 AND s.kind = 'human'
                   ) AS seated
            FROM games AS g
            WHERE g.id = $1
            """,
            game_id,
            user.id,
        )
        if game is None:
            raise AppError(404, "not_found", "Партия не найдена.")
        if game["user_id"] != user.id and not game["seated"]:
            raise AppError(403, "forbidden", "Приглашать может только игрок за столом.")
        if game["mode"] != "online" or game["status"] != "waiting" or not game["join_code"]:
            raise AppError(422, "bad_game", "Стол уже не ждёт игрока.")
        other = await conn.fetchrow(
            "SELECT id FROM users WHERE username = $1 AND is_active = TRUE",
            username,
        )
        if other is None:
            raise AppError(404, "not_found", "Такого игрока нет.")
        if other["id"] == user.id:
            raise AppError(422, "bad_account", "Себе приглашение не отправить.")
        title = GAMES[str(game["game_type"])].title
        code = str(game["join_code"])
        await conn.execute(
            "INSERT INTO messages (sender_id, recipient_id, body) VALUES ($1, $2, $3)",
            user.id,
            other["id"],
            f"Зову за стол: {title}. Код {code}. Откройте /join?code={code}",
        )
    return JSONResponse({"sent": username})


@router.post("/settings")
async def update_settings(request: Request, body: SettingsBody) -> JSONResponse:
    user = _user(request)
    await _store_settings(request, user.id, body)
    return JSONResponse({"saved": True})


@router.post("/settings/theme")
async def update_theme(request: Request, body: ThemeBody) -> JSONResponse:
    user = _user(request)
    async with request.app.state.pool.acquire() as conn:
        current = await settings_repo.get_settings(conn, user.id)
        preferences = as_preferences(current["analysis_preferences"])
        await settings_repo.update_settings(
            conn,
            user.id,
            theme=body.theme,
            board_style=current["board_style"],
            default_game=current["default_game"],
            default_side=current["default_side"],
            analysis_preferences=preferences,
        )
    return JSONResponse({"theme": body.theme})


_ = _game_id
