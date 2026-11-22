"""JSON API для мобильного приложения. Сайт по-прежнему ходит в свои страницы."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Request
from starlette.responses import JSONResponse

from app.api.dump import dump
from app.auth.attempts import authenticate
from app.auth.captcha import issue as issue_captcha
from app.auth.routes import _create_account, _require_human, _signup_code
from app.auth.validation import normalize_username, password_requirements, validate_password
from app.avatars import remove_avatar, store_avatar
from app.cards.registry import ADULT_GAMES
from app.catalog import GAMES
from app.db.repositories import api_access, news, users
from app.db.repositories import games as games_repo
from app.db.repositories import sessions as session_repo
from app.db.repositories.users import User
from app.errors import AppError
from app.games.schemas import (
    AccountBody,
    ApiLoginBody,
    AuthCodeBody,
    ChallengeBody,
    ChipGrantBody,
    MessageBody,
    PasswordBody,
    RefreshBody,
    RegisterBody,
    SeekBody,
    SettingsBody,
    UsernameBody,
)
from app.games.service import _summarize
from app.greeting import greeting
from app.names import parse_full_name, shown, split_full_name
from app.paging import clamp_page, page_count, read_page
from app.profile_stats import tally
from app.site_policy import current, referral_is_live
from app.social.notices import mark_chat_read
from app.social.routes import _activity, _chats_context, _friends_context, _pace, _presence, _seek_seats, _thread
from app.wallet import adult_denial, balance, born_from_parts, credit, is_adult
from app.web.routes import (
    _CHIP_PAGE,
    _LOGIN,
    _NEWS_PAGE,
    _birth,
    _chip_events,
    _friend_state,
    _grant_amount,
    _prefs,
    _referral_link,
    _store_settings,
    _stored_born,
    live_tables,
)

router = APIRouter(prefix="/api/v1")


def _json(payload: object, status: int = 200) -> JSONResponse:
    return JSONResponse(dump(payload), status_code=status)


def _user(request: Request):
    user = request.state.user
    if user is None:
        raise AppError(401, "unauthorized", "Нужно войти в систему.")
    return user


def _pair_payload(issued, user, chips: int) -> dict[str, object]:
    return {
        "token_type": "Bearer",
        "access_token": issued.access_token,
        "expires_in": issued.access_seconds,
        "refresh_token": issued.refresh_token,
        "refresh_expires_in": issued.refresh_seconds,
        "user": _card(user, chips),
    }


def _card(user, chips: int | None) -> dict[str, object]:
    return {
        "id": str(user.id),
        "username": user.username,
        "name": user.display_name,
        "full_name": user.full_name,
        "role": user.role,
        "avatar": user.avatar,
        "ask_name": bool(user.ask_name and not user.full_name),
        "chips": chips,
    }


async def _catalog(request: Request, user) -> list[dict[str, object]]:
    policy = await current(request)
    async with request.app.state.pool.acquire() as conn:
        adult = await is_adult(conn, user.id)
    items = []
    for spec in GAMES.values():
        if spec.adult and not adult:
            continue
        items.append(
            {
                "key": spec.key,
                "title": spec.title,
                "family": spec.family,
                "adult": spec.adult,
                "blurb": spec.blurb,
                "open": policy.allows(spec.key),
            }
        )
    return items


async def _issue_for(request: Request, user_id, client_id: str):
    policy = await current(request)
    async with request.app.state.pool.acquire() as conn:
        issued = await api_access.issue_pair(
            conn,
            user_id=user_id,
            client_id=client_id,
            refresh_seconds=policy.session_ttl_seconds,
            user_agent=request.headers.get("user-agent"),
            ip_address=request.state.client_ip,
        )
        user = await api_access.load_user(conn, user_id)
        chips = await balance(conn, user_id) if user is not None else 0
    if user is None:
        raise AppError(401, "unauthorized", "Нужно войти в систему.")
    return _pair_payload(issued, user, int(chips))


async def _first_party(request: Request, client_id: str):
    async with request.app.state.pool.acquire() as conn:
        client = await api_access.get_client(conn, client_id.strip().lower())
    if client is None or not client.is_active:
        raise AppError(401, "invalid_client", "Приложение не зарегистрировано.")
    if not client.first_party:
        raise AppError(403, "forbidden", "Это приложение входит через подтверждение на сайте.")
    return client


def _register_rules(policy, *, open_now: bool) -> dict[str, object]:
    return {
        "mode": policy.registration_mode,
        "open": open_now,
        "referral_required": policy.registration_mode == "referral",
        "username_min": policy.username_min,
        "username_max": policy.username_max,
        "password_min": policy.password_min,
        "password_letter": policy.password_needs_letter,
        "password_digit": policy.password_needs_digit,
        "password_rules": password_requirements(
            minimum=policy.password_min,
            letter=policy.password_needs_letter,
            digit=policy.password_needs_digit,
        ),
        "client_ids": ["parlor-ios", "parlor-android"],
    }


@router.get("/auth/register")
async def api_register_status(request: Request, ref: str = "") -> JSONResponse:
    policy = await current(request)
    code = ref.strip().lower() or str(request.query_params.get("ref") or "")
    if policy.registration_mode == "open":
        open_now = True
    elif policy.registration_mode == "referral":
        open_now = await referral_is_live(request, code)
    else:
        open_now = False
    return _json(_register_rules(policy, open_now=open_now))


@router.get("/auth/captcha")
async def api_captcha(request: Request, ref: str = "") -> JSONResponse:
    policy = await current(request)
    await _signup_code(request, policy, ref)
    if not await request.app.state.gate.allow(f"captcha:{request.state.client_ip}", 30, 60):
        raise AppError(429, "rate_limited", "Слишком много проверок. Подождите минуту.")
    return JSONResponse(issue_captcha(request.app.state.settings.secret_key))


@router.post("/auth/register", status_code=201)
async def api_register(request: Request, body: RegisterBody) -> JSONResponse:
    client = await _first_party(request, body.client_id)
    policy = await current(request)
    code = await _signup_code(request, policy, body.referral)
    await _require_human(request, body.captcha)
    try:
        born = born_from_parts(body.born_day, body.born_month, body.born_year)
    except ValueError as exc:
        raise AppError(422, "bad_date", str(exc)) from exc
    if born is None:
        raise AppError(422, "bad_date", "Укажите дату рождения.")
    await _create_account(
        request,
        username=body.username,
        password=body.password,
        role="user",
        referral=True,
        born_on=born,
        ask_name=True,
        referral_code=code,
    )
    record_name = normalize_username(body.username)
    async with request.app.state.pool.acquire() as conn:
        created = await users.get_auth_record(conn, record_name)
    if created is None:
        raise AppError(500, "internal", "Учётную запись не удалось открыть.")
    return _json(await _issue_for(request, created.id, client.id), status=201)


@router.post("/auth/login")
async def api_login(request: Request, body: ApiLoginBody) -> JSONResponse:
    client = await _first_party(request, body.client_id)
    record = await authenticate(request, normalize_username(body.username), body.password)
    return _json(await _issue_for(request, record.id, client.id))


@router.post("/auth/refresh")
async def api_refresh(request: Request, body: RefreshBody) -> JSONResponse:
    policy = await current(request)
    async with request.app.state.pool.acquire() as conn:
        issued, _reused = await api_access.rotate(
            conn,
            body.refresh_token,
            refresh_seconds=policy.session_ttl_seconds,
            user_agent=request.headers.get("user-agent"),
            ip_address=request.state.client_ip,
        )
        user = None
        chips = 0
        if issued is not None:
            row = await conn.fetchrow(
                "SELECT user_id FROM api_tokens WHERE id = $1",
                issued.refresh_id,
            )
            if row is not None:
                user = await api_access.load_user(conn, row["user_id"])
                chips = int(await balance(conn, row["user_id"]))
    if issued is None or user is None:
        raise AppError(401, "unauthorized", "Сессия приложения закончилась. Войдите снова.")
    return _json(_pair_payload(issued, user, chips))


@router.post("/auth/logout")
async def api_logout(request: Request, body: RefreshBody) -> JSONResponse:
    async with request.app.state.pool.acquire() as conn:
        await api_access.revoke_refresh(conn, body.refresh_token)
    return _json({"logged_out": True})


@router.post("/auth/token")
async def api_token(request: Request, body: AuthCodeBody) -> JSONResponse:
    if not await request.app.state.gate.allow(f"oauth:{request.state.client_ip}", 20, 60):
        raise AppError(429, "rate_limited", "Слишком много попыток. Подождите минуту.")
    policy = await current(request)
    async with request.app.state.pool.acquire() as conn:
        user_id = await api_access.take_code(
            conn,
            raw_code=body.code,
            client_id=body.client_id.strip().lower(),
            client_secret=body.client_secret,
            redirect_uri=body.redirect_uri,
        )
        if user_id is None:
            raise AppError(401, "invalid_grant", "Код входа недействителен.")
        issued = await api_access.issue_pair(
            conn,
            user_id=user_id,
            client_id=body.client_id.strip().lower(),
            refresh_seconds=policy.session_ttl_seconds,
            user_agent=request.headers.get("user-agent"),
            ip_address=request.state.client_ip,
        )
        user = await api_access.load_user(conn, user_id)
        chips = int(await balance(conn, user_id)) if user is not None else 0
    if user is None:
        raise AppError(401, "invalid_grant", "Код входа недействителен.")
    return _json(_pair_payload(issued, user, chips))


@router.get("/auth/me")
async def api_me(request: Request) -> JSONResponse:
    user = _user(request)
    return _json({"user": _card(user, request.state.chips), "client_id": getattr(request.state, "api_client", None)})


@router.get("/catalog")
async def api_catalog(request: Request) -> JSONResponse:
    user = _user(request)
    return _json({"games": await _catalog(request, user)})


@router.get("/home")
async def api_home(request: Request) -> JSONResponse:
    user = _user(request)
    data = await request.app.state.service.dashboard(user, page=read_page(request.query_params.get("page")))
    return _json(
        {
            "greeting": greeting(user.display_name),
            "chips": request.state.chips,
            "continue_id": None if data["continue_id"] is None else str(data["continue_id"]),
            "continue_game": data["continue_game"],
            "recent": data["recent"],
            "page": data["page"],
            "pages": data["pages"],
            "total": data["total"],
        }
    )


async def _loaded(request: Request):
    user = _user(request)
    async with request.app.state.pool.acquire() as conn:
        loaded = await api_access.load_user(conn, user.id)
    if loaded is None:
        raise AppError(401, "unauthorized", "Нужно войти в систему.")
    return loaded


@router.get("/account")
async def api_account(request: Request) -> JSONResponse:
    user = await _loaded(request)
    family, given, patronymic = split_full_name(user.full_name)
    prefs = await _prefs(request, user.id)
    birth = await _birth(request, user.id)
    return _json(
        {
            "user": _card(user, request.state.chips),
            "family": family,
            "given": given,
            "patronymic": patronymic,
            "birth": birth,
            "settings": prefs,
            "referral_link": await _referral_link(request, user.id),
        }
    )


@router.patch("/account")
async def api_account_save(request: Request, body: AccountBody) -> JSONResponse:
    user = _user(request)
    if body.family is not None or body.given is not None or body.patronymic is not None:
        full_name = parse_full_name(body.family or "", body.given or "", body.patronymic or "")
        async with request.app.state.pool.acquire() as conn:
            await users.set_full_name(conn, user.id, full_name)
    if body.born_day is not None or body.born_month is not None or body.born_year is not None:
        try:
            posted = born_from_parts(body.born_day or "", body.born_month or "", body.born_year or "")
        except ValueError as exc:
            raise AppError(422, "bad_date", str(exc)) from exc
        stored = await _stored_born(request, user.id)
        if posted is not None and posted != stored and not body.confirm:
            raise AppError(422, "bad_date", "Подтвердите, что дата указана верно.")
        if posted is not None and posted != stored:
            if not user.is_admin:
                raise AppError(403, "forbidden", "Дату рождения меняет администратор.")
            async with request.app.state.pool.acquire() as conn:
                await conn.execute(
                    "UPDATE users SET born_on = $2, updated_at = now() WHERE id = $1",
                    user.id,
                    posted,
                )
    return await api_account(request)


@router.put("/account/settings")
async def api_settings(request: Request, body: SettingsBody) -> JSONResponse:
    user = _user(request)
    await _store_settings(request, user.id, body)
    return _json({"saved": True, "settings": await _prefs(request, user.id)})


@router.post("/account/password")
async def api_password(request: Request, body: PasswordBody) -> JSONResponse:
    user = _user(request)
    if body.new_password != body.repeat_password:
        raise AppError(422, "bad_password", "Новые пароли не совпадают.")
    policy = await current(request)
    password_error = validate_password(
        body.new_password,
        minimum=policy.password_min,
        letter=policy.password_needs_letter,
        digit=policy.password_needs_digit,
    )
    if password_error:
        raise AppError(422, "bad_password", password_error)
    async with request.app.state.pool.acquire() as conn:
        record = await users.get_auth_record(conn, user.username)
    digest = record.password_hash if record and record.is_active else None
    if not await request.app.state.passwords.verify_async(digest, body.current_password):
        raise AppError(401, "unauthorized", "Старый пароль указан неверно.")
    if body.current_password == body.new_password:
        raise AppError(422, "bad_password", "Новый пароль совпадает со старым.")
    password_hash = request.app.state.passwords.hash_password(body.new_password)
    keep = getattr(request.state, "api_family", None) if getattr(request.state, "bearer", False) else None
    async with request.app.state.pool.acquire() as conn:
        async with conn.transaction():
            await users.set_password_hash(conn, user.id, password_hash)
            if getattr(request.state, "bearer", False):
                await session_repo.revoke_user_sessions(conn, user.id)
            else:
                token_hash = getattr(request.state, "session_hash", None)
                if token_hash:
                    await session_repo.revoke_other_user_sessions(conn, user.id, token_hash)
            await api_access.revoke_user(conn, user.id, keep_family=keep)
    return _json({"saved": True})


@router.post("/account/avatar")
async def api_avatar(request: Request) -> JSONResponse:
    user = _user(request)
    form = await request.form()
    upload = form.get("file")
    payload = await upload.read() if hasattr(upload, "read") else b""
    directory = Path(request.app.state.settings.avatar_dir)
    try:
        name = store_avatar(directory, payload, limit=request.app.state.settings.avatar_bytes)
    except ValueError as exc:
        raise AppError(422, "bad_image", "Нужен JPEG, PNG или WebP не больше 10 МБ.") from exc
    async with request.app.state.pool.acquire() as conn:
        previous = await users.set_avatar(conn, user.id, name)
    if previous and previous != name:
        remove_avatar(directory, previous)
    return _json({"src": f"/avatars/{name}"})


@router.delete("/account/avatar")
async def api_avatar_clear(request: Request) -> JSONResponse:
    user = _user(request)
    directory = Path(request.app.state.settings.avatar_dir)
    async with request.app.state.pool.acquire() as conn:
        previous = await users.set_avatar(conn, user.id, None)
    if previous:
        remove_avatar(directory, previous)
    return _json({"src": ""})


@router.get("/account/chips")
async def api_chips(request: Request) -> JSONResponse:
    user = _user(request)
    async with request.app.state.pool.acquire() as conn:
        events = await _chip_events(conn, user.id)
    pages = max(1, (len(events) + _CHIP_PAGE - 1) // _CHIP_PAGE)
    current_page = min(read_page(request.query_params.get("page")), pages)
    start = (current_page - 1) * _CHIP_PAGE
    window = events[start : start + _CHIP_PAGE]
    return _json(
        {
            "chips": request.state.chips,
            "events": window,
            "page": current_page,
            "pages": pages,
            "total": len(events),
        }
    )


@router.get("/friends")
async def api_friends(request: Request) -> JSONResponse:
    user = _user(request)
    async with request.app.state.pool.acquire() as conn:
        context = await _friends_context(conn, user.id)
    context["games"] = await _catalog(request, user)
    return _json(context)


@router.post("/friends")
async def api_friend_request(request: Request, body: UsernameBody) -> JSONResponse:
    user = _user(request)
    await _pace(request, f"friend:{user.id}", 10)
    username = normalize_username(body.username)
    async with request.app.state.pool.acquire() as conn:
        other = await conn.fetchrow(
            "SELECT id FROM users WHERE username = $1 AND is_active = TRUE",
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
        friendship_id = uuid.uuid4()
        await conn.execute(
            """
            INSERT INTO friendships (id, requester_id, addressee_id, status)
            VALUES ($1, $2, $3, 'pending')
            """,
            friendship_id,
            user.id,
            other["id"],
        )
    return _json({"id": str(friendship_id), "username": username}, status=201)


@router.post("/friends/{friendship_id}/accept")
async def api_friend_accept(request: Request, friendship_id: uuid.UUID) -> JSONResponse:
    user = _user(request)
    async with request.app.state.pool.acquire() as conn:
        updated = await conn.execute(
            """
            UPDATE friendships SET status = 'accepted'
            WHERE id = $1 AND addressee_id = $2 AND status = 'pending'
            """,
            friendship_id,
            user.id,
        )
    if updated.endswith("0"):
        raise AppError(404, "not_found", "Запрос не найден.")
    return _json({"accepted": True})


@router.post("/friends/{friendship_id}/decline")
async def api_friend_decline(request: Request, friendship_id: uuid.UUID) -> JSONResponse:
    user = _user(request)
    async with request.app.state.pool.acquire() as conn:
        deleted = await conn.execute(
            """
            DELETE FROM friendships
            WHERE id = $1 AND (requester_id = $2 OR addressee_id = $2)
            """,
            friendship_id,
            user.id,
        )
    if deleted.endswith("0"):
        raise AppError(404, "not_found", "Запрос не найден.")
    return _json({"removed": True})


@router.post("/friends/{friendship_id}/challenge")
async def api_friend_challenge(request: Request, friendship_id: uuid.UUID, body: ChallengeBody) -> JSONResponse:
    user = _user(request)
    if body.game_type not in GAMES:
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
            "game_type": body.game_type,
            "mode": "online",
            "player_side": "white",
            "engine_level": 3,
            "engine_time_ms": 1000,
        },
    )
    code = state.get("join_code") or ""
    async with request.app.state.pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO messages (sender_id, recipient_id, body) VALUES ($1, $2, $3)",
            user.id,
            other_id,
            f"Зову за стол: {GAMES[body.game_type].title}. Код {code}. Откройте /join?code={code}",
        )
    return _json({"game_id": state["id"], "join_code": code})


@router.get("/lobby")
async def api_lobby(request: Request) -> JSONResponse:
    user = _user(request)
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
            SELECT username, full_name, avatar, last_seen
            FROM users
            WHERE is_active = TRUE AND id <> $1 AND last_seen > now() - interval '2 minutes'
            ORDER BY username
            """,
            user.id,
        )
        adult = await is_adult(conn, user.id)
        live_count = await conn.fetchval(
            """
            SELECT count(*) FROM games
            WHERE mode IN ('online', 'vs_computer') AND status IN ('waiting', 'active')
            """
        )
    now = datetime.now(UTC)
    people = []
    for row in seekers:
        if not adult and row["game_type"] in ADULT_GAMES:
            continue
        people.append(
            {
                "user_id": row["user_id"],
                "username": row["username"],
                "name": shown(row["full_name"], row["username"]),
                "avatar": row["avatar"] or "",
                "game_type": row["game_type"],
                "seats": row["seats"],
                "created_at": row["created_at"],
                "mine": row["user_id"] == user.id,
            }
        )
    guests = []
    for row in online:
        guests.append(
            {
                "username": row["username"],
                "name": shown(row["full_name"], row["username"]),
                "avatar": row["avatar"] or "",
                "live": _presence(row["last_seen"], now, None)[1],
            }
        )
    return _json(
        {
            "seekers": people,
            "online": guests,
            "live_count": int(live_count or 0),
            "games": await _catalog(request, user),
        }
    )


