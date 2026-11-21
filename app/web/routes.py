"""Страницы кабинета, партий и настроек."""

from __future__ import annotations

import re
import secrets
import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any
from pathlib import Path

from fastapi import APIRouter, Request
from starlette.responses import FileResponse, JSONResponse, RedirectResponse, Response

from app.auth.validation import password_requirements, validate_password
from app.avatars import image_file as avatar_file
from app.avatars import media_type as avatar_media
from app.avatars import remove_avatar, store_avatar
from app.cards.preferans import STACK_POINTS
from app.cards.registry import ADULT_GAMES
from app.catalog import GAMES
from app.db.repositories import api_access, news, users
from app.db.repositories import games as games_repo
from app.db.repositories import sessions as session_repo
from app.db.repositories import settings as settings_repo
from app.db.repositories.settings import as_preferences
from app.errors import AppError
from app.errors_page import error_response
from app.games.present import computer_names
from app.games.schemas import SettingsBody
from app.games.service import _summarize
from app.greeting import greeting
from app.names import called, parse_full_name, shown, split_full_name
from app.news_images import image_file, media_type
from app.paging import page_links
from app.profile_stats import tally
from app.site_policy import current as current_policy
from app.templating import render, safe_json
from app.wallet import adult_message, age_years, balance, born_from_parts, credit, format_born, is_adult, years_phrase

_REFERRAL = re.compile(r"^[a-z0-9]{6,12}$")
_LOGIN = re.compile(r"^[a-z0-9_-]{3,32}$")
_CHIP_CAP = 100_000
_CHIP_PAGE = 50
_NEWS_PAGE = 6

router = APIRouter()


@router.get("/news-images/{name}")
async def news_image(request: Request, name: str) -> Response:
    path = image_file(Path(request.app.state.settings.news_image_dir), name)
    if path is None:
        raise AppError(404, "not_found", "Картинка не найдена.")
    return FileResponse(path, media_type=media_type(name), headers={"cache-control": "public, max-age=86400"})


def _player_side(value: object) -> str:
    side = str(value or "random")
    if side == "random":
        return secrets.choice(("white", "black"))
    return side


def _page_number(request: Request) -> int:
    raw = request.query_params.get("page", "1")
    if not raw.isdigit() or len(raw) > 6:
        return 1
    return int(raw)


def _user_or_login(request: Request) -> object:
    if request.state.user is None:
        return RedirectResponse("/login", status_code=303)
    return request.state.user


@router.get("/")
async def dashboard(request: Request) -> Response:
    user = request.state.user
    if user is None:
        return await _landing(request)
    data = await request.app.state.service.dashboard(user, page=_page_number(request))
    asked = request.query_params.get("page")
    if asked is not None and asked != str(data["page"]):
        target = "/" if data["page"] == 1 else f"/?page={data['page']}"
        return RedirectResponse(target, status_code=303)
    theme = data["settings"]["theme"]
    return render(
        request,
        "dashboard/index.html",
        {
            "dashboard": data,
            "greeting": greeting(user.display_name),
            "theme": theme,
            "board_style": data["settings"]["board_style"],
            "referral_link": await _referral_link(request, user.id),
        },
    )


