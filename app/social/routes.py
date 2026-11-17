"""Друзья, вызовы, переписка, возраст и обзор гостиной."""

from __future__ import annotations

import re
import uuid
from datetime import UTC, date, datetime, timedelta

import asyncpg
from fastapi import APIRouter, Request
from starlette.responses import JSONResponse, RedirectResponse, Response

from app.cards.registry import ADULT_GAMES
from app.catalog import GAMES, visible_games
from app.clock import current_zone
from app.db.repositories import games as games_repo
from app.db.repositories.users import User
from app.errors import AppError
from app.games.present import computer_names
from app.geo import device_label
from app.names import shown
from app.paging import clamp_page, page_count, page_links, read_page, window
from app.site_policy import current
from app.social.notices import _TABLE_READY, fresh_notices, mark_chat_read, nav_counts, unread_threads
from app.templating import render
from app.wallet import adult_denial, format_born, is_adult, parse_born_text

router = APIRouter()
_SEEK_SEATS = {
    "uno": (2, 6),
    "poker": (2, 6),
    "durak": (2, 6),
    "blackjack": (2, 6),
    "preferans": (3, 3),
}
ONLINE_FOR = timedelta(minutes=2)
_OVERVIEW_GAMES = 8
_OVERVIEW_PEOPLE = 10
_OVERVIEW_SESSIONS = 10
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
_INVITE = re.compile(r"Зову за стол(?:: (?P<title>[^.]+))?\.\s*Код (?P<code>[a-z0-9]{8})", re.IGNORECASE)


def _seek_seats(game: str, raw: object) -> int:
    bounds = _SEEK_SEATS.get(game)
    if bounds is None:
        return 2
    low, high = bounds
    try:
        seats = int(str(raw))
    except (TypeError, ValueError):
        return low
    return min(high, max(low, seats))


def _user(request: Request) -> User | Response:
    if request.state.user is None:
        return RedirectResponse("/login", status_code=303)
    return request.state.user


def _admin(request: Request) -> User | Response:
    user = _user(request)
    if isinstance(user, Response):
        return user
    if not user.is_admin:
        raise AppError(404, "not_found", "Страница не найдена.")
    return user


async def _pace(request: Request, bucket: str, limit: int) -> None:
    allowed = await request.app.state.gate.allow(bucket, limit, 60)
    if not allowed:
        raise AppError(429, "rate_limited", "Слишком много запросов. Подождите минуту.")


def _page(request: Request, name: str, context: dict[str, object], status: int = 200) -> Response:
    return render(request, name, context, status=status)


@router.get("/friends")
async def friends_page(request: Request) -> Response:
    user = _user(request)
    if isinstance(user, Response):
        return user
    async with request.app.state.pool.acquire() as conn:
        context = await _friends_context(conn, user.id)
        adult = await is_adult(conn, user.id)
    return _page(request, "social/friends.html", {**context, "error": None, "games": visible_games(adult)})


@router.post("/friends")
async def friend_request(request: Request) -> Response:
    user = _user(request)
    if isinstance(user, Response):
        return user
    await _pace(request, f"friend:{user.id}", 10)
    form = await request.form()
    username = str(form.get("username") or "").strip().lower()
    try:
        async with request.app.state.pool.acquire() as conn:
            other = await conn.fetchrow(
                "SELECT id, username FROM users WHERE username = $1 AND is_active = TRUE",
                username,
            )
            if other is None or other["id"] == user.id:
                raise AppError(404, "not_found", "Такого игрока нет.")
            exists = await conn.fetchval(
                """
                SELECT 1 FROM friendships
                WHERE (requester_id = $1 AND addressee_id = $2)
                   OR (requester_id = $2 AND addressee_id = $1)
                """,
                user.id,
                other["id"],
            )
            if exists:
                raise AppError(409, "already_friends", "Запрос уже есть.")
            await conn.execute(
                """
                INSERT INTO friendships (id, requester_id, addressee_id, status)
                VALUES ($1, $2, $3, 'pending')
                """,
                uuid.uuid4(),
                user.id,
                other["id"],
            )
    except AppError as exc:
        async with request.app.state.pool.acquire() as conn:
            context = await _friends_context(conn, user.id)
            adult = await is_adult(conn, user.id)
        return _page(
            request,
            "social/friends.html",
            {**context, "error": exc.message, "games": visible_games(adult)},
            exc.status,
        )
    return RedirectResponse("/friends", status_code=303)


@router.post("/friends/{friendship_id}/accept")
async def friend_accept(request: Request, friendship_id: uuid.UUID) -> Response:
    user = _user(request)
    if isinstance(user, Response):
        return user
    async with request.app.state.pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE friendships SET status = 'accepted'
            WHERE id = $1 AND addressee_id = $2 AND status = 'pending'
            """,
            friendship_id,
            user.id,
        )
    return RedirectResponse("/friends", status_code=303)


@router.post("/friends/{friendship_id}/decline")
async def friend_decline(request: Request, friendship_id: uuid.UUID) -> Response:
    user = _user(request)
    if isinstance(user, Response):
        return user
    async with request.app.state.pool.acquire() as conn:
        await conn.execute(
            """
            DELETE FROM friendships
            WHERE id = $1 AND (requester_id = $2 OR addressee_id = $2)
            """,
            friendship_id,
            user.id,
        )
    return RedirectResponse("/friends", status_code=303)


@router.post("/friends/{friendship_id}/challenge")
async def friend_challenge(request: Request, friendship_id: uuid.UUID) -> Response:
    user = _user(request)
    if isinstance(user, Response):
        return user
    form = await request.form()
    game_type = str(form.get("game_type") or "chess")
    if game_type not in GAMES:
        raise AppError(422, "bad_game", "Выберите игру из каталога.")
    async with request.app.state.pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT requester_id, addressee_id FROM friendships
            WHERE id = $1 AND status = 'accepted'
              AND (requester_id = $2 OR addressee_id = $2)
            """,
            friendship_id,
            user.id,
        )
    if row is None:
        raise AppError(404, "not_found", "Друг не найден.")
    other_id = row["addressee_id"] if row["requester_id"] == user.id else row["requester_id"]
    state = await request.app.state.service.create(
        user,
        {
            "game_type": game_type,
            "mode": "online",
            "player_side": "white",
            "engine_level": 3,
            "engine_time_ms": 1000,
        },
    )
    code = state.get("join_code") or ""
    async with request.app.state.pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO messages (sender_id, recipient_id, body)
            VALUES ($1, $2, $3)
            """,
            user.id,
            other_id,
            f"Зову за стол: {GAMES[game_type].title}. Код {code}. Откройте /join?code={code}",
        )
    return RedirectResponse(f"/games/{state['id']}", status_code=303)


@router.get("/lobby")
async def lobby_page(request: Request) -> Response:
    user = _user(request)
    if isinstance(user, Response):
        return user
    async with request.app.state.pool.acquire() as conn:
        seekers = await conn.fetch(
            """
            SELECT s.user_id, s.game_type, s.seats, s.created_at, u.username, u.full_name, u.avatar
            FROM seekers AS s
            JOIN users AS u ON u.id = s.user_id
            WHERE s.created_at > now() - interval '15 minutes'
            ORDER BY s.created_at DESC
            """
        )
        online = await conn.fetch(
            """
            SELECT username, full_name, avatar, last_seen, last_country
            FROM users
            WHERE is_active = TRUE
              AND id <> $1
              AND last_seen > now() - interval '2 minutes'
            ORDER BY username
            """,
            user.id,
        )
        adult = await is_adult(conn, user.id)
        if not adult:
            seekers = [row for row in seekers if row["game_type"] not in {"poker", "blackjack", "preferans"}]
        seekers = [_named(row) for row in seekers]
        online = [_named(row) for row in online]
        live_count = await conn.fetchval(
            """
            SELECT count(*)
            FROM games
            WHERE mode IN ('online', 'vs_computer')
              AND status IN ('waiting', 'active')
            """
        )
    return _page(
        request,
        "social/lobby.html",
        {
            "seekers": seekers,
            "online": online,
            "live_count": int(live_count or 0),
            "games": visible_games(adult),
            "error": None,
        },
    )


@router.post("/lobby/seek")
async def lobby_seek(request: Request) -> Response:
    user = _user(request)
    if isinstance(user, Response):
        return user
    form = await request.form()
    game_type = str(form.get("game_type") or "chess")
    policy = await current(request)
    if game_type not in GAMES or not policy.allows(game_type):
        raise AppError(422, "bad_game", "Эта игра сейчас закрыта.")
    if game_type in ADULT_GAMES:
        async with request.app.state.pool.acquire() as conn:
            reason = await adult_denial(conn, user.id, game_type)
        if reason:
            raise AppError(403, "adult_only", reason)
    seats = _seek_seats(game_type, form.get("seats"))
    async with request.app.state.pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO seekers (user_id, game_type, seats, created_at)
            VALUES ($1, $2, $3, now())
            ON CONFLICT (user_id) DO UPDATE
            SET game_type = EXCLUDED.game_type, seats = EXCLUDED.seats, created_at = now()
            """,
            user.id,
            game_type,
            seats,
        )
    return RedirectResponse("/lobby", status_code=303)