@router.post("/lobby/seek")
async def api_lobby_seek(request: Request, body: SeekBody) -> JSONResponse:
    user = _user(request)
    policy = await current(request)
    if body.game_type not in GAMES or not policy.allows(body.game_type):
        raise AppError(422, "bad_game", "Эта игра сейчас закрыта.")
    if body.game_type in ADULT_GAMES:
        async with request.app.state.pool.acquire() as conn:
            reason = await adult_denial(conn, user.id, body.game_type)
        if reason:
            raise AppError(403, "adult_only", reason)
    seats = _seek_seats(body.game_type, body.seats)
    async with request.app.state.pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO seekers (user_id, game_type, seats, created_at)
            VALUES ($1, $2, $3, now())
            ON CONFLICT (user_id) DO UPDATE
            SET game_type = EXCLUDED.game_type, seats = EXCLUDED.seats, created_at = now()
            """,
            user.id,
            body.game_type,
            seats,
        )
    return _json({"seeking": True, "game_type": body.game_type, "seats": seats})


@router.post("/lobby/cancel")
async def api_lobby_cancel(request: Request) -> JSONResponse:
    user = _user(request)
    async with request.app.state.pool.acquire() as conn:
        await conn.execute("DELETE FROM seekers WHERE user_id = $1", user.id)
    return _json({"seeking": False})


@router.post("/lobby/accept/{seeker_id}")
async def api_lobby_accept(request: Request, seeker_id: uuid.UUID) -> JSONResponse:
    user = _user(request)
    if seeker_id == user.id:
        raise AppError(422, "bad_game", "Свой вызов принять нельзя.")
    async with request.app.state.pool.acquire() as conn:
        seeker_row = await conn.fetchrow(
            """
            SELECT u.id, u.username, u.role, u.full_name, u.ask_name, u.avatar, s.game_type, s.seats
            FROM seekers AS s
            JOIN users AS u ON u.id = s.user_id
            WHERE s.user_id = $1
            """,
            seeker_id,
        )
    if seeker_row is None:
        raise AppError(404, "not_found", "Игрок уже сел за другой стол.")
    seeker = User(
        id=seeker_row["id"],
        username=seeker_row["username"],
        role=seeker_row["role"],
        full_name=str(seeker_row["full_name"] or ""),
        ask_name=bool(seeker_row["ask_name"]),
        avatar=str(seeker_row["avatar"] or ""),
    )
    game_type = str(seeker_row["game_type"])
    seats = _seek_seats(game_type, seeker_row["seats"])
    payload: dict[str, object] = {
        "game_type": game_type,
        "mode": "online",
        "player_side": "white",
        "engine_level": 3,
        "engine_time_ms": 1000,
    }
    if seats > 2:
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
    return _json({"game_id": str(game_id)})


@router.get("/chats")
async def api_chats(request: Request) -> JSONResponse:
    user = _user(request)
    async with request.app.state.pool.acquire() as conn:
        context = await _chats_context(conn, user)
    context.pop("games", None)
    return _json(context)


@router.get("/chats/{username}")
async def api_thread(request: Request, username: str) -> JSONResponse:
    user = _user(request)
    login = normalize_username(username)
    async with request.app.state.pool.acquire() as conn:
        other = await conn.fetchrow(
            "SELECT id, username, full_name, avatar, last_seen FROM users WHERE username = $1 AND is_active = TRUE",
            login,
        )
        if other is None or other["id"] == user.id:
            raise AppError(404, "not_found", "Такого игрока нет.")
        await mark_chat_read(conn, user.id, other["id"])
        messages = await _thread(conn, user.id, other["id"])
        context = await _chats_context(conn, user, other=other, messages=messages)
    context.pop("games", None)
    return _json(context)


@router.post("/chats/{username}")
async def api_thread_send(request: Request, username: str, body: MessageBody) -> JSONResponse:
    user = _user(request)
    text = " ".join(body.body.split())
    if not text or len(text) > 1000:
        raise AppError(422, "bad_message", "Сообщение должно быть от 1 до 1000 символов.")
    await _pace(request, f"chat:{user.id}", 30)
    login = normalize_username(username)
    async with request.app.state.pool.acquire() as conn:
        other = await conn.fetchrow(
            "SELECT id FROM users WHERE username = $1 AND is_active = TRUE",
            login,
        )
        if other is None or other["id"] == user.id:
            raise AppError(404, "not_found", "Такого игрока нет.")
        await conn.execute(
            "INSERT INTO messages (sender_id, recipient_id, body) VALUES ($1, $2, $3)",
            user.id,
            other["id"],
            text,
        )
    return await api_thread(request, login)


@router.get("/live")
async def api_live(request: Request) -> JSONResponse:
    user = _user(request)
    return _json(await live_tables(request, user))


@router.post("/live/{game_id}/watch")
async def api_live_watch(request: Request, game_id: uuid.UUID) -> JSONResponse:
    user = _user(request)
    watched = await request.app.state.service.watch_table(user, game_id)
    return _json({"game_id": str(watched)})


@router.post("/live/{game_id}/sit")
async def api_live_sit(request: Request, game_id: uuid.UUID) -> JSONResponse:
    user = _user(request)
    seated = await request.app.state.service.sit_open(user, game_id)
    return _json({"game_id": str(seated)})


@router.get("/news")
async def api_news(request: Request) -> JSONResponse:
    async with request.app.state.pool.acquire() as conn:
        total = await news.count_news(conn)
        pages = page_count(total, _NEWS_PAGE)
        current_page = clamp_page(read_page(request.query_params.get("page")), pages)
        posts = await news.list_news(conn, _NEWS_PAGE, (current_page - 1) * _NEWS_PAGE)
    return _json({"posts": posts, "page": current_page, "pages": pages, "total": total})


@router.get("/news/{news_id}")
async def api_news_item(request: Request, news_id: uuid.UUID) -> JSONResponse:
    async with request.app.state.pool.acquire() as conn:
        post = await news.get_news(conn, news_id)
    if post is None:
        raise AppError(404, "not_found", "Новость не найдена.")
    return _json({"post": post})


@router.get("/players/{username}")
async def api_player(request: Request, username: str) -> JSONResponse:
    user = _user(request)
    login = normalize_username(username)
    if not _LOGIN.fullmatch(login):
        raise AppError(404, "not_found", "Такого игрока нет.")
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
            raise AppError(404, "not_found", "Такого игрока нет.")
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
    activity = {}
    async with request.app.state.pool.acquire() as conn:
        activity = await _activity(conn, [row["id"]])
    label, live = _presence(moment, datetime.now(UTC), activity.get(row["id"]))
    return _json(
        {
            "username": row["username"],
            "name": shown(row["full_name"], row["username"]),
            "full_name": shown(row["full_name"], ""),
            "avatar": row["avatar"] or "",
            "created_at": row["created_at"],
            "online": online or live,
            "presence": label,
            "chips": int(purse),
            "friend_state": await _friend_state(request, user.id, row["id"]),
            "stats": tally([dict(item) for item in played], row["id"]),
            "breakdown": _summarize(counted, row["id"]),
        }
    )


@router.post("/players/{username}/chips")
async def api_player_chips(request: Request, username: str, body: ChipGrantBody) -> JSONResponse:
    user = _user(request)
    if not user.is_admin:
        raise AppError(404, "not_found", "Страница не найдена.")
    login = normalize_username(username)
    async with request.app.state.pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id FROM users WHERE username = $1 AND is_active = TRUE",
            login,
        )
        if row is None:
            raise AppError(404, "not_found", "Такого игрока нет.")
        purse = int(await balance(conn, row["id"]))
        amount, error = _grant_amount(str(body.amount), purse)
        if error or amount is None:
            raise AppError(422, "bad_amount", error or "Укажите, сколько фишек добавить.")
        await credit(conn, row["id"], amount, reason="admin", game_id=None)
        purse = int(await balance(conn, row["id"]))
    request.app.state.gate.chips.pop(str(row["id"]), None)
    return _json({"chips": purse})


@router.post("/players/{username}/friend")
async def api_player_friend(request: Request, username: str) -> JSONResponse:
    return await api_friend_request(request, UsernameBody(username=username))
