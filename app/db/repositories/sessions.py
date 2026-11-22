"""Серверные сессии. В cookie лежит исходный токен, в базе — только его хеш."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date

import asyncpg

from app.auth.csrf import new_session_secrets
from app.db.repositories.users import User


@dataclass(frozen=True, slots=True)
class Session:
    id: uuid.UUID
    user: User
    csrf_token: str


async def create_session(
    conn: asyncpg.Connection,
    *,
    user_id: uuid.UUID,
    ttl_seconds: int,
    user_agent: str | None,
    ip_address: str | None,
) -> tuple[str, str]:
    token, digest, csrf = new_session_secrets()
    await conn.execute(
        """
        INSERT INTO sessions (id, token_hash, user_id, csrf_token, expires_at, user_agent, ip_address)
        VALUES ($1, $2, $3, $4, now() + make_interval(secs => $5), $6, $7)
        """,
        uuid.uuid4(),
        digest,
        user_id,
        csrf,
        ttl_seconds,
        (user_agent or "")[:300],
        ip_address,
    )
    return token, csrf


async def revoke_token(conn: asyncpg.Connection, token_hash: str) -> None:
    await conn.execute(
        """
        UPDATE sessions
        SET revoked_at = now()
        WHERE token_hash = $1 AND revoked_at IS NULL
        """,
        token_hash,
    )


async def revoke_other_sessions(conn: asyncpg.Connection, token_hash: str) -> None:
    await conn.execute(
        """
        UPDATE sessions
        SET revoked_at = now()
        WHERE revoked_at IS NULL AND token_hash <> $1
        """,
        token_hash,
    )


async def revoke_other_user_sessions(conn: asyncpg.Connection, user_id: uuid.UUID, token_hash: str) -> None:
    await conn.execute(
        """
        UPDATE sessions
        SET revoked_at = now()
        WHERE user_id = $1 AND revoked_at IS NULL AND token_hash <> $2
        """,
        user_id,
        token_hash,
    )


async def revoke_user_sessions(conn: asyncpg.Connection, user_id: uuid.UUID) -> None:
    await conn.execute(
        """
        UPDATE sessions
        SET revoked_at = now()
        WHERE user_id = $1 AND revoked_at IS NULL
        """,
        user_id,
    )


async def find_session(conn: asyncpg.Connection, token_hash: str) -> Session | None:
    row = await conn.fetchrow(
        """
        SELECT s.id AS session_id, s.csrf_token,
               u.id, u.username, u.role, u.full_name, u.ask_name, u.avatar, u.born_on, u.email
        FROM sessions AS s
        JOIN users AS u ON u.id = s.user_id
        WHERE s.token_hash = $1
          AND s.revoked_at IS NULL
          AND s.expires_at > now()
          AND u.is_active = TRUE
        """,
        token_hash,
    )
    if row is None:
        return None
    return Session(
        id=row["session_id"],
        user=User(
            id=row["id"],
            username=row["username"],
            role=row["role"],
            full_name=str(row["full_name"] or ""),
            ask_name=bool(row["ask_name"]),
            avatar=str(row["avatar"] or ""),
            born_on=row["born_on"] if isinstance(row["born_on"], date) else None,
            email=str(row["email"] or ""),
        ),
        csrf_token=row["csrf_token"],
    )