@router.post("/lobby/cancel")
async def lobby_cancel(request: Request) -> Response:
    user = _user(request)
    if isinstance(user, Response):
        return user
    async with request.app.state.pool.acquire() as conn:
        await conn.execute("DELETE FROM seekers WHERE user_id = $1", user.id)
    return RedirectResponse("/lobby", status_code=303)


@router.post("/lobby/accept/{seeker_id}")
async def lobby_accept(request: Request, seeker_id: uuid.UUID) -> Response:
    user = _user(request)
    if isinstance(user, Response):
        return user
    if seeker_id == user.id:
        raise AppError(422, "bad_game", "Свой вызов принять нельзя.")
    async with request.app.state.pool.acquire() as conn:
        seeker_row = await conn.fetchrow(
            """
            SELECT u.id, u.username, u.role, s.game_type, s.seats
            FROM seekers AS s
            JOIN users AS u ON u.id = s.user_id
            WHERE s.user_id = $1
            """,
            seeker_id,
        )
    if seeker_row is None:
        raise AppError(404, "not_found", "Игрок уже сел за другой стол.")
    seeker = User(id=seeker_row["id"], username=seeker_row["username"], role=seeker_row["role"])
    game_type = str(seeker_row["game_type"])
    seats = _seek_seats(game_type, seeker_row["seats"])
    payload: dict[str, object] = {
        "game_type": game_type,
        "mode": "online",
        "player_side": "white",
        "engine_level": 3,
        "engine_time_ms": 1000,
    }
    if game_type in _SEEK_SEATS and seats > 2:
        payload["computers"] = 0
        payload["open_seats"] = seats - 1
    state = await request.app.state.service.create(seeker, payload)
    game_id = await request.app.state.service.join(user, str(state.get("join_code") or ""))
    async with request.app.state.pool.acquire() as conn:
        await conn.execute("DELETE FROM seekers WHERE user_id = $1", seeker_id)
        await conn.execute(
            "INSERT INTO messages (sender_id, recipient_id, body) VALUES ($1, $2, $3)",
            user.id,
            seeker_id,
            "Я сел за ваш стол.",
        )
    return RedirectResponse(f"/games/{game_id}", status_code=303)


@router.get("/api/v1/notices")
async def notices(request: Request) -> JSONResponse:
    user = request.state.user
    if user is None:
        raise AppError(401, "unauthorized", "Нужно войти в систему.")
    async with request.app.state.pool.acquire() as conn:
        items = await fresh_notices(conn, user.id)
        counts = await nav_counts(conn, user.id)
        threads = await unread_threads(conn, user.id)
    return JSONResponse({"items": items, "counts": counts, "threads": threads})


@router.get("/chats")
async def chats_page(request: Request) -> Response:
    user = _user(request)
    if isinstance(user, Response):
        return user
    async with request.app.state.pool.acquire() as conn:
        context = await _chats_context(conn, user)
    return _page(request, "social/chats.html", {**context, "error": None})


@router.post("/chats/open")
async def chat_open(request: Request) -> Response:
    user = _user(request)
    if isinstance(user, Response):
        return user
    form = await request.form()
    username = str(form.get("username") or "").strip().lower()
    async with request.app.state.pool.acquire() as conn:
        other = await conn.fetchrow(
            "SELECT id FROM users WHERE username = $1 AND is_active = TRUE",
            username,
        )
        if other is None or other["id"] == user.id:
            context = await _chats_context(conn, user)
            return _page(
                request,
                "social/chats.html",
                {**context, "error": "Такого игрока нет."},
                404,
            )
    return RedirectResponse(f"/chats/{username}", status_code=303)


@router.get("/chats/{username}")
async def thread_page(request: Request, username: str) -> Response:
    user = _user(request)
    if isinstance(user, Response):
        return user
    async with request.app.state.pool.acquire() as conn:
        other = await conn.fetchrow(
            "SELECT id, username, full_name, avatar, last_seen FROM users WHERE username = $1",
            username.lower(),
        )
        if other is None or other["id"] == user.id:
            raise AppError(404, "not_found", "Такого игрока нет.")
        await mark_chat_read(conn, user.id, other["id"])
        request.state.nav_counts = await nav_counts(conn, user.id)
        messages = await _thread(conn, user.id, other["id"])
        context = await _chats_context(conn, user, other=other, messages=messages)
    return _page(request, "social/chats.html", {**context, "error": None})


