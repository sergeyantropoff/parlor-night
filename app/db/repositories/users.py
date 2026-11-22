"""Пользователи в PostgreSQL."""

from __future__ import annotations

import re
import secrets
import uuid
from dataclasses import dataclass
from datetime import date, datetime

import asyncpg

from app.errors import AppError
from app.names import called, shown
from app.wallet import credit


@dataclass(frozen=True, slots=True)
class User:
    id: uuid.UUID
    username: str
    role: str
    full_name: str = ""
    ask_name: bool = False
    avatar: str = ""
    born_on: date | None = None
    email: str = ""

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

    @property
    def needs_intake(self) -> bool:
        return self.born_on is None or self.ask_name

    @property
    def display_name(self) -> str:
        return shown(self.full_name, self.username)

    @property
    def called_name(self) -> str:
        return called(self.full_name, self.username)


@dataclass(frozen=True, slots=True)
class UserRecord:
    id: uuid.UUID
    username: str
    password_hash: str
    role: str
    is_active: bool
    created_at: datetime


_CODE = "abcdefghijkmnopqrstuvwxyz23456789"
_REFERRAL = re.compile(r"^[a-z0-9]{6,12}$")


def new_referral_code() -> str:
    return "".join(secrets.choice(_CODE) for _ in range(8))


def _user(row: asyncpg.Record) -> User:
    return User(
        id=row["id"],
        username=row["username"],
        role=row["role"],
        full_name=str(row["full_name"] or ""),
        ask_name=bool(row["ask_name"]),
        avatar=str(row["avatar"] or ""),
    )


async def create_user(
    conn: asyncpg.Connection,
    *,
    username: str,
    password_hash: str,
    role: str,
    starting_chips: int = 500,
    born_on: date | None = None,
    ask_name: bool = False,
    email: str | None = None,
) -> User:
    user_id = uuid.uuid4()
    row = None
    for _ in range(5):
        try:
            row = await conn.fetchrow(
                """
                INSERT INTO users (id, username, password_hash, role, referral_code, born_on, ask_name, email)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                RETURNING id, username, role, full_name, ask_name, avatar, born_on, email
                """,
                user_id,
                username,
                password_hash,
                role,
                new_referral_code(),
                born_on,
                ask_name,
                email,
            )
            break
        except asyncpg.UniqueViolationError as exc:
            if getattr(exc, "constraint_name", "") != "users_referral_code":
                raise
    assert row is not None
    await conn.execute(
        "INSERT INTO user_settings (user_id, theme) VALUES ($1, 'dark')",
        user_id,
    )
    await conn.execute(
        "INSERT INTO wallets (user_id, balance) VALUES ($1, $2)",
        user_id,
        starting_chips,
    )
    return _user(row)


async def get_auth_record(conn: asyncpg.Connection, username: str) -> UserRecord | None:
    row = await conn.fetchrow(
        """
        SELECT id, username, password_hash, role, is_active, created_at
        FROM users
        WHERE username = $1
           OR ($2 AND lower(email) = $1)
        """,
        username,
        "@" in username,
    )
    if row is None:
        return None
    return UserRecord(
        id=row["id"],
        username=row["username"],
        password_hash=row["password_hash"],
        role=row["role"],
        is_active=row["is_active"],
        created_at=row["created_at"],
    )


async def list_users(conn: asyncpg.Connection) -> list[asyncpg.Record]:
    return await conn.fetch(
        """
        SELECT u.id, u.username, u.full_name, u.avatar, u.role, u.is_active, u.created_at,
               COALESCE(w.balance, 0) AS balance
        FROM users AS u
        LEFT JOIN wallets AS w ON w.user_id = u.id
        ORDER BY u.created_at
        """
    )


async def referral_code(conn: asyncpg.Connection, user_id: uuid.UUID) -> str:
    value = await conn.fetchval("SELECT referral_code FROM users WHERE id = $1", user_id)
    return str(value or "")


async def attach_referral(conn: asyncpg.Connection, user_id: uuid.UUID, code: str, chips: int) -> None:
    if not _REFERRAL.fullmatch(code):
        return
    inviter = await conn.fetchrow(
        "SELECT id FROM users WHERE referral_code = $1 AND is_active = TRUE",
        code,
    )
    if inviter is None or inviter["id"] == user_id:
        return
    updated = await conn.fetchval(
        """
        UPDATE users SET referred_by = $2
        WHERE id = $1 AND referred_by IS NULL
        RETURNING id
        """,
        user_id,
        inviter["id"],
    )
    if updated is not None and chips > 0:
        await credit(conn, inviter["id"], chips, reason="referral", game_id=None)


async def set_avatar(conn: asyncpg.Connection, user_id: uuid.UUID, avatar: str | None) -> str:
    previous = await conn.fetchval("SELECT avatar FROM users WHERE id = $1", user_id)
    await conn.execute(
        "UPDATE users SET avatar = $2, updated_at = now() WHERE id = $1",
        user_id,
        avatar,
    )
    return str(previous or "")


async def set_password_hash(conn: asyncpg.Connection, user_id: uuid.UUID, password_hash: str) -> None:
    await conn.execute(
        "UPDATE users SET password_hash = $2, updated_at = now() WHERE id = $1",
        user_id,
        password_hash,
    )


async def set_full_name(conn: asyncpg.Connection, user_id: uuid.UUID, full_name: str) -> None:
    await conn.execute(
        """
        UPDATE users
        SET full_name = $2, ask_name = FALSE, updated_at = now()
        WHERE id = $1
        """,
        user_id,
        full_name,
    )


async def get_user(conn: asyncpg.Connection, user_id: uuid.UUID) -> asyncpg.Record | None:
    return await conn.fetchrow(
        "SELECT id, username, role, is_active FROM users WHERE id = $1",
        user_id,
    )


async def set_email(conn: asyncpg.Connection, user_id: uuid.UUID, email: str) -> None:
    try:
        await conn.execute(
            "UPDATE users SET email = $2, updated_at = now() WHERE id = $1",
            user_id,
            email,
        )
    except asyncpg.UniqueViolationError as exc:
        raise AppError(409, "email_taken", "Эта почта уже указана у другого игрока.") from exc


async def set_active(conn: asyncpg.Connection, user_id: uuid.UUID, *, active: bool) -> None:
    await conn.execute(
        "UPDATE users SET is_active = $2, updated_at = now() WHERE id = $1",
        user_id,
        active,
    )


async def set_role(conn: asyncpg.Connection, user_id: uuid.UUID, role: str) -> None:
    await conn.execute(
        "UPDATE users SET role = $2, updated_at = now() WHERE id = $1",
        user_id,
        role,
    )


async def other_active_admins(conn: asyncpg.Connection, user_id: uuid.UUID) -> int:
    value = await conn.fetchval(
        """
        SELECT count(*) FROM users
        WHERE role = 'admin' AND is_active = TRUE AND id <> $1
        """,
        user_id,
    )
    return int(value or 0)
