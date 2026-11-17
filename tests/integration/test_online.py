from __future__ import annotations

import asyncio
import base64
import json
import os
import re
import uuid
from datetime import date

import asyncpg
import pytest
from httpx import ASGITransport, AsyncClient

from app.auth.captcha import solve
from app.auth.passwords import Passwords
from app.config import get_settings
from app.db.migrate import apply_migrations
from app.db.repositories import games as games_repo
from app.db.repositories import users

pytestmark = pytest.mark.asyncio


async def _connect() -> asyncpg.Connection:
    try:
        return await asyncpg.connect(os.environ["DATABASE_URL"], timeout=3)
    except Exception as exc:
        pytest.skip(f"Тестовый PostgreSQL недоступен: {exc}")


@pytest.fixture
async def database():
    conn = await _connect()
    await apply_migrations(os.environ["DATABASE_URL"])
    await conn.execute(
        """
        TRUNCATE TABLE
            rematch_offers, game_seats, game_moves, games, analysis_cache, sessions,
            login_attempts, rate_events, user_settings, users, site_settings, news_posts
        RESTART IDENTITY CASCADE
        """
    )
    passwords = Passwords(get_settings())
    async with conn.transaction():
        admin = await users.create_user(
            conn,
            username="admin",
            password_hash=passwords.hash_password("admin-pass-1"),
            role="admin",
        )
        player = await users.create_user(
            conn,
            username="player",
            password_hash=passwords.hash_password("player-pass-1"),
            role="user",
        )
        await conn.execute(
            """
            UPDATE user_settings
            SET analysis_preferences = $2::jsonb
            WHERE user_id = $1
            """,
            admin.id,
            '{"checkers_level":1,"checkers_time_ms":250,"chess_depth":6,"chess_time_ms":200,"chess_multipv":1,"variety":false}',
        )
    yield {"conn": conn, "admin_id": admin.id, "player_id": player.id}
    await conn.close()


@pytest.fixture
async def clients(database):
    from app.main import app

    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as admin:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as player:
                yield admin, player, database


def _csrf_from(html: str) -> str:
    match = re.search(r'name="csrf-token" content="([^"]+)"', html)
    assert match is not None
    return match.group(1)


def _login_token(html: str) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', html)
    assert match is not None
    return match.group(1)


async def _captcha(client: AsyncClient, path: str = "/login/captcha") -> str:
    task = (await client.get(path)).json()
    number = solve(task)
    return base64.b64encode(
        json.dumps(
            {
                "algorithm": task["algorithm"],
                "challenge": task["challenge"],
                "number": number,
                "salt": task["salt"],
                "signature": task["signature"],
            }
        ).encode()
    ).decode()


async def _login(client: AsyncClient, username: str, password: str) -> str:
    page = await client.get("/login")
    assert page.status_code == 200
    assert "Я не робот" in page.text
    response = await client.post(
        "/login",
        data={
            "username": username,
            "password": password,
            "csrf_token": _login_token(page.text),
            "captcha": await _captcha(client),
        },
    )
    assert response.status_code == 303
    home = await client.get("/")
    if home.status_code == 303 and home.headers.get("location") == "/name":
        form = await client.get("/name")
        assert form.status_code == 200
        saved = await client.post(
            "/name",
            data={
                "family": "Иванов",
                "given": "Иван",
                "patronymic": "Иванович",
                "csrf_token": _login_token(form.text),
            },
        )
        assert saved.status_code == 303
        home = await client.get("/")
        assert "Иванов Иван Иванович" in home.text
    else:
        assert username in home.text
    assert home.status_code == 200
    return _csrf_from(home.text)


async def _signup_fields(client, page_text: str) -> dict[str, str]:
    payload = await _captcha(client, "/register/captcha")
    return {
        "born_day": "16",
        "born_month": "11",
        "born_year": "1990",
        "captcha": payload,
        "csrf_token": _login_token(page_text),
    }


async def test_login_rejects_injection_and_closed_registration(clients) -> None:
    admin, _player, _db = clients
    page = await admin.get("/login")
    bare = await admin.post(
        "/login",
        data={"username": "admin", "password": "admin-pass-1", "csrf_token": _login_token(page.text)},
    )
    assert bare.status_code == 422
    assert "не робот" in bare.text
    injected = await admin.post(
        "/login",
        data={
            "username": "' OR 1=1 --",
            "password": "anything1",
            "csrf_token": _login_token(bare.text),
            "captcha": await _captcha(admin),
        },
    )
    assert injected.status_code == 401
    assert "Неверный логин" in injected.text
    csrf = await _login(admin, "admin", "admin-pass-1")
    closed = await admin.post(
        "/register",
        headers={"Accept": "application/json"},
        data={"username": "newbie", "password": "newbie-pass-1", "csrf_token": csrf},
    )
    assert closed.status_code == 403
    assert closed.json()["error"]["code"] == "registration_disabled"