@router.post("/chats/{username}")
async def thread_send(request: Request, username: str) -> Response:
    user = _user(request)
    if isinstance(user, Response):
        return user
    form = await request.form()
    body = " ".join(str(form.get("body") or "").split())
    if not body or len(body) > 1000:
        raise AppError(422, "bad_message", "Сообщение должно быть от 1 до 1000 символов.")
    await _pace(request, f"chat:{user.id}", 30)
    async with request.app.state.pool.acquire() as conn:
        other = await conn.fetchrow("SELECT id FROM users WHERE username = $1", username.lower())
        if other is None or other["id"] == user.id:
            raise AppError(404, "not_found", "Такого игрока нет.")
        await conn.execute(
            "INSERT INTO messages (sender_id, recipient_id, body) VALUES ($1, $2, $3)",
            user.id,
            other["id"],
            body,
        )
    return RedirectResponse(f"/chats/{username.lower()}", status_code=303)


@router.get("/age")
async def age_page(request: Request) -> Response:
    user = _user(request)
    if isinstance(user, Response):
        return user
    return RedirectResponse("/settings", status_code=303)


@router.post("/age")
async def age_save(request: Request) -> Response:
    user = _user(request)
    if isinstance(user, Response):
        return user
    form = await request.form()
    try:
        born = parse_born_text(str(form.get("born_on") or ""))
    except ValueError as exc:
        raise AppError(422, "bad_date", "Укажите дату рождения.") from exc
    if form.get("confirm") != "yes":
        raise AppError(422, "bad_date", "Подтвердите, что дата указана верно.")
    async with request.app.state.pool.acquire() as conn:
        await conn.execute("UPDATE users SET born_on = $2, updated_at = now() WHERE id = $1", user.id, born)
    return RedirectResponse("/settings", status_code=303)


async def _require_table(conn: asyncpg.Connection, game_id: uuid.UUID, user_id: uuid.UUID) -> None:
    if await games_repo.get_visible(conn, game_id, user_id) is None:
        raise AppError(404, "not_found", "Партия не найдена.")


@router.get("/api/v1/games/{game_id}/chat")
async def table_chat(request: Request, game_id: uuid.UUID) -> JSONResponse:
    user = request.state.user
    if user is None:
        raise AppError(401, "unauthorized", "Нужно войти в систему.")
    async with request.app.state.pool.acquire() as conn:
        await _require_table(conn, game_id, user.id)
        rows = await conn.fetch(
            """
            SELECT m.body, m.created_at,
                   shown_name(u.full_name, u.username) AS username,
                   u.username AS login, u.avatar
            FROM messages AS m
            JOIN users AS u ON u.id = m.sender_id
            WHERE m.game_id = $1
            ORDER BY m.created_at
            LIMIT 80
            """,
            game_id,
        )
    payload = [
        {
            "body": row["body"],
            "username": row["username"],
            "login": row["login"],
            "avatar": row["avatar"] or "",
            "at": row["created_at"].isoformat(),
        }
        for row in rows
    ]
    return JSONResponse({"messages": payload})


@router.post("/api/v1/games/{game_id}/chat")
async def table_chat_send(request: Request, game_id: uuid.UUID) -> JSONResponse:
    user = request.state.user
    if user is None:
        raise AppError(401, "unauthorized", "Нужно войти в систему.")
    payload = await request.json()
    body = " ".join(str(payload.get("body") or "").split())
    if not body or len(body) > 1000:
        raise AppError(422, "bad_message", "Сообщение должно быть от 1 до 1000 символов.")
    await _pace(request, f"chat:{user.id}", 30)
    async with request.app.state.pool.acquire() as conn:
        await _require_table(conn, game_id, user.id)
        await conn.execute(
            "INSERT INTO messages (sender_id, game_id, body) VALUES ($1, $2, $3)",
            user.id,
            game_id,
            body,
        )
    return JSONResponse({"saved": True})


_REASONS = {
    "checkmate": "Мат",
    "stalemate": "Пат",
    "resign": "Сдача",
    "insufficient_material": "Мало материала",
    "fifty_moves": "50 ходов",
    "seventyfive_moves": "75 ходов",
    "threefold_repetition": "Троекратное повторение",
    "fivefold_repetition": "Пятикратное повторение",
    "no_moves": "Нет ходов",
    "repetition": "Повторение",
    "nonprogress": "Без прогресса",
    "technical_limit": "Технический предел",
    "left": "Выход из-за стола",
    "stopped": "Остановлена",
    "empty_hand": "Карты кончились",
    "showdown": "Вскрытие",
    "fold": "Пас",
    "split": "Банк пополам",
    "other": "Без указанной причины",
}
_LEVELS = ("Новичок", "Любитель", "Опытный", "Сильный", "Мастер")
_GAME_ORDER = ("chess", "checkers", "go", "uno", "poker", "durak", "blackjack", "preferans")


_RING = 263.89


def _donut(parts: list[tuple[str, int]]) -> dict[str, object]:
    visible = [(label, count) for label, count in parts if count > 0]
    source = visible or parts
    total = sum(count for _, count in visible)
    drawn: list[dict[str, object]] = []
    cursor = 0.0
    for index, (label, count) in enumerate(source):
        item: dict[str, object] = {"key": f"c{index % 6}", "label": label, "total": count}
        if count > 0 and total > 0:
            arc = _RING * count / total
            pad = 1.8 if arc > 6 and len(visible) > 1 else 0
            length = round(arc - pad, 2)
            item.update(
                {
                    "length": length,
                    "gap": round(_RING - length, 2),
                    "offset": round(-cursor, 2),
                    "draw": True,
                }
            )
            cursor += arc
        drawn.append(item)
    return {
        "slices": [item for item in drawn if item.get("draw")],
        "legend": drawn,
        "total": total,
    }


def _bars(parts: list[tuple[str, int]]) -> list[dict[str, object]]:
    peak = max((count for _, count in parts), default=0)
    return [
        {
            "label": label,
            "total": count,
            "bar": 0 if count <= 0 or peak <= 0 else max(8, round(100 * count / peak)),
        }
        for label, count in parts
    ]


def _shares(pairs: list[tuple[str, int]]) -> list[dict[str, object]]:
    whole = sum(count for _, count in pairs)
    if whole <= 0:
        return []
    rows = [(key, count, round(100 * count / whole)) for key, count in pairs if count]
    drift = 100 - sum(share for _, _, share in rows)
    if rows and drift:
        key, count, share = rows[0]
        rows[0] = (key, count, max(0, share + drift))
    return [{"key": key, "total": count, "share": share} for key, count, share in rows]


