"""Настройки гостиной. Их меняет администратор, границы проверяет сервер."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass

import asyncpg
from starlette.requests import Request

from app.errors import AppError

_GAMES = ("chess", "checkers", "go", "uno", "poker", "durak", "blackjack", "preferans", "domino")
_MODES = ("closed", "referral", "open")
_REFERRAL = re.compile(r"^[a-z0-9]{6,12}$")


@dataclass(frozen=True, slots=True)
class SitePolicy:
    registration_mode: str
    username_min: int
    username_max: int
    password_min: int
    password_needs_letter: bool
    password_needs_digit: bool
    session_hours: int
    login_failures: int
    login_window_minutes: int
    starting_chips: int
    referral_chips: int
    chess: bool
    checkers: bool
    go: bool
    uno: bool
    poker: bool
    durak: bool
    blackjack: bool
    preferans: bool
    domino: bool
    notice: str
    maintenance: bool

    @property
    def registration_open(self) -> bool:
        return self.registration_mode == "open"

    def allows(self, game: str) -> bool:
        if game not in _GAMES:
            return False
        return bool(getattr(self, game))

    @property
    def session_ttl_seconds(self) -> int:
        return self.session_hours * 3600

    @property
    def login_window_seconds(self) -> int:
        return self.login_window_minutes * 60


def defaults() -> SitePolicy:
    return SitePolicy(
        registration_mode="closed",
        username_min=3,
        username_max=32,
        password_min=10,
        password_needs_letter=True,
        password_needs_digit=True,
        session_hours=336,
        login_failures=5,
        login_window_minutes=15,
        starting_chips=500,
        referral_chips=100,
        chess=True,
        checkers=True,
        go=True,
        uno=True,
        poker=True,
        durak=True,
        blackjack=True,
        preferans=True,
        domino=True,
        notice="",
        maintenance=False,
    )


def password_floor(local: bool) -> int:
    return 4 if local else 10


def _flag(value: object) -> bool:
    return str(value or "").lower() in {"1", "on", "true", "yes"}


def _number(value: object, *, low: int, high: int, label: str) -> int:
    try:
        number = int(str(value))
    except (TypeError, ValueError):
        raise AppError(422, "bad_settings", f"Поле «{label}» должно быть числом.") from None
    if not low <= number <= high:
        raise AppError(422, "bad_settings", f"«{label}»: допустимо от {low} до {high}.")
    return number


def normalize(data: dict[str, object], *, local: bool) -> SitePolicy:
    username_min = _number(data.get("username_min"), low=3, high=16, label="Минимальная длина логина")
    username_max = _number(data.get("username_max"), low=8, high=32, label="Максимальная длина логина")
    if username_min > username_max:
        raise AppError(422, "bad_settings", "Минимальная длина логина больше максимальной.")
    letter = True if not local else _flag(data.get("password_needs_letter"))
    digit = True if not local else _flag(data.get("password_needs_digit"))
    games = {str(item) for item in data.get("games") or []}
    chosen = {name: name in games for name in _GAMES}
    if not any(chosen.values()):
        raise AppError(422, "bad_settings", "Оставьте открытой хотя бы одну игру.")
    notice = " ".join(str(data.get("notice") or "").split())
    if len(notice) > 240:
        raise AppError(422, "bad_settings", "Объявление длиннее 240 символов.")
    mode = str(data.get("registration_mode") or "")
    if mode not in _MODES:
        mode = "open" if _flag(data.get("registration_open")) else "closed"
    return SitePolicy(
        registration_mode=mode,
        username_min=username_min,
        username_max=username_max,
        password_min=_number(
            data.get("password_min"),
            low=password_floor(local),
            high=64,
            label="Минимальная длина пароля",
        ),
        password_needs_letter=letter,
        password_needs_digit=digit,
        session_hours=_number(data.get("session_hours"), low=1, high=2160, label="Срок сессии"),
        login_failures=_number(data.get("login_failures"), low=3, high=20, label="Попытки входа"),
        login_window_minutes=_number(
            data.get("login_window_minutes"),
            low=5,
            high=1440,
            label="Окно блокировки",
        ),
        starting_chips=_number(data.get("starting_chips"), low=0, high=100_000, label="Фишки новому игроку"),
        referral_chips=_number(
            100 if data.get("referral_chips") in (None, "") else data.get("referral_chips"),
            low=0,
            high=100_000,
            label="Фишки за приглашение",
        ),
        chess=chosen["chess"],
        checkers=chosen["checkers"],
        go=chosen["go"],
        uno=chosen["uno"],
        poker=chosen["poker"],
        durak=chosen["durak"],
        blackjack=chosen["blackjack"],
        preferans=chosen["preferans"],
        domino=chosen["domino"],
        notice=notice,
        maintenance=_flag(data.get("maintenance")),
    )


def from_row(row: asyncpg.Record) -> SitePolicy:
    return SitePolicy(
        registration_mode=str(row["registration_mode"]),
        username_min=int(row["username_min"]),
        username_max=int(row["username_max"]),
        password_min=int(row["password_min"]),
        password_needs_letter=bool(row["password_needs_letter"]),
        password_needs_digit=bool(row["password_needs_digit"]),
        session_hours=int(row["session_hours"]),
        login_failures=int(row["login_failures"]),
        login_window_minutes=int(row["login_window_minutes"]),
        starting_chips=int(row["starting_chips"]),
        referral_chips=int(row["referral_chips"]),
        chess=bool(row["chess_open"]),
        checkers=bool(row["checkers_open"]),
        go=bool(row["go_open"]),
        uno=bool(row["uno_open"]),
        poker=bool(row["poker_open"]),
        durak=bool(row["durak_open"]),
        blackjack=bool(row["blackjack_open"]),
        preferans=bool(row["preferans_open"]),
        domino=bool(row["domino_open"]),
        notice=str(row["notice"] or ""),
        maintenance=bool(row["maintenance"]),
    )


async def load_policy(conn: asyncpg.Connection, *, registration_default: bool = False) -> SitePolicy:
    row = await conn.fetchrow("SELECT * FROM site_settings WHERE id = TRUE")
    if row is None:
        await conn.execute(
            """
            INSERT INTO site_settings (id, registration_open, registration_mode)
            VALUES (TRUE, $1, $2)
            """,
            registration_default,
            "open" if registration_default else "closed",
        )
        row = await conn.fetchrow("SELECT * FROM site_settings WHERE id = TRUE")
    assert row is not None
    return from_row(row)


async def save_policy(conn: asyncpg.Connection, policy: SitePolicy) -> None:
    await conn.execute(
        """
        UPDATE site_settings
        SET registration_open = $1,
            username_min = $2,
            username_max = $3,
            password_min = $4,
            password_needs_letter = $5,
            password_needs_digit = $6,
            session_hours = $7,
            login_failures = $8,
            login_window_minutes = $9,
            starting_chips = $10,
            referral_chips = $11,
            chess_open = $12,
            checkers_open = $13,
            uno_open = $14,
            poker_open = $15,
            durak_open = $16,
            blackjack_open = $17,
            preferans_open = $18,
            notice = $19,
            maintenance = $20,
            registration_mode = $21,
            go_open = $22,
            domino_open = $23,
            updated_at = now()
        WHERE id = TRUE
        """,
        policy.registration_open,
        policy.username_min,
        policy.username_max,
        policy.password_min,
        policy.password_needs_letter,
        policy.password_needs_digit,
        policy.session_hours,
        policy.login_failures,
        policy.login_window_minutes,
        policy.starting_chips,
        policy.referral_chips,
        policy.chess,
        policy.checkers,
        policy.uno,
        policy.poker,
        policy.durak,
        policy.blackjack,
        policy.preferans,
        policy.notice,
        policy.maintenance,
        policy.registration_mode,
        policy.go,
        policy.domino,
    )


async def referral_is_live(request: Request, code: str) -> bool:
    if not _REFERRAL.fullmatch(code):
        return False
    pool = getattr(request.app.state, "pool", None)
    if pool is None:
        return False
    async with pool.acquire() as conn:
        found = await conn.fetchval(
            "SELECT 1 FROM users WHERE referral_code = $1 AND is_active = TRUE",
            code,
        )
    return found is not None


async def visitor_may_register(request: Request, policy: SitePolicy) -> bool:
    """Открытая регистрация доступна всем. Режим по ссылке — только с живым приглашением."""
    if policy.registration_mode == "open":
        return True
    if policy.registration_mode != "referral":
        return False
    code = str(request.cookies.get("pn_ref") or request.query_params.get("ref") or "")
    return await referral_is_live(request, code)


def remember(app: object, policy: SitePolicy) -> None:
    state = app.state  # type: ignore[attr-defined]
    state.site_policy = policy
    state.site_policy_until = time.monotonic() + 5


async def current(request: Request) -> SitePolicy:
    return await current_app(request.app)


async def current_app(app: object) -> SitePolicy:
    state = app.state  # type: ignore[attr-defined]
    cached = getattr(state, "site_policy", None)
    until = float(getattr(state, "site_policy_until", 0.0))
    if isinstance(cached, SitePolicy) and time.monotonic() < until:
        return cached
    pool = getattr(state, "pool", None)
    if pool is None:
        return defaults()
    async with pool.acquire() as conn:
        policy = await load_policy(conn, registration_default=bool(state.settings.allow_registration))
    remember(app, policy)
    return policy