async def test_online_game_hides_hint_from_player(clients) -> None:
    admin, player, _db = clients
    admin_csrf = await _login(admin, "admin", "admin-pass-1")
    player_csrf = await _login(player, "player", "player-pass-1")
    denied = await player.post(
        "/api/v1/games",
        json={"game_type": "checkers", "mode": "online", "player_side": "white"},
    )
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "csrf"

    created = await player.post(
        "/api/v1/games",
        headers={"X-CSRF-Token": player_csrf},
        json={
            "game_type": "checkers",
            "mode": "online",
            "player_side": "white",
            "engine_level": 1,
            "engine_time_ms": 200,
            "initial_position": "w|18,32|22|0",
        },
    )
    assert created.status_code == 201
    state = created.json()
    game_id = state["id"]
    assert state["waiting"] is True
    assert state["can_hint"] is False
    assert state["can_engine"] is False
    code = state["join_code"]

    hidden = await admin.get(f"/api/v1/games/{game_id}")
    assert hidden.status_code == 404
    stranger_hint = await admin.post(
        f"/api/v1/games/{game_id}/hint",
        headers={"X-CSRF-Token": admin_csrf},
        json={"version": state["version"]},
    )
    assert stranger_hint.status_code == 404

    joined = await admin.post("/api/v1/games/join", headers={"X-CSRF-Token": admin_csrf}, json={"code": code})
    assert joined.status_code == 200
    assert joined.json()["your_side"] == "black"
    assert joined.json()["black_at_bottom"] is True
    assert joined.json()["can_hint"] is True
    assert joined.json()["legal_moves"] == []

    page = await player.get(f"/games/{game_id}")
    assert page.status_code == 200
    assert "Подсказка" not in page.text
    assert "Сделать ход компьютера" not in page.text
    admin_page = await admin.get(f"/games/{game_id}")
    assert "Подсказка" in admin_page.text
    assert "id=\"hint\"" in admin_page.text

    fresh = await player.get(f"/api/v1/games/{game_id}")
    version = fresh.json()["version"]
    quiet = await player.post(
        f"/api/v1/games/{game_id}/moves",
        headers={"X-CSRF-Token": player_csrf},
        json={"version": version, "path": ["32", "27"]},
    )
    assert quiet.status_code == 422
    assert quiet.json()["error"]["code"] == "illegal_move"
    still = await player.get(f"/api/v1/games/{game_id}")
    assert still.json()["version"] == version
    assert still.json()["moves"] == []

    player_hint = await player.post(
        f"/api/v1/games/{game_id}/hint",
        headers={"X-CSRF-Token": player_csrf},
        json={"version": version},
    )
    assert player_hint.status_code == 403
    assert player_hint.json()["error"]["code"] == "hint_forbidden"

    computer = await admin.post(
        f"/api/v1/games/{game_id}/engine-move",
        headers={"X-CSRF-Token": admin_csrf},
        json={"version": version},
    )
    assert computer.status_code == 409
    assert computer.json()["error"]["code"] == "engine_rejected"

    hint = await admin.post(
        f"/api/v1/games/{game_id}/hint",
        headers={"X-CSRF-Token": admin_csrf},
        json={"version": version},
    )
    assert hint.status_code == 200
    body = hint.json()
    assert body["private"] is True
    assert body["version"] == version
    path = body["lines"][0]["path"]
    legal = {tuple(item["path"]) for item in fresh.json()["legal_moves"]}
    assert tuple(path) in legal
    after_hint = await player.get(f"/api/v1/games/{game_id}")
    assert after_hint.json()["version"] == version
    assert "lines" not in after_hint.json()
    assert "best_move" not in after_hint.json()

    wrong_turn = await admin.post(
        f"/api/v1/games/{game_id}/moves",
        headers={"X-CSRF-Token": admin_csrf},
        json={"version": version, "path": path},
    )
    assert wrong_turn.status_code == 409

    played = await player.post(
        f"/api/v1/games/{game_id}/moves",
        headers={"X-CSRF-Token": player_csrf},
        json={"version": version, "path": path},
    )
    assert played.status_code == 200
    assert played.json()["state"]["moves"]
    reloaded = await player.get(f"/games/{game_id}")
    assert path[0] in reloaded.text