def _overview_games(
    by_type: list[asyncpg.Record],
    reasons: list[asyncpg.Record],
) -> list[dict[str, object]]:
    indexed = {str(row["game_type"]): row for row in by_type}
    grouped: dict[str, list[asyncpg.Record]] = {}
    for row in reasons:
        grouped.setdefault(str(row["game_type"]), []).append(row)
    cards: list[dict[str, object]] = []
    for key in _GAME_ORDER:
        raw = indexed.get(key)
        total = int(raw["total"]) if raw else 0
        white = int(raw["white_wins"]) if raw else 0
        black = int(raw["black_wins"]) if raw else 0
        draws = int(raw["draws"]) if raw else 0
        human = int(raw["human_wins"]) if raw else 0
        engine = int(raw["engine_wins"]) if raw else 0
        engine_draws = int(raw["engine_draws"]) if raw else 0
        computer = int(raw["vs_computer"]) if raw else 0
        finished_count = int(raw["finished"]) if raw else 0
        ranked = sorted(grouped.get(key, []), key=lambda item: int(item["total"]), reverse=True)
        reason_rows = [
            (_REASONS.get(str(row["reason"]), str(row["reason"])), int(row["total"])) for row in ranked[:6]
        ]
        reason_bars = [
            {"label": str(item["key"]), "total": int(item["total"]), "share": int(item["share"])}
            for item in _shares(reason_rows)
        ]
        cards.append(
            {
                "key": key,
                "total": total,
                "finished": finished_count,
                "active": int(raw["active"]) if raw else 0,
                "waiting": int(raw["waiting"]) if raw else 0,
                "white": white,
                "black": black,
                "draws": draws,
                "result_donut": _donut(
                    [
                        ("Белые", white),
                        ("Чёрные", black),
                        ("Ничьи", draws),
                        ("Не завершены", max(0, total - white - black - draws)),
                    ]
                ),
                "duel_donut": _donut(
                    [
                        ("Игрок", human),
                        ("Компьютер", engine),
                        ("Ничьи", engine_draws),
                        ("Не завершены", max(0, computer - human - engine - engine_draws)),
                    ]
                ),
                "results": _shares(
                    [
                        ("white", white),
                        ("black", black),
                        ("draw", draws),
                        ("rest", max(0, total - white - black - draws)),
                    ]
                ),
                "modes": [
                    ("С компьютером", computer),
                    ("Онлайн", int(raw["online"]) if raw else 0),
                    ("Свободная", int(raw["free_play"]) if raw else 0),
                    ("Анализ", int(raw["analysis"]) if raw else 0),
                    ("Разбор", int(raw["lesson"]) if raw else 0),
                ],
                "open_tables": int(raw["open_tables"]) if raw else 0,
                "computer": computer,
                "duel": _shares(
                    [
                        ("human", human),
                        ("engine", engine),
                        ("draw", engine_draws),
                        ("rest", max(0, computer - human - engine - engine_draws)),
                    ]
                ),
                "human": human,
                "engine": engine,
                "engine_draws": engine_draws,
                "avg_moves": int(raw["avg_moves"]) if raw else 0,
                "longest": int(raw["longest"]) if raw else 0,
                "reasons": reason_bars,
            }
        )
    return cards


def _overview_days(rows: list[asyncpg.Record]) -> tuple[list[dict[str, object]], dict[str, object]]:
    found = {row["day"]: int(row["total"]) for row in rows}
    today = datetime.now(current_zone()).date()
    peak = max([*found.values(), 1])
    width, height, pad_x, pad_top, pad_bottom = 640, 188, 18, 28, 16
    plot = height - pad_top - pad_bottom
    series: list[dict[str, object]] = []
    for offset in range(13, -1, -1):
        day = today - timedelta(days=offset)
        total = found.get(day, 0)
        index = 13 - offset
        x = pad_x + (width - 2 * pad_x) * (index / 13)
        y = pad_top + plot * (1 - total / peak)
        series.append(
            {
                "label": f"{day.day:02d}.{day.month:02d}",
                "total": total,
                "x": round(x, 1),
                "y": round(y, 1),
            }
        )
    baseline = height - pad_bottom
    spots = " ".join(f"{item['x']},{item['y']}" for item in series)
    area = f"{series[0]['x']},{baseline} {spots} {series[-1]['x']},{baseline}"
    chart = {
        "width": width,
        "height": height,
        "line": spots,
        "area": area,
        "baseline": baseline,
        "guides": [pad_top, round(pad_top + plot / 2, 1), baseline],
        "peak": peak if any(item["total"] for item in series) else 0,
    }
    return series, chart


def _overview_charts(
    numbers: dict[str, object],
    game_cards: list[dict[str, object]],
    guests: list[dict[str, object]],
    strength: list[dict[str, object]],
    session_totals: asyncpg.Record | None,
    session_users: list[asyncpg.Record],
    session_devices: list[asyncpg.Record],
) -> dict[str, object]:
    def count(key: str) -> int:
        value = numbers.get(key) or 0
        return int(value) if isinstance(value, int) else int(str(value))

    mode_counts = [0, 0, 0, 0, 0]
    reason_counts: dict[str, int] = {}
    for card in game_cards:
        modes = card["modes"]
        if isinstance(modes, list):
            for index, pair in enumerate(modes):
                if index < 5 and isinstance(pair, tuple):
                    mode_counts[index] += int(pair[1])
        reasons = card["reasons"]
        if isinstance(reasons, list):
            for reason in reasons:
                if isinstance(reason, dict):
                    label = str(reason["label"])
                    reason_counts[label] = reason_counts.get(label, 0) + int(reason["total"])
    ranked_reasons = sorted(reason_counts.items(), key=lambda item: (-item[1], item[0]))
    donut_reasons = ranked_reasons
    if len(ranked_reasons) > 6:
        rest = sum(total for _, total in ranked_reasons[5:])
        donut_reasons = [*ranked_reasons[:5], ("Остальные", rest)]
    white = sum(int(card["white"]) for card in game_cards)
    black = sum(int(card["black"]) for card in game_cards)
    draws = sum(int(card["draws"]) for card in game_cards)
    games_total = count("games")
    users_total = count("users")
    online = count("online")
    sessions_row = session_totals
    devices: dict[str, int] = {}
    for row in session_devices:
        label = device_label(row["user_agent"])
        devices[label] = devices.get(label, 0) + int(row["total"])
    return {
        "status_donut": _donut(
            [
                ("Идут", count("active_games")),
                ("Ждут", count("waiting_games")),
                ("Завершены", count("finished_games")),
            ]
        ),
        "mode_donut": _donut(
            [
                ("С компьютером", mode_counts[0]),
                ("Онлайн", mode_counts[1]),
                ("Свободная", mode_counts[2]),
                ("Анализ", mode_counts[3]),
                ("Разбор", mode_counts[4]),
            ]
        ),
        "audience_donut": _donut(
            [
                ("Открытые", count("open_games")),
                ("Закрытые", count("closed_games")),
            ]
        ),
        "message_donut": _donut(
            [
                ("Личные", count("personal_messages")),
                ("За столом", count("table_messages")),
            ]
        ),
        "type_donut": _donut([(_game_title(str(card["key"])), int(card["total"])) for card in game_cards]),
        "result_donut": _donut(
            [
                ("Белые", white),
                ("Чёрные", black),
                ("Ничьи", draws),
                ("Не завершены", max(0, games_total - white - black - draws)),
            ]
        ),
        "level_donut": _donut([(str(level["title"]), int(level["total"])) for level in strength]),
        "reason_donut": _donut(donut_reasons),
        "reason_bars": _bars(ranked_reasons),
        "people_game_donut": _donut([(str(person["username"]), int(person["games"])) for person in guests]),
        "people_win_donut": _donut([(str(person["username"]), int(person["wins"])) for person in guests]),
        "people_chip_donut": _donut([(str(person["username"]), int(person["balance"])) for person in guests]),
        "people_presence_donut": _donut(
            [
                ("В сети", online),
                ("Не в сети", max(0, users_total - online)),
            ]
        ),
        "people_game_bars": _bars([(str(person["username"]), int(person["games"])) for person in guests]),
        "people_win_bars": _bars([(str(person["username"]), int(person["wins"])) for person in guests]),
        "session_state_donut": _donut(
            [
                ("Открыты", int(sessions_row["live"]) if sessions_row else 0),
                ("Истекли", int(sessions_row["expired"]) if sessions_row else 0),
                ("Завершены", int(sessions_row["revoked"]) if sessions_row else 0),
            ]
        ),
        "device_donut": _donut(sorted(devices.items(), key=lambda item: (-item[1], item[0]))),
        "session_user_donut": _donut([(str(row["username"]), int(row["total"])) for row in session_users]),
        "session_user_bars": _bars([(str(row["username"]), int(row["total"])) for row in session_users]),
    }