@router.get("/chips")
async def chip_history(request: Request) -> Response:
    user = _user_or_login(request)
    if isinstance(user, Response):
        return user
    async with request.app.state.pool.acquire() as conn:
        events = await _chip_events(conn, user.id)
    pages = max(1, (len(events) + _CHIP_PAGE - 1) // _CHIP_PAGE)
    current = min(_page_number(request), pages)
    asked = request.query_params.get("page")
    if asked is not None and asked != str(current):
        target = "/chips" if current == 1 else f"/chips?page={current}"
        return RedirectResponse(target, status_code=303)
    start = (current - 1) * _CHIP_PAGE
    window = events[start : start + _CHIP_PAGE]
    first = start + 1 if window else 0
    last = start + len(window)
    span = f"{first}–{last}" if first != last else str(first)
    shown = f"{span} из {len(events)}" if window and pages > 1 else ""
    return render(
        request,
        "chips/index.html",
        {
            "events": window,
            "page": current,
            "pages": pages,
            "page_links": page_links(current, pages),
            "shown": shown,
        },
    )


@router.get("/news")
async def news_index(request: Request) -> Response:
    if request.query_params.get("page"):
        return RedirectResponse("/news", status_code=303)
    async with request.app.state.pool.acquire() as conn:
        posts = await news.list_news(conn, limit=3)
    return render(
        request,
        "public/news_index.html",
        {"posts": posts, "public_page": request.state.user is None},
    )


def _public_page(request: Request, template: str) -> Response:
    return render(request, template, {"public_page": True})


@router.get("/rules")
async def house_rules(request: Request) -> Response:
    return _public_page(request, "public/rules.html")


@router.get("/privacy")
async def privacy(request: Request) -> Response:
    return _public_page(request, "public/privacy.html")


@router.get("/contact")
async def contact(request: Request) -> Response:
    return _public_page(request, "public/contact.html")


@router.get("/about")
async def about(request: Request) -> Response:
    return _public_page(request, "public/about.html")


@router.get("/news/{news_id}")
async def news_page(request: Request, news_id: uuid.UUID) -> Response:
    async with request.app.state.pool.acquire() as conn:
        post = await news.get_news(conn, news_id)
    if post is None:
        return error_response(request, 404, note="Новость не найдена.")
    return render(request, "public/news.html", {"post": post, "public_page": True})


def _offered_game(request: Request, game: str | None) -> str | None:
    if not game or game not in GAMES:
        return None
    site = getattr(request.state, "site", None)
    if site is not None and not site.allows(game):
        return None
    return game


async def _new_game_page(
    request: Request,
    user,
    *,
    game: str | None,
    error: str | None,
    age_block: str = "",
    status: int = 200,
) -> Response:
    prefs = await _prefs(request, user.id)
    picked = _offered_game(request, game)
    birth = await _birth(request, user.id)
    if picked in ADULT_GAMES and not birth["adult"]:
        picked = None
        age_block = age_block or adult_message(birth["born"] if isinstance(birth["born"], date) else None, game or "poker") or ""
        status = 403
    return render(
        request,
        "games/new.html",
        {
            "error": error,
            "age_block": age_block,
            "game": picked,
            "setup_title": GAMES[picked].title if picked else None,
            "setup_blurb": GAMES[picked].blurb if picked else None,
            "theme": prefs["theme"],
            "prefs": prefs,
            "board_style": prefs["board_style"],
            "preferans_stack_points": STACK_POINTS,
            **birth,
        },
        status=status,
    )


@router.get("/games/new")
async def new_game(request: Request) -> Response:
    user = _user_or_login(request)
    if isinstance(user, Response):
        return user
    return await _new_game_page(request, user, game=None, error=None)


@router.get("/games/new/{game_type}")
async def new_game_setup(request: Request, game_type: str) -> Response:
    user = _user_or_login(request)
    if isinstance(user, Response):
        return user
    if _offered_game(request, game_type) is None:
        return RedirectResponse("/games/new", status_code=303)
    return await _new_game_page(request, user, game=game_type, error=None)


@router.post("/games")
async def create_game(request: Request) -> Response:
    user = _user_or_login(request)
    if isinstance(user, Response):
        return user
    form = await request.form()
    moves = str(form.get("moves") or "").strip()
    payload = {
        "game_type": str(form.get("game_type") or "chess"),
        "mode": str(form.get("mode") or "vs_computer"),
        "player_side": _player_side(form.get("player_side")),
        "engine_level": _int(form.get("engine_level"), 3),
        "engine_time_ms": _int(form.get("engine_time_ms"), 1000),
        "audience": str(form.get("audience") or "closed"),
        "computers": _int(form.get("computers"), 0) if "computers" in form else None,
        "open_seats": _int(form.get("open_seats"), 0) if "open_seats" in form else None,
        "initial_fen": str(form.get("initial_fen") or "").strip() or None,
        "pgn": str(form.get("pgn") or "").strip() or None,
        "initial_position": str(form.get("initial_position") or "").strip() or None,
        "moves": [line.strip() for line in moves.splitlines() if line.strip()] or None,
        "durak_kind": str(form.get("durak_kind") or "podkidnoy"),
        "pool": _int(form.get("pool"), 12),
        "stake": _int(form.get("stake"), 1),
        "board_size": _int(form.get("board_size"), 19),
    }
    try:
        state = await request.app.state.service.create(user, payload)
    except AppError as exc:
        blocked = exc.code == "adult_only"
        return await _new_game_page(
            request,
            user,
            game=None if blocked else str(form.get("game_type") or ""),
            error=None if blocked else exc.message,
            age_block=exc.message if blocked else "",
            status=exc.status,
        )
    return RedirectResponse(f"/games/{state['id']}", status_code=303)


@router.get("/games/{game_id}")
async def game_page(request: Request, game_id: uuid.UUID) -> Response:
    return await _board_page(request, game_id, analysis=False)


@router.get("/games/{game_id}/analysis")
async def analysis_page(request: Request, game_id: uuid.UUID) -> Response:
    return await _board_page(request, game_id, analysis=True)


@router.get("/join")
async def join_form(request: Request) -> Response:
    user = _user_or_login(request)
    if isinstance(user, Response):
        return user
    prefs = await _prefs(request, user.id)
    code = request.query_params.get("code", "")
    return render(
        request,
        "games/join.html",
        {"error": None, "code": code, "theme": prefs["theme"], "board_style": prefs["board_style"]},
    )


@router.post("/join")
async def join_submit(request: Request) -> Response:
    user = _user_or_login(request)
    if isinstance(user, Response):
        return user
    form = await request.form()
    code = str(form.get("code") or "")
    try:
        game_id = await request.app.state.service.join(user, code)
    except AppError as exc:
        return await _join_error(request, user, code, exc)
    return RedirectResponse(f"/games/{game_id}", status_code=303)


async def _join_error(request: Request, user, code: str, exc: AppError) -> Response:
    prefs = await _prefs(request, user.id)
    blocked = exc.code == "adult_only"
    return render(
        request,
        "games/join.html",
        {
            "error": None if blocked else exc.message,
            "age_block": exc.message if blocked else "",
            "code": code,
            "theme": prefs["theme"],
            "board_style": prefs["board_style"],
        },
        status=exc.status,
    )


@router.post("/join/watch")
async def watch_submit(request: Request) -> Response:
    user = _user_or_login(request)
    if isinstance(user, Response):
        return user
    form = await request.form()
    code = str(form.get("code") or "")
    try:
        game_id = await request.app.state.service.watch(user, code)
    except AppError as exc:
        return await _join_error(request, user, code, exc)
    return RedirectResponse(f"/games/{game_id}", status_code=303)


@router.get("/live")
async def live_page(request: Request) -> Response:
    user = _user_or_login(request)
    if isinstance(user, Response):
        return user
    return await _live_page(request, user)


@router.post("/live/{game_id}/watch")
async def live_watch(request: Request, game_id: uuid.UUID) -> Response:
    user = _user_or_login(request)
    if isinstance(user, Response):
        return user
    try:
        watched = await request.app.state.service.watch_table(user, game_id)
    except AppError as exc:
        return await _live_refusal(request, user, exc)
    return RedirectResponse(f"/games/{watched}", status_code=303)


@router.post("/live/{game_id}/sit")
async def live_sit(request: Request, game_id: uuid.UUID) -> Response:
    user = _user_or_login(request)
    if isinstance(user, Response):
        return user
    try:
        seated = await request.app.state.service.sit_open(user, game_id)
    except AppError as exc:
        return await _live_refusal(request, user, exc)
    return RedirectResponse(f"/games/{seated}", status_code=303)


@router.get("/settings")
async def settings_page(request: Request) -> Response:
    user = _user_or_login(request)
    if isinstance(user, Response):
        return user
    return await _settings_page(request, user, password_saved=request.query_params.get("password") == "changed")


@router.post("/settings")
async def settings_save(request: Request) -> Response:
    user = _user_or_login(request)
    if isinstance(user, Response):
        return user
    form = await request.form()
    family = str(form.get("family") or "")
    given = str(form.get("given") or "")
    patronymic = str(form.get("patronymic") or "")
    posted_name = (family, given, patronymic)
    try:
        full_name = parse_full_name(family, given, patronymic)
    except AppError as exc:
        return await _settings_page(request, user, error=exc.message, name=posted_name)
    try:
        posted_born = _posted_born(form)
    except AppError as exc:
        return await _settings_page(request, user, error=exc.message, name=posted_name)
    stored = await _stored_born(request, user.id)
    if posted_born is not None and posted_born != stored and form.get("confirm") != "yes":
        return await _settings_page(
            request,
            user,
            error="Подтвердите, что дата указана верно.",
            born=posted_born,
            preview=True,
            name=posted_name,
        )
    body = SettingsBody(
        theme=str(form.get("theme") or "system"),  # type: ignore[arg-type]
        board_style=str(form.get("board_style") or "classic"),  # type: ignore[arg-type]
        default_game=str(form.get("default_game") or "chess"),  # type: ignore[arg-type]
        default_side=str(form.get("default_side") or "white"),  # type: ignore[arg-type]
        chess_depth=_int(form.get("chess_depth"), 12),
        chess_time_ms=_int(form.get("chess_time_ms"), 1000),
        chess_multipv=_int(form.get("chess_multipv"), 3),
        checkers_level=_int(form.get("checkers_level"), 3),
        checkers_time_ms=_int(form.get("checkers_time_ms"), 1000),
    )
    await _store_settings(request, user.id, body)
    if full_name != (user.full_name or ""):
        async with request.app.state.pool.acquire() as conn:
            await users.set_full_name(conn, user.id, full_name)
    if posted_born is not None and posted_born != stored:
        async with request.app.state.pool.acquire() as conn:
            await conn.execute(
                "UPDATE users SET born_on = $2, updated_at = now() WHERE id = $1",
                user.id,
                posted_born,
            )
    return await _settings_page(request, user, saved=True, name=split_full_name(full_name))


@router.post("/settings/password")
async def settings_password(request: Request) -> Response:
    user = _user_or_login(request)
    if isinstance(user, Response):
        return user
    form = await request.form()
    current_password = str(form.get("current_password") or "")
    new_password = str(form.get("new_password") or "")
    repeat_password = str(form.get("repeat_password") or "")
    if new_password != repeat_password:
        return await _settings_page(request, user, password_error="Новые пароли не совпадают.")
    policy = await current_policy(request)
    password_error = validate_password(
        new_password,
        minimum=policy.password_min,
        letter=policy.password_needs_letter,
        digit=policy.password_needs_digit,
    )
    if password_error:
        return await _settings_page(request, user, password_error=password_error)
    async with request.app.state.pool.acquire() as conn:
        record = await users.get_auth_record(conn, user.username)  # type: ignore[attr-defined]
    digest = record.password_hash if record and record.is_active else None
    if not await request.app.state.passwords.verify_async(digest, current_password):
        return await _settings_page(request, user, password_error="Старый пароль указан неверно.")
    if current_password == new_password:
        return await _settings_page(request, user, password_error="Новый пароль совпадает со старым.")
    password_hash = request.app.state.passwords.hash_password(new_password)
    token_hash = getattr(request.state, "session_hash", None)
    async with request.app.state.pool.acquire() as conn:
        async with conn.transaction():
            await users.set_password_hash(conn, user.id, password_hash)  # type: ignore[attr-defined]
            if token_hash:
                await session_repo.revoke_other_user_sessions(conn, user.id, token_hash)  # type: ignore[attr-defined]
            await api_access.revoke_user(conn, user.id)
    return RedirectResponse("/settings?password=changed", status_code=303)


@router.get("/avatars/{name}")
async def avatar_image(request: Request, name: str) -> Response:
    user = _user_or_login(request)
    if isinstance(user, Response):
        return user
    path = avatar_file(Path(request.app.state.settings.avatar_dir), name)
    if path is None:
        raise AppError(404, "not_found", "Портрет не найден.")
    return FileResponse(path, media_type=avatar_media(name), headers={"cache-control": "private, max-age=86400"})


@router.post("/settings/avatar")
async def avatar_save(request: Request) -> Response:
    user = _user_or_login(request)
    if isinstance(user, Response):
        return user
    form = await request.form()
    upload = form.get("file")
    payload = await upload.read() if hasattr(upload, "read") else b""
    directory = Path(request.app.state.settings.avatar_dir)
    try:
        name = store_avatar(directory, payload, limit=request.app.state.settings.avatar_bytes)
    except ValueError:
        return JSONResponse({"error": "Нужен JPEG, PNG или WebP не больше 10 МБ."}, status_code=422)
    async with request.app.state.pool.acquire() as conn:
        previous = await users.set_avatar(conn, user.id, name)  # type: ignore[attr-defined]
    if previous and previous != name:
        remove_avatar(directory, previous)
    return JSONResponse({"src": f"/avatars/{name}"})


@router.post("/settings/avatar/remove")
async def avatar_clear(request: Request) -> Response:
    user = _user_or_login(request)
    if isinstance(user, Response):
        return user
    directory = Path(request.app.state.settings.avatar_dir)
    async with request.app.state.pool.acquire() as conn:
        previous = await users.set_avatar(conn, user.id, None)  # type: ignore[attr-defined]
    if previous:
        remove_avatar(directory, previous)
    return JSONResponse({"src": ""})


@router.get("/players/{username}")
async def player_page(request: Request, username: str) -> Response:
    user = _user_or_login(request)
    if isinstance(user, Response):
        return user
    loaded = await _load_player(request, username)
    if isinstance(loaded, Response):
        return loaded
    player, played, counted, online, purse = loaded
    return await _profile_page(
        request,
        user,
        player,
        played,
        counted,
        online,
        purse,
        chips_added=request.query_params.get("chips") == "1",
    )


@router.post("/players/{username}/chips")
async def grant_profile_chips(request: Request, username: str) -> Response:
    user = _user_or_login(request)
    if isinstance(user, Response):
        return user
    if not user.is_admin:  # type: ignore[attr-defined]
        raise AppError(404, "not_found", "Страница не найдена.")
    loaded = await _load_player(request, username)
    if isinstance(loaded, Response):
        return loaded
    player, played, counted, online, purse = loaded
    form = await request.form()
    amount, error = _grant_amount(str(form.get("amount") or ""), purse)
    if error or amount is None:
        return await _profile_page(
            request,
            user,
            player,
            played,
            counted,
            online,
            purse,
            chip_error=error or "Укажите, сколько фишек добавить.",
            status=422,
        )
    async with request.app.state.pool.acquire() as conn:
        await credit(conn, player["id"], amount, reason="admin", game_id=None)
        purse = await balance(conn, player["id"])
    request.app.state.gate.chips.pop(str(player["id"]), None)
    return RedirectResponse(f"/players/{player['username']}?chips=1", status_code=303)


@router.post("/players/{username}/friend")
async def profile_friend(request: Request, username: str) -> Response:
    user = _user_or_login(request)
    if isinstance(user, Response):
        return user
    loaded = await _load_player(request, username)
    if isinstance(loaded, Response):
        return loaded
    player, played, counted, online, purse = loaded
    allowed = await request.app.state.gate.allow(f"friend:{user.id}", 10, 60)  # type: ignore[attr-defined]
    if not allowed:
        return await _profile_page(
            request,
            user,
            player,
            played,
            counted,
            online,
            purse,
            friend_error="Слишком много запросов. Подождите минуту.",
            status=429,
        )
    if player["id"] == user.id:  # type: ignore[attr-defined]
        return await _profile_page(
            request,
            user,
            player,
            played,
            counted,
            online,
            purse,
            friend_error="Себя добавить в друзья нельзя.",
            status=422,
        )
    async with request.app.state.pool.acquire() as conn:
        exists = await conn.fetchval(
            """
            SELECT 1 FROM friendships
            WHERE (requester_id = $1 AND addressee_id = $2)
               OR (requester_id = $2 AND addressee_id = $1)
            """,
            user.id,  # type: ignore[attr-defined]
            player["id"],
        )
        if not exists:
            await conn.execute(
                """
                INSERT INTO friendships (id, requester_id, addressee_id, status)
                VALUES ($1, $2, $3, 'pending')
                """,
                uuid.uuid4(),
                user.id,  # type: ignore[attr-defined]
                player["id"],
            )
    return RedirectResponse(f"/players/{player['username']}", status_code=303)


@router.post("/players/{username}/unfriend")
async def profile_unfriend(request: Request, username: str) -> Response:
    user = _user_or_login(request)
    if isinstance(user, Response):
        return user
    loaded = await _load_player(request, username)
    if isinstance(loaded, Response):
        return loaded
    player, _played, _counted, _online, _purse = loaded
    async with request.app.state.pool.acquire() as conn:
        await conn.execute(
            """
            DELETE FROM friendships
            WHERE (requester_id = $1 AND addressee_id = $2)
               OR (requester_id = $2 AND addressee_id = $1)
            """,
            user.id,  # type: ignore[attr-defined]
            player["id"],
        )
    return RedirectResponse(f"/players/{player['username']}", status_code=303)


def _grant_amount(raw: str, purse: int) -> tuple[int | None, str]:
    text = raw.strip()
    if not text.isdigit() or len(text) > 6:
        return None, "Укажите, сколько фишек добавить: от 1 до 100 000."
    amount = int(text)
    if not 1 <= amount <= _CHIP_CAP:
        return None, "Укажите, сколько фишек добавить: от 1 до 100 000."
    if purse + amount > _CHIP_CAP:
        return None, "После начисления на счёте может быть не больше 100 000 фишек."
    return amount, ""


async def _load_player(
    request: Request,
    username: str,
) -> tuple[dict[str, object], list[object], list[object], bool, int] | Response:
    login = username.strip().lower()
    if not _LOGIN.fullmatch(login):
        return error_response(request, 404, note="Такого игрока нет.")
    async with request.app.state.pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, username, full_name, avatar, created_at, last_seen
            FROM users
            WHERE username = $1 AND is_active = TRUE
            """,
            login,
        )
        if row is None:
            return error_response(request, 404, note="Такого игрока нет.")
        played = await conn.fetch(
            """
            SELECT g.game_type, g.result, g.result_reason, g.player_side, g.user_id, g.updated_at,
                   (
                       SELECT s.seat_key FROM game_seats AS s
                       WHERE s.game_id = g.id AND s.user_id = $1
                       LIMIT 1
                   ) AS seat_key,
                   CASE
                       WHEN g.result = 'draw'
                        AND g.game_type IN ('durak', 'blackjack', 'poker', 'preferans')
                       THEN g.current_position
                   END AS finish_position
            FROM games AS g
            WHERE g.status = 'finished'
              AND (
                    g.user_id = $1 OR g.opponent_id = $1
                    OR EXISTS (
                        SELECT 1 FROM game_seats AS s
                        WHERE s.game_id = g.id AND s.user_id = $1
                    )
              )
            """,
            row["id"],
        )
        counted = await games_repo.stats_rows(conn, row["id"])
        purse = await balance(conn, row["id"])
    seen = row["last_seen"]
    moment = seen if isinstance(seen, datetime) else None
    if moment is not None and moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    online = moment is not None and datetime.now(UTC) - moment < timedelta(minutes=2)
    player = dict(row)
    player["full_name"] = shown(player.get("full_name"), "")
    return player, list(played), list(counted), online, purse


async def _profile_page(
    request: Request,
    user: object,
    player: dict[str, object],
    played: list[object],
    counted: list[object],
    online: bool,
    purse: int,
    *,
    chips_added: bool = False,
    chip_error: str = "",
    friend_error: str = "",
    status: int = 200,
) -> Response:
    prefs = await _prefs(request, user.id)  # type: ignore[attr-defined]
    friend_state = await _friend_state(request, user.id, player["id"])  # type: ignore[attr-defined]
    return render(
        request,
        "players/profile.html",
        {
            "player": player,
            "stats": tally([dict(item) for item in played], player["id"]),
            "breakdown": _summarize(counted, player["id"]),
            "online": online,
            "player_chips": purse,
            "chips_added": chips_added,
            "chip_error": chip_error,
            "friend_state": friend_state,
            "friend_error": friend_error,
            "theme": prefs["theme"],
            "board_style": prefs["board_style"],
        },
        status=status,
    )


async def _friend_state(request: Request, viewer_id: object, player_id: object) -> str:
    if viewer_id == player_id:
        return "self"
    async with request.app.state.pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT status, requester_id
            FROM friendships
            WHERE (requester_id = $1 AND addressee_id = $2)
               OR (requester_id = $2 AND addressee_id = $1)
            """,
            viewer_id,
            player_id,
        )
    if row is None:
        return "none"
    if row["status"] == "accepted":
        return "accepted"
    if row["requester_id"] == viewer_id:
        return "outgoing"
    return "incoming"