async def test_parallel_move_and_session_expiry(clients) -> None:
    admin, _player, database = clients
    csrf = await _login(admin, "admin", "admin-pass-1")
    created = await admin.post(
        "/api/v1/games",
        headers={"X-CSRF-Token": csrf},
        json={
            "game_type": "checkers",
            "mode": "free",
            "player_side": "white",
            "engine_level": 1,
            "engine_time_ms": 200,
        },
    )
    state = created.json()
    game_id = state["id"]
    move = state["legal_moves"][0]

    async def send() -> int:
        response = await admin.post(
            f"/api/v1/games/{game_id}/moves",
            headers={"X-CSRF-Token": csrf},
            json={"version": state["version"], "path": move["path"]},
        )
        return response.status_code

    codes = sorted(await asyncio.gather(send(), send()))
    assert codes == [200, 409]

    chess = await admin.post(
        "/api/v1/games",
        headers={"X-CSRF-Token": csrf},
        json={
            "game_type": "chess",
            "mode": "vs_computer",
            "player_side": "black",
            "engine_level": 1,
            "engine_time_ms": 200,
        },
    )
    assert chess.status_code == 201
    board = chess.json()
    assert board["black_at_bottom"] is True
    assert board["your_turn"] is False
    assert board["can_hint"] is True
    assert board["legal_moves"] == []
    page = await admin.get(f"/games/{board['id']}")
    assert '"black_at_bottom": true' in page.text

    await database["conn"].execute(
        "UPDATE sessions SET expires_at = now() - interval '1 minute' WHERE user_id = $1",
        database["admin_id"],
    )
    expired = await admin.get("/api/v1/games/" + board["id"])
    assert expired.status_code == 401


def _site_form(csrf: str, **overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "csrf_token": csrf,
        "username_min": "3",
        "username_max": "32",
        "password_min": "10",
        "password_needs_letter": "on",
        "password_needs_digit": "on",
        "session_hours": "336",
        "login_failures": "5",
        "login_window_minutes": "15",
        "starting_chips": "500",
        "notice": "",
        "game": ["chess", "checkers", "uno", "poker", "durak", "blackjack", "preferans"],
    }
    data.update(overrides)
    return data


async def test_admin_configures_site(clients) -> None:
    admin, player, database = clients
    admin_csrf = await _login(admin, "admin", "admin-pass-1")
    player_csrf = await _login(player, "player", "player-pass-1")
    hidden = await player.get("/admin/site")
    assert hidden.status_code == 404
    page = await admin.get("/admin/site")
    assert page.status_code == 200
    assert "Регистрация по ссылкам пользователей" in page.text

    weak = await admin.post("/admin/site", data=_site_form(admin_csrf, password_min="4"))
    assert weak.status_code == 422

    saved = await admin.post(
        "/admin/site",
        data=_site_form(admin_csrf, registration_open="on", notice="Вечер открыт", game=["chess", "checkers", "poker"]),
        follow_redirects=True,
    )
    assert saved.status_code == 200
    assert "Настройки сохранены." in saved.text
    home = await player.get("/")
    assert "Вечер открыт" in home.text
    new_game = await player.get("/games/new")
    assert "Уно" not in new_game.text
    assert "UNO" not in new_game.text
    denied = await player.post(
        "/api/v1/games",
        headers={"X-CSRF-Token": player_csrf},
        json={"game_type": "uno", "mode": "vs_computer", "player_side": "white"},
    )
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "game_closed"

    await admin.post("/logout", data={"csrf_token": admin_csrf})
    register_page = await admin.get("/register")
    assert register_page.status_code == 200
    bare = await admin.post(
        "/register",
        data={"username": "bare", "password": "bare-pass-1", "csrf_token": _login_token(register_page.text)},
    )
    assert bare.status_code == 422
    assert "не робот" in bare.text
    created = await admin.post(
        "/register",
        data={
            "username": "newbie",
            "password": "newbie-pass-1",
            **await _signup_fields(admin, bare.text),
        },
    )
    assert created.status_code == 303
    newbie_csrf = await _login(admin, "newbie", "newbie-pass-1")
    await admin.post("/logout", data={"csrf_token": newbie_csrf})
    short = await admin.get("/register")
    rejected = await admin.post(
        "/register",
        data={"username": "shorty", "password": "short1", **await _signup_fields(admin, short.text)},
    )
    assert rejected.status_code == 422

    admin_csrf = await _login(admin, "admin", "admin-pass-1")
    await admin.post(
        f"/admin/users/{database['player_id']}/chips",
        data={"csrf_token": admin_csrf, "balance": "40"},
    )
    purse = await player.get("/")
    assert "40 фишек" in purse.text

    closed = await admin.post(
        "/admin/site",
        data=_site_form(admin_csrf, maintenance="on"),
        follow_redirects=True,
    )
    assert closed.status_code == 200
    maintained = await player.get("/")
    assert maintained.status_code == 503
    assert "Гостиная закрыта" in maintained.text
    office = await admin.get("/admin/site")
    assert office.status_code == 200
    await admin.post("/admin/site", data=_site_form(admin_csrf), follow_redirects=True)
    await admin.post(
        f"/admin/users/{database['player_id']}/active",
        data={"csrf_token": admin_csrf, "active": "0"},
    )
    blocked = await player.get("/lobby")
    assert blocked.status_code == 303