@router.post("/admin/overview/clear")
async def admin_clear_games(request: Request) -> Response:
    user = _admin(request)
    if isinstance(user, Response):
        return user
    form = await request.form()
    if form.get("confirm") != "yes":
        raise AppError(422, "confirm", "Подтвердите очистку партий.")
    async with request.app.state.pool.acquire() as conn, conn.transaction():
        await conn.execute("DELETE FROM games")
    return RedirectResponse("/admin/overview?cleared=1", status_code=303)


@router.get("/admin/overview")
async def admin_overview(request: Request) -> Response:
    user = _admin(request)
    if isinstance(user, Response):
        return user
    async with request.app.state.pool.acquire() as conn:
        people = await conn.fetch(
            """
            SELECT shown_name(u.full_name, u.username) AS username,
                   u.username AS login, u.avatar,
                   u.role, u.created_at, u.last_seen, u.last_ip, u.last_country,
                   u.last_user_agent, u.born_on,
                   shown_name(inv.full_name, inv.username) AS invited_by,
                   inv.username AS invited_login,
                   COALESCE(w.balance, 0) AS balance,
                   (SELECT count(*) FROM games AS g WHERE g.user_id = u.id OR g.opponent_id = u.id) AS games,
                   (SELECT count(*) FROM games AS g
                     WHERE (g.user_id = u.id OR g.opponent_id = u.id) AND g.status = 'finished') AS finished,
                   (SELECT count(*) FROM games AS g
                     WHERE g.result IS NOT NULL AND (
                        (g.user_id = u.id AND (
                            (g.player_side = 'white' AND g.result = 'white_win')
                            OR (g.player_side = 'black' AND g.result = 'black_win')
                        ))
                        OR (g.opponent_id = u.id AND (
                            (g.player_side = 'white' AND g.result = 'black_win')
                            OR (g.player_side = 'black' AND g.result = 'white_win')
                        ))
                     )) AS wins
            FROM users AS u
            LEFT JOIN wallets AS w ON w.user_id = u.id
            LEFT JOIN users AS inv ON inv.id = u.referred_by
            ORDER BY games DESC, u.created_at
            """
        )
        totals = await conn.fetchrow(
            """
            SELECT
                (SELECT count(*) FROM users) AS users,
                (SELECT count(*) FROM users WHERE last_seen > now() - interval '2 minutes') AS online,
                (SELECT count(*) FROM games) AS games,
                (SELECT count(*) FROM games WHERE status = 'active') AS active_games,
                (SELECT count(*) FROM games WHERE status = 'waiting') AS waiting_games,
                (SELECT count(*) FROM games WHERE status = 'finished') AS finished_games,
                (SELECT count(*) FROM messages) AS messages,
                (SELECT count(*) FROM messages WHERE game_id IS NULL) AS personal_messages,
                (SELECT count(*) FROM messages WHERE game_id IS NOT NULL) AS table_messages,
                (SELECT count(*) FROM game_moves) AS moves,
                (SELECT count(*) FROM watchers) AS watchers,
                (SELECT count(*) FROM games WHERE audience = 'open') AS open_games,
                (SELECT count(*) FROM games WHERE audience = 'closed') AS closed_games,
                (SELECT COALESCE(sum(balance), 0) FROM wallets) AS chips
            """
        )
        by_type = await conn.fetch(
            """
            SELECT g.game_type,
                   count(*) AS total,
                   count(*) FILTER (WHERE g.status = 'finished') AS finished,
                   count(*) FILTER (WHERE g.status = 'active') AS active,
                   count(*) FILTER (WHERE g.status = 'waiting') AS waiting,
                   count(*) FILTER (WHERE g.result = 'white_win') AS white_wins,
                   count(*) FILTER (WHERE g.result = 'black_win') AS black_wins,
                   count(*) FILTER (WHERE g.result = 'draw') AS draws,
                   count(*) FILTER (WHERE g.mode = 'vs_computer') AS vs_computer,
                   count(*) FILTER (WHERE g.mode = 'online') AS online,
                   count(*) FILTER (WHERE g.mode = 'free') AS free_play,
                   count(*) FILTER (WHERE g.mode = 'analysis') AS analysis,
                   count(*) FILTER (WHERE g.mode = 'lesson') AS lesson,
                   count(*) FILTER (WHERE g.mode = 'online' AND g.audience = 'open') AS open_tables,
                   count(*) FILTER (WHERE g.mode = 'vs_computer' AND (
                        (g.player_side = 'white' AND g.result = 'white_win')
                        OR (g.player_side = 'black' AND g.result = 'black_win')
                   )) AS human_wins,
                   count(*) FILTER (WHERE g.mode = 'vs_computer' AND (
                        (g.player_side = 'white' AND g.result = 'black_win')
                        OR (g.player_side = 'black' AND g.result = 'white_win')
                   )) AS engine_wins,
                   count(*) FILTER (WHERE g.mode = 'vs_computer' AND g.result = 'draw') AS engine_draws,
                   COALESCE(round(avg(m.moves) FILTER (WHERE g.status = 'finished')), 0) AS avg_moves,
                   COALESCE(max(m.moves), 0) AS longest
            FROM games AS g
            LEFT JOIN (
                SELECT game_id, count(*) AS moves FROM game_moves GROUP BY game_id
            ) AS m ON m.game_id = g.id
            GROUP BY g.game_type
            """
        )
        reasons = await conn.fetch(
            """
            SELECT game_type, COALESCE(result_reason, 'other') AS reason, count(*) AS total
            FROM games
            WHERE status = 'finished'
            GROUP BY game_type, reason
            ORDER BY total DESC, reason
            """
        )
        zone = current_zone().key
        days = await conn.fetch(
            """
            SELECT (created_at AT TIME ZONE $1)::date AS day, count(*) AS total
            FROM games
            WHERE (created_at AT TIME ZONE $1)::date
                  >= ((now() AT TIME ZONE $1)::date - 13)
            GROUP BY 1
            ORDER BY 1
            """,
            zone,
        )
        move_days = await conn.fetch(
            """
            SELECT (created_at AT TIME ZONE $1)::date AS day, count(*) AS total
            FROM game_moves
            WHERE (created_at AT TIME ZONE $1)::date
                  >= ((now() AT TIME ZONE $1)::date - 13)
            GROUP BY 1
            ORDER BY 1
            """,
            zone,
        )
        login_days = await conn.fetch(
            """
            SELECT (created_at AT TIME ZONE $1)::date AS day, count(*) AS total
            FROM sessions
            WHERE (created_at AT TIME ZONE $1)::date
                  >= ((now() AT TIME ZONE $1)::date - 13)
            GROUP BY 1
            ORDER BY 1
            """,
            zone,
        )
        session_totals = await conn.fetchrow(
            """
            SELECT
                count(*) FILTER (WHERE revoked_at IS NULL AND expires_at > now()) AS live,
                count(*) FILTER (WHERE revoked_at IS NOT NULL) AS revoked,
                count(*) FILTER (WHERE revoked_at IS NULL AND expires_at <= now()) AS expired
            FROM sessions
            """
        )
        session_users = await conn.fetch(
            """
            SELECT shown_name(u.full_name, u.username) AS username, count(*) AS total
            FROM sessions AS s
            JOIN users AS u ON u.id = s.user_id
            GROUP BY 1
            ORDER BY total DESC, username
            """
        )
        session_devices = await conn.fetch(
            """
            SELECT user_agent, count(*) AS total
            FROM sessions
            GROUP BY user_agent
            """
        )
        levels = await conn.fetch(
            """
            SELECT engine_level, count(*) AS total
            FROM games
            WHERE mode = 'vs_computer'
            GROUP BY engine_level
            ORDER BY engine_level
            """
        )
        games_total = int(await conn.fetchval("SELECT count(*) FROM games") or 0)
        games_pages = page_count(games_total, _OVERVIEW_GAMES)
        games_page = clamp_page(read_page(request.query_params.get("games_page")), games_pages)
        recent_games = await conn.fetch(
            """
            SELECT g.id, g.game_type, g.mode, g.status, g.result, g.result_reason, g.audience, g.updated_at,
                   g.player_side,
                   shown_name(cu.full_name, cu.username) AS creator_name,
                   shown_name(ou.full_name, ou.username) AS opponent_name,
                   cu.username AS creator_login, ou.username AS opponent_login,
                   (
                       SELECT string_agg(s.seat_key, ',' ORDER BY s.seat_key)
                       FROM game_seats AS s
                       WHERE s.game_id = g.id AND s.kind = 'computer'
                   ) AS cpu_seats,
                   (
                       SELECT string_agg(shown_name(hu.full_name, hu.username), E'\x1f')
                       FROM game_seats AS s
                       JOIN users AS hu ON hu.id = s.user_id
                       WHERE s.game_id = g.id AND s.kind = 'human'
                   ) AS human_names
            FROM games AS g
            JOIN users AS cu ON cu.id = g.user_id
            LEFT JOIN users AS ou ON ou.id = g.opponent_id
            ORDER BY g.updated_at DESC
            LIMIT $1 OFFSET $2
            """,
            _OVERVIEW_GAMES,
            (games_page - 1) * _OVERVIEW_GAMES,
        )
        invites = await conn.fetch(
            """
            SELECT shown_name(inv.full_name, inv.username) AS username, count(*) AS total
            FROM users AS child
            JOIN users AS inv ON inv.id = child.referred_by
            GROUP BY 1
            ORDER BY total DESC, username
            """
        )
        sessions_total = int(await conn.fetchval("SELECT count(*) FROM sessions") or 0)
        sessions_pages = page_count(sessions_total, _OVERVIEW_SESSIONS)
        sessions_page = clamp_page(read_page(request.query_params.get("sessions_page")), sessions_pages)
        recent_sessions = await conn.fetch(
            """
            SELECT shown_name(u.full_name, u.username) AS username,
                   u.username AS login,
                   s.ip_address, s.user_agent, s.created_at, s.expires_at, s.revoked_at
            FROM sessions AS s
            JOIN users AS u ON u.id = s.user_id
            ORDER BY s.created_at DESC
            LIMIT $1 OFFSET $2
            """,
            _OVERVIEW_SESSIONS,
            (sessions_page - 1) * _OVERVIEW_SESSIONS,
        )
    now = datetime.now(UTC)
    guests = []
    for row in people:
        item = dict(row)
        item["device"] = device_label(item.get("last_user_agent"))
        born = item.get("born_on")
        item["born_label"] = format_born(born) if isinstance(born, date) else ""
        guests.append(item)
    sessions = []
    for row in recent_sessions:
        item = dict(row)
        item["device"] = device_label(item.get("user_agent"))
        expires = _aware(item.get("expires_at"))
        item["live"] = item.get("revoked_at") is None and expires is not None and expires > now
        sessions.append(item)
    level_rows = {int(row["engine_level"]): int(row["total"]) for row in levels}
    level_peak = max(level_rows.values(), default=0)
    strength = [
        {
            "title": title,
            "total": level_rows.get(index, 0),
            "share": 0 if not level_peak else round(100 * level_rows.get(index, 0) / level_peak),
            "height": 0 if not level_rows.get(index, 0) else max(10, round(88 * level_rows.get(index, 0) / level_peak)),
        }
        for index, title in enumerate(_LEVELS, start=1)
    ]
    numbers = dict(totals) if totals else {}
    series, chart = _overview_days(list(days))
    move_series, move_chart = _overview_days(list(move_days))
    login_series, login_chart = _overview_days(list(login_days))
    game_cards = _overview_games(list(by_type), list(reasons))
    tallest = max((int(card["total"]) for card in game_cards), default=0)
    for card in game_cards:
        total = int(card["total"])
        card["bar"] = 0 if not total or not tallest else max(8, round(100 * total / tallest))
    charts = _overview_charts(numbers, game_cards, guests, strength, session_totals, session_users, session_devices)
    people_frame = window(guests, read_page(request.query_params.get("people_page")), _OVERVIEW_PEOPLE)
    pages = {
        "games_page": games_page,
        "people_page": int(people_frame["page"]),
        "sessions_page": sessions_page,
    }
    if any(
        request.query_params.get(key) not in (None, str(value))
        for key, value in pages.items()
    ):
        extra = "cleared=1" if request.query_params.get("cleared") == "1" else ""
        return RedirectResponse(_overview_target(pages, extra), status_code=303)
    cleared = request.query_params.get("cleared") == "1"
    return _page(
        request,
        "admin/overview.html",
        {
            "people": people_frame["items"],
            "totals": numbers,
            "games": game_cards,
            "days": series,
            "chart": chart,
            "day_total": sum(int(row["total"]) for row in days),
            "move_days": move_series,
            "move_chart": move_chart,
            "move_total": sum(int(row["total"]) for row in move_days),
            "login_days": login_series,
            "login_chart": login_chart,
            "login_total": sum(int(row["total"]) for row in login_days),
            "strength": strength,
            "recent_games": [
                {
                    **dict(row),
                    "cpu_label": ", ".join(
                        computer_names(
                            row["id"],
                            row["player_side"],
                            row["cpu_seats"],
                            [row["creator_name"], row["opponent_name"], row["human_names"]],
                        )
                    )
                    if row["mode"] == "vs_computer"
                    else "",
                }
                for row in recent_games
            ],
            "recent_total": games_total,
            "recent_sessions": sessions,
            "games_page": games_page,
            "games_pages": games_pages,
            "games_links": page_links(games_page, games_pages),
            "games_href": _overview_href(pages, "games_page", "#summary"),
            "people_page": pages["people_page"],
            "people_pages": people_frame["pages"],
            "people_links": people_frame["links"],
            "people_href": _overview_href(pages, "people_page", "#people"),
            "sessions_page": sessions_page,
            "sessions_pages": sessions_pages,
            "sessions_links": page_links(sessions_page, sessions_pages),
            "sessions_href": _overview_href(pages, "sessions_page", "#sessions"),
            "referral_bars": _bars([(str(row["username"]), int(row["total"])) for row in invites]),
            "cleared": cleared,
            **charts,
        },
    )


