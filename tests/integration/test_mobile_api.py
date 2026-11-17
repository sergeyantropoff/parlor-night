"""Вход мобильного приложения и обновление токена."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re

import asyncpg
import pytest
from httpx import ASGITransport, AsyncClient
from tests.integration.test_online import _csrf_from, _login

from app.auth.captcha import solve
from app.auth.passwords import Passwords
from app.config import get_settings
from app.db.migrate import apply_migrations
from app.db.repositories import users

pytestmark = pytest.mark.asyncio


async def _connect() -> asyncpg.Connection:
    try:
        return await asyncpg.connect(os.environ["DATABASE_URL"], timeout=3)
    except Exception as exc:
        pytest.skip(f"Тестовый PostgreSQL недоступен: {exc}")


@pytest.fixture
async def client():
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
    secret = hashlib.sha256(b"sample-secret").hexdigest()
    await conn.execute(
        """
        INSERT INTO api_clients (id, name, kind, secret_hash, redirect_uris)
        VALUES ('sample-app', 'Sample', 'third_party', $1, ARRAY['https://app.example/callback'])
        ON CONFLICT (id) DO UPDATE
        SET secret_hash = EXCLUDED.secret_hash, redirect_uris = EXCLUDED.redirect_uris, is_active = TRUE
        """,
        secret,
    )
    passwords = Passwords(get_settings())
    await users.create_user(
        conn,
        username="mobile",
        password_hash=passwords.hash_password("mobile-pass-1"),
        role="user",
    )
    from app.main import app

    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as http:
            yield http
    await conn.close()


async def _token(
    http: AsyncClient,
    username: str = "mobile",
    password: str = "mobile-pass-1",
    client_id: str = "parlor-ios",
):
    return await http.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password, "client_id": client_id},
    )


def _auth(access: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access}"}


async def test_mobile_login_refresh_and_reuse(client: AsyncClient):
    denied = await client.get("/api/v1/home")
    assert denied.status_code == 401

    foreign = await _token(client, client_id="sample-app")
    assert foreign.status_code == 403

    logged = await _token(client)
    assert logged.status_code == 200
    body = logged.json()
    assert body["token_type"] == "Bearer"
    assert body["expires_in"] == 900
    assert body["user"]["username"] == "mobile"

    me = await client.get("/api/v1/auth/me", headers=_auth(body["access_token"]))
    assert me.status_code == 200
    assert me.json()["user"]["username"] == "mobile"
    assert me.json()["client_id"] == "parlor-ios"

    home = await client.get("/api/v1/home", headers=_auth(body["access_token"]))
    assert home.status_code == 200
    assert "greeting" in home.json()

    catalog = await client.get("/api/v1/catalog", headers=_auth(body["access_token"]))
    assert catalog.status_code == 200
    assert any(item["key"] == "chess" for item in catalog.json()["games"])

    news = await client.get("/api/v1/news")
    assert news.status_code == 200

    refreshed = await client.post("/api/v1/auth/refresh", json={"refresh_token": body["refresh_token"]})
    assert refreshed.status_code == 200
    fresh = refreshed.json()
    assert fresh["access_token"] != body["access_token"]
    assert fresh["refresh_token"] != body["refresh_token"]

    stale = await client.get("/api/v1/auth/me", headers=_auth(body["access_token"]))
    assert stale.status_code == 401

    again = await client.post("/api/v1/auth/refresh", json={"refresh_token": body["refresh_token"]})
    assert again.status_code == 401
    reused = await client.get("/api/v1/home", headers=_auth(fresh["access_token"]))
    assert reused.status_code == 401

    current = await _token(client)
    access = current.json()["access_token"]
    out = await client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": current.json()["refresh_token"]},
        headers=_auth(access),
    )
    assert out.status_code == 200
    gone = await client.get("/api/v1/auth/me", headers=_auth(access))
    assert gone.status_code == 401


async def test_third_party_confirmation_issues_the_same_tokens(client: AsyncClient):
    await _login(client, "mobile", "mobile-pass-1")
    page = await client.get(
        "/oauth/authorize",
        params={"client_id": "sample-app", "redirect_uri": "https://app.example/callback", "state": "xyz"},
    )
    assert page.status_code == 200
    assert "Sample" in page.text
    csrf = _csrf_from(page.text)
    hidden = re.search(r'name="csrf_token" value="([^"]+)"', page.text)
    assert hidden is not None
    decided = await client.post(
        "/oauth/authorize",
        data={
            "csrf_token": hidden.group(1),
            "client_id": "sample-app",
            "redirect_uri": "https://app.example/callback",
            "state": "xyz",
            "decision": "allow",
        },
        headers={"x-csrf-token": csrf},
        follow_redirects=False,
    )
    assert decided.status_code == 303
    location = decided.headers["location"]
    assert location.startswith("https://app.example/callback?")
    code = re.search(r"code=([^&]+)", location)
    assert code is not None
    traded = await client.post(
        "/api/v1/auth/token",
        json={
            "grant_type": "authorization_code",
            "code": code.group(1),
            "client_id": "sample-app",
            "client_secret": "sample-secret",
            "redirect_uri": "https://app.example/callback",
        },
    )
    assert traded.status_code == 200
    me = await client.get("/api/v1/auth/me", headers=_auth(traded.json()["access_token"]))
    assert me.status_code == 200
    assert me.json()["user"]["username"] == "mobile"
    repeat = await client.post(
        "/api/v1/auth/token",
        json={
            "grant_type": "authorization_code",
            "code": code.group(1),
            "client_id": "sample-app",
            "client_secret": "sample-secret",
            "redirect_uri": "https://app.example/callback",
        },
    )
    assert repeat.status_code == 401


async def _mode(mode: str) -> None:
    from app.main import app

    async with app.state.pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO site_settings (id, registration_open, registration_mode)
            VALUES (TRUE, $1, $2)
            ON CONFLICT (id) DO UPDATE
            SET registration_open = EXCLUDED.registration_open,
                registration_mode = EXCLUDED.registration_mode
            """,
            mode == "open",
            mode,
        )
    app.state.site_policy = None
    app.state.site_policy_until = 0.0