async def test_referral_registration_remembers_who_invited(clients) -> None:
    admin, guest, database = clients
    csrf = await _login(admin, "admin", "admin-pass-1")
    code = await database["conn"].fetchval(
        "SELECT referral_code FROM users WHERE id = $1",
        database["admin_id"],
    )
    await admin.post("/admin/site", data=_site_form(csrf, registration_mode="referral"))
    plain = await guest.get("/")
    assert 'href="/register"' not in plain.text
    assert (await guest.get("/register")).status_code == 303
    blocked = await admin.post(
        "/register",
        headers={"Accept": "application/json"},
        data={"username": "outsider", "password": "outsider-pass-1", "csrf_token": csrf},
    )
    assert blocked.status_code == 403
    assert blocked.json()["error"]["code"] == "referral_required"
    invited = await guest.get(f"/?ref={code}")
    assert 'href="/register"' in invited.text
    login = await guest.get("/login")
    assert "signup-link" in login.text
    page = await guest.get("/register")
    assert page.status_code == 200
    created = await guest.post(
        "/register",
        data={"username": "invited", "password": "invited-pass-1", **await _signup_fields(guest, page.text)},
    )
    assert created.status_code == 303
    who = await database["conn"].fetchval("SELECT referred_by FROM users WHERE username = 'invited'")
    assert who == database["admin_id"]
    overview = await admin.get("/admin/overview")
    assert "Пригласил" in overview.text
    assert "invited" in overview.text


async def test_landing_news_and_referral(clients) -> None:
    admin, guest, database = clients
    home = await guest.get("/")
    assert home.status_code == 200
    assert "Хороший вечер" in home.text
    assert 'href="/register"' not in home.text
    csrf = await _login(admin, "admin", "admin-pass-1")
    code = await database["conn"].fetchval(
        "SELECT referral_code FROM users WHERE id = $1",
        database["admin_id"],
    )
    linked = await guest.get(f"/?ref={code}")
    assert "pn_ref" in linked.cookies
    await admin.post(
        "/admin/site",
        data=_site_form(csrf, registration_open="on", referral_chips="25", starting_chips="10"),
    )
    opened = await guest.get("/")
    assert 'href="/register"' in opened.text
    login = await guest.get("/login")
    assert "signup-link" in login.text
    page = await guest.get("/register")
    created = await guest.post(
        "/register",
        data={"username": "friend", "password": "friend-pass-1", **await _signup_fields(guest, page.text)},
    )
    assert created.status_code == 303
    born = await database["conn"].fetchval("SELECT born_on FROM users WHERE username = 'friend'")
    assert str(born) == "1990-11-16"
    inviter = await database["conn"].fetchval("SELECT referred_by FROM users WHERE username = 'friend'")
    assert inviter == database["admin_id"]
    balance = await database["conn"].fetchval(
        "SELECT balance FROM wallets WHERE user_id = $1",
        database["admin_id"],
    )
    assert balance == 525
    posted = await admin.post(
        "/admin/news",
        data={
            "csrf_token": csrf,
            "title": "Вечер открыт",
            "summary": "Собираемся за стол.",
            "body": "Приходите с друзьями.",
            "kind": "event",
            "published_on": "2026-11-16",
        },
        follow_redirects=True,
    )
    assert posted.status_code == 200
    assert "Вечер открыт" in posted.text
    public = await guest.get("/")
    assert "Вечер открыт" in public.text
    found = re.search(r'href="(/news/[^"]+)"', public.text)
    assert found is not None
    article = await guest.get(found.group(1))
    assert article.status_code == 200
    assert "Приходите с друзьями." in article.text


async def test_recent_games_are_paged(clients) -> None:
    _admin, player, database = clients
    await _login(player, "player", "player-pass-1")
    conn = database["conn"]
    user_id = database["player_id"]
    for index in range(10):
        game_id = await games_repo.insert_game(
            conn,
            user_id=user_id,
            game_type="chess",
            variant="standard",
            mode="vs_computer",
            player_side="white",
            status="finished",
            initial_position="start",
            current_position="start",
            result="white_win",
            result_reason=None,
            engine_level=1,
            engine_time_ms=200,
            join_code=None,
            audience="closed",
        )
        await conn.execute(
            "UPDATE games SET updated_at = now() - ($2::int * interval '1 minute') WHERE id = $1",
            game_id,
            index,
        )
    waiting = await games_repo.insert_game(
        conn,
        user_id=user_id,
        game_type="chess",
        variant="standard",
        mode="online",
        player_side="white",
        status="waiting",
        initial_position="start",
        current_position="start",
        result=None,
        result_reason=None,
        engine_level=1,
        engine_time_ms=200,
        join_code="pagecode",
        audience="closed",
    )
    await conn.execute(
        "UPDATE games SET updated_at = now() - interval '3 hours' WHERE id = $1",
        waiting,
    )
    first = await player.get("/")
    assert first.status_code == 200
    assert "Продолжить" in first.text
    assert "pagecode" not in first.text
    assert "1–10 из 11" in first.text
    second = await player.get("/?page=2")
    assert second.status_code == 200
    assert "pagecode" in second.text
    assert "Продолжить" in second.text
    assert 'aria-current="page">2<' in second.text
    too_far = await player.get("/?page=9", follow_redirects=False)
    assert too_far.status_code == 303
    assert too_far.headers["location"] == "/?page=2"
    junk = await player.get("/?page=abc", follow_redirects=False)
    assert junk.status_code == 303
    assert junk.headers["location"] == "/"