def _overview_target(pages: dict[str, int], extra: str = "") -> str:
    parts = [extra] if extra else []
    for key, value in pages.items():
        if value > 1:
            parts.append(f"{key}={value}")
    return "/admin/overview" + (f"?{'&'.join(parts)}" if parts else "")


def _overview_href(pages: dict[str, int], key: str, anchor: str) -> str:
    parts = []
    for name, value in pages.items():
        if name == key:
            parts.append(f"{name}=__PAGE__")
        elif value > 1:
            parts.append(f"{name}={value}")
    query = "&".join(parts)
    return "/admin/overview" + (f"?{query}" if query else "") + anchor


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _game_title(game_type: str) -> str:
    spec = GAMES.get(game_type)
    return spec.title if spec is not None else game_type


def _presence(seen: datetime | None, now: datetime, activity: dict[str, str] | None) -> tuple[str, bool]:
    if activity is not None:
        kind = activity["kind"]
        if kind == "playing":
            return f"Играет в {activity['title']}", True
        if kind == "waiting":
            return "Ждёт соперника", True
        if kind == "seeking":
            return "Ищет стол", True
    stamp = _aware(seen)
    if stamp is not None and now - stamp <= ONLINE_FOR:
        return "В сети", True
    if stamp is None:
        return "Давно не заходил", False
    local = stamp.astimezone(current_zone())
    today = now.astimezone(current_zone()).date()
    if local.date() == today:
        return f"Был сегодня в {local:%H:%M}", False
    if local.date() == today - timedelta(days=1):
        return "Был вчера", False
    return f"Был {local.day} {_MONTHS[local.month - 1]}", False