async def _board_page(request: Request, game_id: uuid.UUID, *, analysis: bool) -> Response:
    user = _user_or_login(request)
    if isinstance(user, Response):
        return user
    try:
        state = await request.app.state.service.view(user, game_id)
        if state.get("watching") and state.get("audience") == "open":
            async with request.app.state.pool.acquire() as conn:
                await games_repo.add_watcher(conn, game_id, user.id)
    except AppError as exc:
        if exc.code == "adult_only":
            prefs = await _prefs(request, user.id)
            return render(
                request,
                "games/blocked.html",
                {"age_block": exc.message, "theme": prefs["theme"], "board_style": prefs["board_style"]},
                status=403,
            )
        if exc.status == 404:
            return error_response(request, 404, note=exc.message)
        raise
    if analysis and state.get("game_type") == "domino":
        return RedirectResponse(f"/games/{game_id}", status_code=303)
    prefs = await _prefs(request, user.id)
    return render(
        request,
        "games/play.html",
        {
            "state": state,
            "state_json": safe_json(state),
            "analysis": analysis,
            "theme": prefs["theme"],
            "board_style": prefs["board_style"],
        },
    )


def _elapsed(started: datetime) -> str:
    moment = started if started.tzinfo is not None else started.replace(tzinfo=UTC)
    minutes = max(0, int((datetime.now(UTC) - moment).total_seconds() // 60))
    if minutes < 1:
        return "меньше минуты"
    if minutes < 60:
        return _phrase(minutes, "минуту", "минуты", "минут")
    return _phrase(minutes // 60, "час", "часа", "часов")


def _person_name(full: object, login: object, fallback: object = "") -> str:
    name = called(full, login)
    if name:
        return name
    text = str(fallback or "")
    return "" if text == "None" else text


def _roster_names(raw: object) -> list[str]:
    names: list[str] = []
    for item in str(raw or "").split("\x1d"):
        if "\x1e" not in item:
            continue
        full, _, login = item.partition("\x1e")
        name = _person_name(full, login)
        if name and name not in names:
            names.append(name)
    return names


def _shown_names(raw: object) -> list[str]:
    return [name for name in str(raw or "").split("\x1f") if name and name != "None"]


def _table_players(row: Any, *, vacancies: int, waiting: bool, cpu_label: str) -> str:
    creator = _person_name(row.get("creator_full"), row.get("creator_login"), row.get("creator_name"))
    seated = _roster_names(row.get("human_roster")) or _shown_names(row.get("human_names"))
    if row["mode"] == "vs_computer" and vacancies == 0:
        return f"{creator} · {cpu_label}" if cpu_label else creator
    names: list[str] = [creator] if creator else []
    for name in seated:
        if name not in names:
            names.append(name)
    rival = _person_name(row.get("opponent_full"), row.get("opponent_login"), row.get("opponent_name"))
    if rival and rival not in names:
        names.append(rival)
    if waiting and len(names) < 2:
        return creator
    if len(names) == 2:
        return f"{names[0]} — {names[1]}"
    if len(names) > 2:
        return " · ".join(names)
    return creator


def _phrase(count: int, one: str, few: str, many: str) -> str:
    tail, hundred = count % 10, count % 100
    if tail == 1 and hundred != 11:
        word = one
    elif 2 <= tail <= 4 and not 12 <= hundred <= 14:
        word = few
    else:
        word = many
    return f"{count} {word}"


async def _live_refusal(request: Request, user: object, exc: AppError) -> Response:
    blocked = exc.code == "adult_only"
    return await _live_page(
        request,
        user,
        error=None if blocked else exc.message,
        age_block=exc.message if blocked else "",
        status=exc.status,
    )


async def live_tables(request: Request, user: object) -> dict[str, object]:
    async with request.app.state.pool.acquire() as conn:
        rows = await games_repo.list_live_tables(conn, user.id)  # type: ignore[attr-defined]
        born = await conn.fetchval("SELECT born_on FROM users WHERE id = $1", user.id)  # type: ignore[attr-defined]
    born_on = born if isinstance(born, date) else None
    tables: list[dict[str, object]] = []
    for row in rows:
        mine = row["user_id"] == user.id or row["opponent_id"] == user.id or row["seated"]  # type: ignore[attr-defined]
        open_table = row["audience"] == "open"
        vacancies = int(row["vacancies"])
        waiting = row["status"] == "waiting" or (row["mode"] == "online" and not row["opponent_name"] and vacancies > 0)
        cpu_label = ""
        creator_name = _person_name(row["creator_full"], row["creator_login"], row["creator_name"])
        rival_name = _person_name(row["opponent_full"], row["opponent_login"], row["opponent_name"])
        if row["mode"] == "vs_computer":
            names = computer_names(
                row["id"],
                row["player_side"],
                row["cpu_seats"],
                [creator_name, rival_name, *_roster_names(row["human_roster"])],
            )
            cpu_label = ", ".join(names)
        if row["mode"] == "vs_computer" and vacancies == 0:
            waiting = False
        players = _table_players(row, vacancies=vacancies, waiting=waiting, cpu_label=cpu_label)
        moves = int(row["moves"])
        watchers = int(row["watchers"])
        seats = int(row["seats"])
        details: list[str] = []
        if seats:
            place = _phrase(seats, "место", "места", "мест").split(" ", 1)[1]
            details.append(f"{max(0, seats - vacancies)} из {seats} {place}")
        elif waiting and vacancies:
            details.append(f"Свободно мест: {vacancies}")
        elif waiting:
            details.append("Ждёт соперника")
        if not waiting:
            details.append(_elapsed(row["created_at"]))
        if moves:
            details.append(_phrase(moves, "ход", "хода", "ходов"))
        if watchers:
            watch_label = _phrase(watchers, "наблюдатель", "наблюдателя", "наблюдателей")
        else:
            watch_label = "Без наблюдателей"
        blocked = adult_message(born_on, str(row["game_type"])) is not None
        tables.append(
            {
                "id": row["id"],
                "game_type": row["game_type"],
                "open": open_table,
                "mine": mine,
                "players": players,
                "cpu_label": cpu_label,
                "initial": creator_name.strip()[:1].upper(),
                "creator": creator_name,
                "creator_login": row["creator_login"],
                "creator_avatar": row["creator_avatar"] or "",
                "opponent": rival_name,
                "opponent_login": row["opponent_login"] or "",
                "opponent_avatar": row["opponent_avatar"] or "",
                "computer": row["mode"] == "vs_computer",
                "mode_label": "С компьютером" if row["mode"] == "vs_computer" else "С человеком",
                "meta": " · ".join(details),
                "chips": row["game_type"] == "poker",
                "watch_label": watch_label,
                "poker_blocked": blocked,
                "age_block": adult_message(born_on, str(row["game_type"])) or "",
                "can_sit": open_table and not mine and not blocked and vacancies > 0,
                "can_watch": open_table and not mine and not blocked,
                "vacancies": vacancies,
            }
        )
    return {
        "tables": tables,
        "open_count": sum(1 for item in tables if item["open"]),
        "closed_count": sum(1 for item in tables if not item["open"]),
        "mine_count": sum(1 for item in tables if item["mine"]),
    }


async def _live_page(
    request: Request,
    user: object,
    *,
    error: str | None = None,
    age_block: str = "",
    status: int = 200,
) -> Response:
    board = await live_tables(request, user)
    prefs = await _prefs(request, user.id)  # type: ignore[attr-defined]
    return render(
        request,
        "games/live.html",
        {
            **board,
            "error": error,
            "age_block": age_block,
            "theme": prefs["theme"],
            "board_style": prefs["board_style"],
        },
        status=status,
    )


def _birth_facts(born: date | None) -> dict[str, object]:
    years = age_years(born) if born else None
    return {
        "born": born,
        "age_years": years,
        "adult": years is not None and years >= 18,
        "born_label": format_born(born) if born else "",
        "age_label": years_phrase(years) if years is not None else "",
    }


def _posted_born(form) -> date | None:
    day = str(form.get("born_day") or "")
    month = str(form.get("born_month") or "")
    year = str(form.get("born_year") or "")
    try:
        return born_from_parts(day, month, year)
    except ValueError as exc:
        raise AppError(422, "bad_date", str(exc)) from exc


async def _stored_born(request: Request, user_id: object) -> date | None:
    async with request.app.state.pool.acquire() as conn:
        born = await conn.fetchval("SELECT born_on FROM users WHERE id = $1", user_id)
    return born if isinstance(born, date) else None


async def _birth(request: Request, user_id: object) -> dict[str, object]:
    return _birth_facts(await _stored_born(request, user_id))


async def _settings_page(
    request: Request,
    user: object,
    *,
    saved: bool = False,
    error: str | None = None,
    password_error: str | None = None,
    password_saved: bool = False,
    born: date | None = None,
    preview: bool = False,
    name: tuple[str, str, str] | None = None,
) -> Response:
    prefs = await _prefs(request, user.id)  # type: ignore[attr-defined]
    facts = _birth_facts(born) if preview else await _birth(request, user.id)  # type: ignore[attr-defined]
    family, given, patronymic = name if name is not None else split_full_name(getattr(user, "full_name", ""))
    policy = await current_policy(request)
    return render(
        request,
        "settings/index.html",
        {
            "prefs": prefs,
            "theme": prefs["theme"],
            "board_style": prefs["board_style"],
            "saved": saved,
            "error": error,
            "password_error": password_error,
            "password_saved": password_saved,
            "password_rules": password_requirements(
                minimum=policy.password_min,
                letter=policy.password_needs_letter,
                digit=policy.password_needs_digit,
            ),
            "password_min": policy.password_min,
            "password_letter": policy.password_needs_letter,
            "password_digit": policy.password_needs_digit,
            "year_now": date.today().year,
            "family": family,
            "given": given,
            "patronymic": patronymic,
            "referral_link": await _referral_link(request, user.id),  # type: ignore[attr-defined]
            **facts,
        },
    )


async def _prefs(request: Request, user_id: object) -> dict[str, object]:
    async with request.app.state.pool.acquire() as conn:
        row = await settings_repo.get_settings(conn, user_id)  # type: ignore[arg-type]
    data = dict(row)
    data["analysis_preferences"] = as_preferences(data["analysis_preferences"])
    return data


async def _store_settings(request: Request, user_id: object, body: SettingsBody) -> None:
    preferences = {
        "chess_depth": body.chess_depth,
        "chess_time_ms": body.chess_time_ms,
        "chess_multipv": body.chess_multipv,
        "checkers_level": body.checkers_level,
        "checkers_time_ms": body.checkers_time_ms,
        "variety": False,
    }
    game = body.default_game
    async with request.app.state.pool.acquire() as conn:
        if game in ADULT_GAMES and not await is_adult(conn, user_id):  # type: ignore[arg-type]
            game = "chess"
        await settings_repo.update_settings(
            conn,
            user_id,  # type: ignore[arg-type]
            theme=body.theme,
            board_style=body.board_style,
            default_game=game,
            default_side=body.default_side,
            analysis_preferences=preferences,
        )


async def _landing(request: Request) -> Response:
    async with request.app.state.pool.acquire() as conn:
        posts = await news.list_news(conn, limit=3)
    response = render(request, "public/home.html", {"posts": posts, "public_page": True})
    code = request.query_params.get("ref", "")
    if _REFERRAL.fullmatch(code):
        response.set_cookie(
            "pn_ref",
            code,
            max_age=30 * 24 * 3600,
            httponly=True,
            secure=request.app.state.settings.cookie_secure,
            samesite="lax",
            path="/",
        )
    return response


async def _referral_link(request: Request, user_id: object) -> str:
    async with request.app.state.pool.acquire() as conn:
        code = await users.referral_code(conn, user_id)  # type: ignore[arg-type]
    origin = str(request.base_url).rstrip("/")
    return f"{origin}/?ref={code}"


def _earn_note(amount: int, reason: str) -> str:
    if reason == "pot":
        return "Выигрыш"
    if amount == 30:
        return "Победа"
    if amount == 10:
        return "Ничья"
    return "За партию"


async def _chip_events(conn: object, user_id: uuid.UUID) -> list[dict[str, object]]:
    games = await conn.fetch(  # type: ignore[attr-defined]
        """
        SELECT l.amount, l.reason, l.created_at, g.id AS game_id, g.game_type
        FROM ledger l
        LEFT JOIN games g ON g.id = l.game_id
        WHERE l.user_id = $1 AND l.amount > 0 AND l.reason IN ('table', 'pot')
        ORDER BY l.created_at DESC
        """,
        user_id,
    )
    people = await conn.fetch(  # type: ignore[attr-defined]
        """
        SELECT id, full_name, username, avatar, created_at
        FROM users
        WHERE referred_by = $1
        ORDER BY created_at DESC
        """,
        user_id,
    )
    credits = await conn.fetch(  # type: ignore[attr-defined]
        """
        SELECT amount, created_at
        FROM ledger
        WHERE user_id = $1 AND reason = 'referral' AND amount > 0
        ORDER BY created_at DESC
        """,
        user_id,
    )
    grants = await conn.fetch(  # type: ignore[attr-defined]
        """
        SELECT amount, created_at
        FROM ledger
        WHERE user_id = $1 AND reason = 'admin' AND amount > 0
        ORDER BY created_at DESC
        """,
        user_id,
    )
    used: set[int] = set()
    events: list[dict[str, object]] = [
        {
            "kind": "game",
            "amount": int(row["amount"]),
            "at": row["created_at"],
            "game_id": row["game_id"],
            "game_type": row["game_type"],
            "note": _earn_note(int(row["amount"]), str(row["reason"])),
            "person_name": None,
            "username": None,
            "avatar": None,
        }
        for row in games
    ]
    for person in people:
        match: int | None = None
        gap: float | None = None
        for index, credit in enumerate(credits):
            if index in used:
                continue
            seconds = abs((person["created_at"] - credit["created_at"]).total_seconds())
            if seconds <= 120 and (gap is None or seconds < gap):
                match = index
                gap = seconds
        when = person["created_at"]
        amount: int | None = None
        if match is not None:
            used.add(match)
            when = credits[match]["created_at"]
            amount = int(credits[match]["amount"])
        events.append(
            {
                "kind": "referral",
                "amount": amount,
                "at": when,
                "game_id": None,
                "game_type": None,
                "note": "зарегистрировался по вашей ссылке",
                "person_name": shown(person["full_name"], person["username"]),
                "username": person["username"],
                "avatar": person["avatar"],
            }
        )
    for row in grants:
        events.append(
            {
                "kind": "grant",
                "amount": int(row["amount"]),
                "at": row["created_at"],
                "game_id": None,
                "game_type": None,
                "note": "Начисление",
                "person_name": None,
                "username": None,
                "avatar": None,
            }
        )
    for index, credit in enumerate(credits):
        if index in used:
            continue
        events.append(
            {
                "kind": "referral",
                "amount": int(credit["amount"]),
                "at": credit["created_at"],
                "game_id": None,
                "game_type": None,
                "note": "гость зарегистрировался по вашей ссылке",
                "person_name": None,
                "username": None,
                "avatar": None,
            }
        )
    events.sort(key=lambda item: item["at"], reverse=True)  # type: ignore[arg-type, return-value]
    return events


def _int(value: object, default: int) -> int:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return default