async def test_opponent_accepts_a_rematch(clients) -> None:
    admin, player, database = clients
    admin_csrf = await _login(admin, "admin", "admin-pass-1")
    player_csrf = await _login(player, "player", "player-pass-1")
    from app.chess.rules import STARTING_FEN

    game_id = await games_repo.insert_game(
        database["conn"],
        user_id=database["player_id"],
        opponent_id=database["admin_id"],
        game_type="chess",
        variant="standard",
        mode="online",
        player_side="white",
        status="finished",
        initial_position=STARTING_FEN,
        current_position=STARTING_FEN,
        result="black_win",
        result_reason="checkmate",
        engine_level=1,
        engine_time_ms=200,
        join_code=None,
        audience="closed",
    )
    page = await player.get(f"/games/{game_id}")
    assert page.status_code == 200
    assert 'id="status" class="status-pill is-loss" role="status" data-hint="Победа чёрных">Победа чёрных</p>' in page.text
    assert "Реванш!" in page.text
    offered = await player.post(
        f"/api/v1/games/{game_id}/rematch",
        headers={"X-CSRF-Token": player_csrf},
        json={},
    )
    assert offered.status_code == 200
    assert offered.json()["game_id"] is None
    assert offered.json()["rematch"]["state"] == "outgoing"
    seen = await admin.get(f"/api/v1/games/{game_id}")
    assert seen.json()["status_line"] == "Победа чёрных"
    assert seen.json()["result_tone"] == "win"
    assert seen.json()["rematch"]["state"] == "incoming"
    accepted = await admin.post(
        f"/api/v1/games/{game_id}/rematch",
        headers={"X-CSRF-Token": admin_csrf},
        json={},
    )
    assert accepted.status_code == 200
    new_id = accepted.json()["game_id"]
    assert new_id
    fresh = await player.get(f"/api/v1/games/{new_id}")
    assert fresh.status_code == 200
    assert fresh.json()["status"] == "active"
    assert fresh.json()["your_side"] == "black"
    opponent = await admin.get(f"/api/v1/games/{new_id}")
    assert opponent.json()["your_side"] == "white"


async def test_player_can_stop_an_empty_table(clients) -> None:
    _admin, player, _database = clients
    csrf = await _login(player, "player", "player-pass-1")
    created = await player.post(
        "/api/v1/games",
        headers={"X-CSRF-Token": csrf},
        json={"game_type": "chess", "mode": "online", "player_side": "white", "engine_level": 1, "engine_time_ms": 200},
    )
    assert created.status_code == 201
    state = created.json()
    assert state["waiting"] is True
    page = await player.get(f"/games/{state['id']}")
    assert "Остановить" in page.text
    assert "Сдаться" not in page.text
    stopped = await player.post(
        f"/api/v1/games/{state['id']}/stop",
        headers={"X-CSRF-Token": csrf},
        json={"version": state["version"]},
    )
    assert stopped.status_code == 200
    body = stopped.json()
    assert body["status"] == "finished"
    assert body["result"] is None
    assert body["status_line"] == "Партия остановлена."
    assert body["join_code"] is None
    again = await player.post(
        f"/api/v1/games/{state['id']}/stop",
        headers={"X-CSRF-Token": csrf},
        json={"version": body["version"]},
    )
    assert again.status_code == 409


async def test_only_the_starter_can_stop(clients) -> None:
    admin, player, _database = clients
    player_csrf = await _login(player, "player", "player-pass-1")
    admin_csrf = await _login(admin, "admin", "admin-pass-1")
    created = await player.post(
        "/api/v1/games",
        headers={"X-CSRF-Token": player_csrf},
        json={"game_type": "chess", "mode": "online", "player_side": "white", "engine_level": 1, "engine_time_ms": 200},
    )
    assert created.status_code == 201
    state = created.json()
    assert state["can_stop"] is True
    joined = await admin.post(
        "/api/v1/games/join",
        headers={"X-CSRF-Token": admin_csrf},
        json={"code": state["join_code"]},
    )
    assert joined.status_code == 200
    assert joined.json()["can_stop"] is False
    guest = await admin.get(f"/games/{state['id']}")
    assert "Остановить" not in guest.text
    host = await player.get(f"/games/{state['id']}")
    assert "Остановить" in host.text
    denied = await admin.post(
        f"/api/v1/games/{state['id']}/stop",
        headers={"X-CSRF-Token": admin_csrf},
        json={"version": joined.json()["version"]},
    )
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "stop_forbidden"