def _short_when(stamp: datetime, now: datetime) -> str:
    local = _aware(stamp).astimezone(current_zone())
    today = now.astimezone(current_zone()).date()
    if local.date() == today:
        return f"{local:%H:%M}"
    if local.date() == today - timedelta(days=1):
        return "Вчера"
    return f"{local.day} {_MONTHS[local.month - 1]}"


def _online_phrase(count: int) -> str:
    mod10 = count % 10
    mod100 = count % 100
    if mod10 == 1 and mod100 != 11:
        word = "друг уже в сети"
    elif mod10 in (2, 3, 4) and mod100 not in (12, 13, 14):
        word = "друга уже в сети"
    else:
        word = "друзей уже в сети"
    return f"{count} {word}"


def _named(row: asyncpg.Record) -> dict[str, object]:
    data = dict(row)
    data["name"] = shown(data.get("full_name"), data.get("username"))
    return data


def _invite_parts(body: object, offer: tuple[str, str] | None = None) -> tuple[str, str]:
    text = " ".join(str(body or "").split())
    found = _INVITE.search(text)
    if found:
        return (found.group("title") or "", found.group("code"))
    if offer and text.casefold() in _TABLE_READY:
        return offer
    return ("", "")


def _inbox_preview(body: object) -> str:
    title, code = _invite_parts(body)
    if code:
        label = f"{title} · " if title else ""
        return f"Приглашение в партию · {label}{code}"
    return " ".join(str(body or "").split())


def _decorate(
    messages: list[asyncpg.Record],
    mine: str,
    now: datetime,
    offers: dict[uuid.UUID, tuple[str, str]] | None = None,
) -> list[dict[str, object]]:
    titles = {spec.title.casefold(): spec.key for spec in GAMES.values()}
    prepared: list[dict[str, object]] = []
    last_day = None
    waiting = offers or {}
    for row in messages:
        local = _aware(row["created_at"]).astimezone(current_zone())
        sender = row["sender_id"] if "sender_id" in row.keys() else None
        title, code = _invite_parts(row["body"], waiting.get(sender))
        prepared.append(
            {
                "body": row["body"],
                "username": row["username"],
                "name": shown(row["full_name"], row["username"]),
                "mine": row["username"] == mine,
                "clock": f"{local:%H:%M}",
                "show_day": local.date() != last_day,
                "day_label": (
                    "Сегодня"
                    if local.date() == now.astimezone(current_zone()).date()
                    else _short_when(row["created_at"], now)
                ),
                "code": code,
                "game_title": title,
                "game_key": titles.get(title.casefold(), ""),
            }
        )
        last_day = local.date()
    return prepared


async def _waiting_invites(conn: asyncpg.Connection, ids: list[uuid.UUID]) -> dict[uuid.UUID, tuple[str, str]]:
    if not ids:
        return {}
    rows = await conn.fetch(
        """
        SELECT DISTINCT ON (user_id) user_id, game_type, join_code
        FROM games
        WHERE user_id = ANY($1::uuid[])
          AND mode = 'online'
          AND status = 'waiting'
          AND join_code IS NOT NULL
        ORDER BY user_id, created_at DESC
        """,
        ids,
    )
    found: dict[uuid.UUID, tuple[str, str]] = {}
    for row in rows:
        spec = GAMES.get(str(row["game_type"]))
        if spec is None or not row["join_code"]:
            continue
        found[row["user_id"]] = (spec.title, str(row["join_code"]))
    return found