async def _captcha(http: AsyncClient, ref: str = "") -> str:
    response = await http.get("/api/v1/auth/captcha", params={"ref": ref} if ref else {})
    assert response.status_code == 200, response.text
    task = response.json()
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


def _signup(
    captcha: str,
    username: str = "newbie",
    referral: str = "",
    client_id: str = "parlor-ios",
) -> dict[str, str]:
    return {
        "username": username,
        "password": "newbie-pass-1",
        "client_id": client_id,
        "born_day": "16",
        "born_month": "11",
        "born_year": "1990",
        "captcha": captcha,
        "referral": referral,
    }


async def test_mobile_registration_follows_the_house_rules(client: AsyncClient):
    closed = await client.get("/api/v1/auth/register")
    assert closed.status_code == 200
    assert closed.json()["mode"] == "closed"
    assert closed.json()["open"] is False
    refused = await client.post("/api/v1/auth/register", json=_signup("x" * 24))
    assert refused.status_code == 403
    assert refused.json()["error"]["code"] == "registration_disabled"

    await _mode("open")
    opened = await client.get("/api/v1/auth/register")
    assert opened.json()["open"] is True
    foreign = await client.post("/api/v1/auth/register", json=_signup(await _captcha(client), client_id="sample-app"))
    assert foreign.status_code == 403

    created = await client.post("/api/v1/auth/register", json=_signup(await _captcha(client)))
    assert created.status_code == 201
    body = created.json()
    assert body["user"]["username"] == "newbie"
    assert body["user"]["ask_name"] is True
    me = await client.get("/api/v1/account", headers=_auth(body["access_token"]))
    assert me.status_code == 200
    assert me.json()["birth"]["born"] == "1990-11-16"

    taken = await client.post("/api/v1/auth/register", json=_signup(await _captcha(client), username="newbie"))
    assert taken.status_code == 409

    await _mode("referral")
    waiting = await client.get("/api/v1/auth/register")
    assert waiting.json()["referral_required"] is True
    assert waiting.json()["open"] is False
    blocked = await client.post("/api/v1/auth/register", json=_signup("x" * 24, username="guest"))
    assert blocked.status_code == 403
    from app.main import app

    async with app.state.pool.acquire() as conn:
        code = await conn.fetchval("SELECT referral_code FROM users WHERE username = 'mobile'")
    invited = await client.get("/api/v1/auth/register", params={"ref": code})
    assert invited.json()["open"] is True
    joined = await client.post(
        "/api/v1/auth/register",
        json=_signup(await _captcha(client, code), username="guest", referral=code),
    )
    assert joined.status_code == 201
    async with app.state.pool.acquire() as conn:
        inviter = await conn.fetchval(
            """
            SELECT u.username
            FROM users AS guest
            JOIN users AS u ON u.id = guest.referred_by
            WHERE guest.username = 'guest'
            """
        )
    assert inviter == "mobile"