async def test_admin_grants_chips_on_profile(clients) -> None:
    admin, player, _database = clients
    player_csrf = await _login(player, "player", "player-pass-1")
    hidden = await player.get("/players/player")
    assert hidden.status_code == 200
    assert "Начислить фишки" not in hidden.text
    denied = await player.post("/players/player/chips", data={"csrf_token": player_csrf, "amount": "25"})
    assert denied.status_code == 404

    admin_csrf = await _login(admin, "admin", "admin-pass-1")
    page = await admin.get("/players/player")
    assert page.status_code == 200
    assert "Начислить фишки" in page.text
    assert "Сколько добавить" in page.text
    granted = await admin.post(
        "/players/player/chips",
        data={"csrf_token": admin_csrf, "amount": "25"},
        follow_redirects=True,
    )
    assert granted.status_code == 200
    assert "Фишки начислены." in granted.text
    assert "Сейчас 525 фишек." in granted.text
    purse = await player.get("/")
    assert "525 фишек" in purse.text
    history = await player.get("/chips")
    assert history.status_code == 200
    assert "Начисление" in history.text
    assert "+25" in history.text
    rejected = await admin.post("/players/player/chips", data={"csrf_token": admin_csrf, "amount": "0"})
    assert rejected.status_code == 422
    assert "от 1 до 100 000" in rejected.text
    still = await player.get("/")
    assert "525 фишек" in still.text


async def test_open_table_lets_a_logged_in_player_sit(clients) -> None:
    admin, player, _db = clients
    admin_csrf = await _login(admin, "admin", "admin-pass-1")
    player_csrf = await _login(player, "player", "player-pass-1")
    closed = await player.post(
        "/api/v1/games",
        headers={"X-CSRF-Token": player_csrf},
        json={
            "game_type": "checkers",
            "mode": "online",
            "player_side": "white",
            "audience": "closed",
            "engine_level": 1,
            "engine_time_ms": 200,
        },
    )
    assert closed.status_code == 201
    closed_id = closed.json()["id"]
    hidden = await admin.get(f"/games/{closed_id}")
    assert hidden.status_code == 404
    refused = await admin.post(
        f"/live/{closed_id}/sit",
        data={"csrf_token": admin_csrf},
    )
    assert refused.status_code == 403
    assert "За закрытый стол садятся по коду приглашения." in refused.text

    created = await player.post(
        "/api/v1/games",
        headers={"X-CSRF-Token": player_csrf},
        json={
            "game_type": "durak",
            "mode": "online",
            "player_side": "white",
            "audience": "open",
            "engine_level": 1,
            "engine_time_ms": 200,
            "computers": 1,
            "open_seats": 1,
            "durak_kind": "podkidnoy",
        },
    )
    assert created.status_code == 201
    game_id = created.json()["id"]
    assert created.json()["waiting"] is True
    assert created.json()["can_sit"] is False

    page = await admin.get(f"/games/{game_id}")
    assert page.status_code == 200
    assert 'class="sit-open"' in page.text
    assert 'class="audience-badge is-watch"' in page.text
    assert "Вы наблюдаете за столом и не делаете ходов." in page.text
    own = await player.get(f"/games/{game_id}")
    assert 'class="sit-open"' not in own.text
    live = await admin.get("/live")
    assert live.status_code == 200
    assert f'action="/live/{game_id}/sit"' in live.text
    assert ">Сесть</button>" in live.text

    computer = await player.post(
        "/api/v1/games",
        headers={"X-CSRF-Token": player_csrf},
        json={
            "game_type": "checkers",
            "mode": "vs_computer",
            "player_side": "white",
            "audience": "open",
            "engine_level": 1,
            "engine_time_ms": 200,
        },
    )
    assert computer.status_code == 201
    watched = await admin.get(f"/games/{computer.json()['id']}")
    assert watched.status_code == 200
    assert 'class="sit-open"' not in watched.text

    sat = await admin.post(
        f"/live/{game_id}/sit",
        data={"csrf_token": _csrf_from(page.text)},
        follow_redirects=False,
    )
    assert sat.status_code == 303
    assert sat.headers["location"] == f"/games/{game_id}"
    seated = await admin.get(f"/games/{game_id}")
    assert seated.status_code == 200
    assert 'class="sit-open"' not in seated.text
    assert "Вы наблюдаете за столом и не делаете ходов." not in seated.text