async def _activity(conn: asyncpg.Connection, ids: list[uuid.UUID]) -> dict[uuid.UUID, dict[str, str]]:
    if not ids:
        return {}
    games = await conn.fetch(
        """
        SELECT user_id, opponent_id, game_type, mode, status
        FROM games
        WHERE status IN ('waiting', 'active')
          AND mode IN ('online', 'vs_computer')
          AND (user_id = ANY($1::uuid[]) OR opponent_id = ANY($1::uuid[]))
        ORDER BY updated_at DESC
        """,
        ids,
    )
    found: dict[uuid.UUID, dict[str, str]] = {}
    wanted = set(ids)
    for row in games:
        kind = "playing" if row["status"] == "active" else "waiting"
        detail = "С компьютером" if row["mode"] == "vs_computer" else "С человеком"
        for seat in (row["user_id"], row["opponent_id"]):
            if seat not in wanted:
                continue
            current = found.get(seat)
            if current is not None and (current["kind"] == "playing" or kind == "waiting"):
                continue
            found[seat] = {
                "kind": kind,
                "title": _game_title(row["game_type"]),
                "detail": detail,
                "game_key": row["game_type"],
            }
    seekers = await conn.fetch(
        """
        SELECT user_id, game_type
        FROM seekers
        WHERE user_id = ANY($1::uuid[]) AND created_at > now() - interval '15 minutes'
        """,
        ids,
    )
    for row in seekers:
        if row["user_id"] in found:
            continue
        found[row["user_id"]] = {
            "kind": "seeking",
            "title": _game_title(row["game_type"]),
            "detail": "",
            "game_key": row["game_type"],
        }
    return found


async def _friends_context(conn: asyncpg.Connection, user_id: uuid.UUID) -> dict[str, object]:
    rows = await conn.fetch(
        """
        SELECT f.id, f.status, f.requester_id, f.addressee_id, f.created_at,
               ru.username AS requester_name, ru.full_name AS requester_full,
               ru.avatar AS requester_avatar, ru.last_seen AS requester_seen,
               au.username AS addressee_name, au.full_name AS addressee_full,
               au.avatar AS addressee_avatar, au.last_seen AS addressee_seen
        FROM friendships AS f
        JOIN users AS ru ON ru.id = f.requester_id
        JOIN users AS au ON au.id = f.addressee_id
        WHERE f.requester_id = $1 OR f.addressee_id = $1
        ORDER BY f.created_at DESC
        """,
        user_id,
    )
    now = datetime.now(UTC)
    people: list[dict[str, object]] = []
    ids: list[uuid.UUID] = []
    for row in rows:
        incoming = row["addressee_id"] == user_id
        other_id = row["requester_id"] if incoming else row["addressee_id"]
        if row["status"] == "accepted":
            relation = "accepted"
        elif incoming:
            relation = "incoming"
        else:
            relation = "outgoing"
        login = row["requester_name"] if incoming else row["addressee_name"]
        full = row["requester_full"] if incoming else row["addressee_full"]
        people.append(
            {
                "id": row["id"],
                "other_id": other_id,
                "username": login,
                "name": shown(full, login),
                "avatar": row["requester_avatar"] if incoming else row["addressee_avatar"],
                "seen": row["requester_seen"] if incoming else row["addressee_seen"],
                "relation": relation,
                "asked": _short_when(row["created_at"], now),
            }
        )
        ids.append(other_id)
    activity = await _activity(conn, ids)
    friends: list[dict[str, object]] = []
    for person in people:
        act = activity.get(person["other_id"])
        label, live = _presence(person["seen"], now, act)
        if person["relation"] == "outgoing":
            label, live = "Запрос отправлен", False
        person["label"] = label
        person["live"] = live
        person["game"] = act["title"] if act and person["relation"] == "accepted" else ""
        person["detail"] = act["detail"] if act and person["relation"] == "accepted" else ""
        friends.append(person)
    incoming = [item for item in friends if item["relation"] == "incoming"]
    online = sum(1 for item in friends if item["relation"] == "accepted" and item["live"])
    return {
        "friends": friends,
        "incoming": incoming,
        "counts": {
            "all": sum(1 for item in friends if item["relation"] != "incoming"),
            "online": online,
            "requests": len(incoming),
        },
        "online_phrase": _online_phrase(online),
    }


async def _chats_context(
    conn: asyncpg.Connection,
    user: User,
    other: asyncpg.Record | None = None,
    messages: list[asyncpg.Record] | None = None,
) -> dict[str, object]:
    rows = await conn.fetch(
        """
        SELECT DISTINCT ON (pairs.other_id)
            pairs.other_id, users.username, users.full_name, users.avatar, users.last_seen,
            pairs.body, pairs.created_at, COALESCE(unread.n, 0) AS unread
        FROM (
            SELECT
                CASE WHEN sender_id = $1 THEN recipient_id ELSE sender_id END AS other_id,
                body,
                created_at
            FROM messages
            WHERE game_id IS NULL AND (recipient_id = $1 OR sender_id = $1)
        ) AS pairs
        JOIN users ON users.id = pairs.other_id
        LEFT JOIN (
            SELECT m.sender_id AS other_id, count(*) AS n
            FROM messages AS m
            LEFT JOIN chat_reads AS r
              ON r.user_id = $1 AND r.peer_id = m.sender_id
            WHERE m.recipient_id = $1
              AND m.game_id IS NULL
              AND m.created_at > COALESCE(r.read_at, '-infinity'::timestamptz)
            GROUP BY m.sender_id
        ) AS unread ON unread.other_id = pairs.other_id
        WHERE pairs.other_id IS NOT NULL
        ORDER BY pairs.other_id, pairs.created_at DESC
        """,
        user.id,
    )
    now = datetime.now(UTC)
    inbox = [
        {
            "username": row["username"],
            "name": shown(row["full_name"], row["username"]),
            "avatar": row["avatar"] or "",
            "body": _inbox_preview(row["body"]),
            "created_at": row["created_at"],
            "when": _short_when(row["created_at"], now),
            "live": _presence(row["last_seen"], now, None)[1],
            "unread": int(row["unread"]),
        }
        for row in rows
    ]
    inbox.sort(key=lambda item: item["created_at"], reverse=True)
    thread = None
    if other is not None:
        activity = await _activity(conn, [other["id"]])
        label, live = _presence(other["last_seen"], now, activity.get(other["id"]))
        friend = await conn.fetchrow(
            """
            SELECT id FROM friendships
            WHERE status = 'accepted'
              AND (
                    (requester_id = $1 AND addressee_id = $2)
                 OR (requester_id = $2 AND addressee_id = $1)
              )
            """,
            user.id,
            other["id"],
        )
        thread = {
            "username": other["username"],
            "name": shown(other["full_name"], other["username"]),
            "avatar": other["avatar"] or "",
            "live": live,
            "label": label,
            "friendship_id": friend["id"] if friend else None,
            "messages": _decorate(
                messages or [],
                user.username,
                now,
                await _waiting_invites(conn, [row["sender_id"] for row in (messages or [])]),
            ),
        }
    return {"inbox": inbox, "thread": thread, "games": visible_games(await is_adult(conn, user.id))}


async def _thread(conn: asyncpg.Connection, left: uuid.UUID, right: uuid.UUID) -> list[asyncpg.Record]:
    return await conn.fetch(
        """
        SELECT m.sender_id, m.body, m.created_at, u.username, u.full_name
        FROM messages AS m
        JOIN users AS u ON u.id = m.sender_id
        WHERE m.game_id IS NULL
          AND ((m.sender_id = $1 AND m.recipient_id = $2) OR (m.sender_id = $2 AND m.recipient_id = $1))
        ORDER BY m.created_at
        LIMIT 200
        """,
        left,
        right,
    )