async def test_minor_cannot_enter_an_adult_table(clients) -> None:
    admin, player, database = clients
    admin_csrf = await _login(admin, "admin", "admin-pass-1")
    player_csrf = await _login(player, "player", "player-pass-1")
    await database["conn"].execute(
        "UPDATE users SET born_on = $2 WHERE id = $1",
        database["admin_id"],
        date(1982, 9, 26),
    )
    await database["conn"].execute(
        "UPDATE users SET born_on = $2 WHERE id = $1",
        database["player_id"],
        date(2015, 1, 1),
    )

    grown = await admin.get("/games/new")
    assert grown.status_code == 200
    assert 'href="/games/new/poker"' in grown.text
    assert "data-open" not in grown.text
    hidden = await player.get("/games/new")
    assert hidden.status_code == 200
    assert 'href="/games/new/poker"' not in hidden.text
    assert 'href="/games/new/blackjack"' not in hidden.text
    assert 'href="/games/new/preferans"' not in hidden.text
    direct = await player.get("/games/new/poker")
    assert direct.status_code == 403
    assert "Игра с 18 лет" in direct.text
    assert "Покер доступен с 18 лет" in direct.text
    assert 'id="new-game"' not in direct.text

    created = await admin.post(
        "/api/v1/games",
        headers={"X-CSRF-Token": admin_csrf},
        json={
            "game_type": "poker",
            "mode": "online",
            "player_side": "white",
            "audience": "open",
            "computers": 1,
            "open_seats": 1,
            "engine_level": 1,
            "engine_time_ms": 200,
        },
    )
    assert created.status_code == 201
    game_id = created.json()["id"]
    code = created.json()["join_code"]

    board = await player.get(f"/games/{game_id}")
    assert board.status_code == 403
    assert "Покер доступен с 18 лет" in board.text
    assert "Сесть за стол и смотреть партию нельзя" in board.text
    assert "card-table" not in board.text
    analysis = await player.get(f"/games/{game_id}/analysis")
    assert analysis.status_code == 403
    assert "Игра с 18 лет" in analysis.text

    checkers = await admin.post(
        "/api/v1/games",
        headers={"X-CSRF-Token": admin_csrf},
        json={
            "game_type": "checkers",
            "mode": "vs_computer",
            "player_side": "white",
            "audience": "open",
            "engine_level": 1,
            "engine_time_ms": 200,
        },
    )
    assert checkers.status_code == 201
    checkers_id = checkers.json()["id"]

    live = await player.get("/live")
    assert live.status_code == 200
    assert live.text.count("С 18 лет") == 1
    assert f'href="/games/{game_id}"' not in live.text
    assert f"/live/{game_id}/sit" not in live.text
    assert f"/live/{game_id}/watch" not in live.text
    assert f"/live/{checkers_id}/watch" in live.text
    assert "Уно · 18+" not in live.text
    assert "Шахматы · 18+" not in live.text

    sat = await player.post(f"/live/{game_id}/sit", data={"csrf_token": player_csrf})
    assert sat.status_code == 403
    assert "Покер доступен с 18 лет" in sat.text
    watched = await player.post(f"/live/{game_id}/watch", data={"csrf_token": player_csrf})
    assert watched.status_code == 403
    assert "data-open" in watched.text
    joined = await player.post("/join", data={"csrf_token": player_csrf, "code": code})
    assert joined.status_code == 403
    assert "Сесть за стол и смотреть партию нельзя" in joined.text
    looked = await player.post("/join/watch", data={"csrf_token": player_csrf, "code": code})
    assert looked.status_code == 403
    sought = await player.post(
        "/lobby/seek",
        data={"csrf_token": player_csrf, "game_type": "poker", "seats": "2"},
    )
    assert sought.status_code == 403
    assert "Покер доступен с 18 лет" in sought.text

    game_uuid = uuid.UUID(game_id)
    seated = await database["conn"].fetchval(
        "SELECT count(*) FROM game_seats WHERE game_id = $1 AND user_id = $2",
        game_uuid,
        database["player_id"],
    )
    watchers = await database["conn"].fetchval(
        "SELECT count(*) FROM watchers WHERE game_id = $1 AND user_id = $2",
        game_uuid,
        database["player_id"],
    )
    seeking = await database["conn"].fetchval(
        "SELECT count(*) FROM seekers WHERE user_id = $1",
        database["player_id"],
    )
    assert seated == 0
    assert watchers == 0
    assert seeking == 0


async def test_player_can_change_password_when_it_matches_the_rules(clients) -> None:
    from app.main import app

    _admin, player, _database = clients
    csrf = await _login(player, "player", "player-pass-1")
    page = await player.get("/settings")
    assert page.status_code == 200
    assert 'id="password-form"' in page.text
    assert "Старый пароль" in page.text
    assert "Новый пароль ещё раз" in page.text
    assert "Не меньше 10 символов, хотя бы одна буква, хотя бы одна цифра, не длиннее 128 символов." in page.text

    async def post(current: str, new: str, repeat: str | None = None):
        return await player.post(
            "/settings/password",
            data={
                "csrf_token": csrf,
                "current_password": current,
                "new_password": new,
                "repeat_password": new if repeat is None else repeat,
            },
        )

    mismatch = await post("player-pass-1", "player-pass-2", "player-pass-3")
    assert mismatch.status_code == 200
    assert "Новые пароли не совпадают." in mismatch.text
    short = await post("player-pass-1", "short1")
    assert "Пароль должен содержать не меньше 10 символов." in short.text
    letters = await post("player-pass-1", "abcdefghij")
    assert "В пароле нужна хотя бы одна цифра." in letters.text
    digits = await post("player-pass-1", "1234567890")
    assert "В пароле нужна хотя бы одна буква." in digits.text
    huge = await post("player-pass-1", "a1" + ("b" * 127))
    assert "Пароль слишком длинный." in huge.text
    wrong = await post("not-the-old", "player-pass-2")
    assert "Старый пароль указан неверно." in wrong.text
    same = await post("player-pass-1", "player-pass-1")
    assert "Новый пароль совпадает со старым." in same.text

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as other:
        await _login(other, "player", "player-pass-1")
        changed = await post("player-pass-1", "player-pass-2")
        assert changed.status_code == 303
        assert changed.headers["location"] == "/settings?password=changed"
        done = await player.get("/settings?password=changed")
        assert done.status_code == 200
        assert "Пароль изменён." in done.text
        still = await player.get("/settings")
        assert still.status_code == 200
        kicked = await other.get("/settings")
        assert kicked.status_code == 303
        assert kicked.headers["location"] == "/login"

    signed_out = await player.post("/logout", data={"csrf_token": csrf})
    assert signed_out.status_code == 303
    login_page = await player.get("/login")
    stale = await player.post(
        "/login",
        data={
            "username": "player",
            "password": "player-pass-1",
            "csrf_token": _login_token(login_page.text),
            "captcha": await _captcha(player),
        },
    )
    assert stale.status_code == 401
    await _login(player, "player", "player-pass-2")


async def test_profile_can_send_a_friend_request(clients) -> None:
    admin, player, database = clients
    await _login(admin, "admin", "admin-pass-1")
    own = await admin.get("/players/admin")
    assert own.status_code == 200
    assert "Добавить в друзья" not in own.text
    csrf = await _login(player, "player", "player-pass-1")
    page = await player.get("/players/admin")
    assert page.status_code == 200
    assert "В гостиной с" in page.text
    assert page.text.index("В гостиной с") < page.text.index("Добавить в друзья")
    assert 'class="friend-add"' in page.text
    sent = await player.post("/players/admin/friend", data={"csrf_token": csrf})
    assert sent.status_code == 303
    assert sent.headers["location"] == "/players/admin"
    again = await player.get("/players/admin")
    assert "Заявка отправлена" in again.text
    assert "Добавить в друзья" not in again.text
    status = await database["conn"].fetchval(
        """
        SELECT status FROM friendships
        WHERE requester_id = $1 AND addressee_id = $2
        """,
        database["player_id"],
        database["admin_id"],
    )
    assert status == "pending"


async def test_watcher_count_drops_when_the_guest_leaves(clients) -> None:
    admin, player, database = clients
    admin_csrf = await _login(admin, "admin", "admin-pass-1")
    player_csrf = await _login(player, "player", "player-pass-1")
    created = await admin.post(
        "/api/v1/games",
        headers={"X-CSRF-Token": admin_csrf},
        json={
            "game_type": "checkers",
            "mode": "vs_computer",
            "player_side": "white",
            "audience": "open",
            "engine_level": 1,
            "engine_time_ms": 200,
        },
    )
    assert created.status_code == 201
    game_id = created.json()["id"]
    watched = await player.post(
        f"/live/{game_id}/watch",
        data={"csrf_token": player_csrf},
        follow_redirects=False,
    )
    assert watched.status_code == 303
    state = await admin.get(f"/api/v1/games/{game_id}")
    assert [item["username"] for item in state.json()["watchers"]] == ["player"]
    listed = await admin.get(f"/api/v1/games/{game_id}/watchers")
    assert [item["username"] for item in listed.json()["watchers"]] == ["player"]

    left = await player.post(
        f"/api/v1/games/{game_id}/watch/leave",
        headers={"X-CSRF-Token": player_csrf},
    )
    assert left.status_code == 200
    gone = await admin.get(f"/api/v1/games/{game_id}")
    assert gone.json()["watchers"] == []
    stayed = await player.get(f"/api/v1/games/{game_id}/watchers")
    assert [item["username"] for item in stayed.json()["watchers"]] == ["player"]

    arrived = await player.post(
        f"/api/v1/games/{game_id}/watch/arrive",
        headers={"X-CSRF-Token": player_csrf},
    )
    assert arrived.status_code == 200
    back = await admin.get(f"/api/v1/games/{game_id}")
    assert [item["username"] for item in back.json()["watchers"]] == ["player"]

    await database["conn"].execute(
        "UPDATE watchers SET seen_at = now() - interval '1 minute' WHERE game_id = $1",
        uuid.UUID(game_id),
    )
    stale = await admin.get(f"/api/v1/games/{game_id}")
    assert stale.json()["watchers"] == []
    still = await database["conn"].fetchval(
        "SELECT count(*) FROM watchers WHERE game_id = $1",
        uuid.UUID(game_id),
    )
    assert still == 0


async def test_logout_revokes_session(clients) -> None:
    admin, _player, _db = clients
    csrf = await _login(admin, "admin", "admin-pass-1")
    response = await admin.post("/logout", data={"csrf_token": csrf})
    assert response.status_code == 303
    assert response.headers["location"] == "/"
    again = await admin.get("/api/v1/games/00000000-0000-0000-0000-000000000000")
    assert again.status_code == 401
