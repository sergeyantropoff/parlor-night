"""Токены мобильного API. В базе лежит только хеш, исходный токен видит приложение."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from dataclasses import dataclass

import asyncpg

from app.db.repositories.users import User

ACCESS_SECONDS = 15 * 60
CODE_SECONDS = 60


@dataclass(frozen=True, slots=True)
class Client:
    id: str
    name: str
    kind: str
    secret_hash: str
    redirect_uris: tuple[str, ...]
    is_active: bool

    @property
    def first_party(self) -> bool:
        return self.kind == "first_party"


@dataclass(frozen=True, slots=True)
class Access:
    family_id: uuid.UUID
    client_id: str
    user: User


@dataclass(frozen=True, slots=True)
class Issued:
    access_token: str
    refresh_token: str
    refresh_id: uuid.UUID
    family_id: uuid.UUID
    access_seconds: int
    refresh_seconds: int


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def secret_matches(stored: str, given: str) -> bool:
    if not stored or not given:
        return False
    digest = hashlib.sha256(given.encode()).hexdigest()
    if len(digest) != len(stored):
        return False
    return hmac.compare_digest(digest, stored)


def _client(row: asyncpg.Record) -> Client:
    uris = row["redirect_uris"] or []
    return Client(
        id=row["id"],
        name=row["name"],
        kind=row["kind"],
        secret_hash=str(row["secret_hash"] or ""),
        redirect_uris=tuple(uris),
        is_active=bool(row["is_active"]),
    )


def _user(row: asyncpg.Record) -> User:
    return User(
        id=row["id"],
        username=row["username"],
        role=row["role"],
        full_name=str(row["full_name"] or ""),
        ask_name=bool(row["ask_name"]),
        avatar=str(row["avatar"] or ""),
    )


async def get_client(conn: asyncpg.Connection, client_id: str) -> Client | None:
    row = await conn.fetchrow(
        """
        SELECT id, name, kind, secret_hash, redirect_uris, is_active
        FROM api_clients
        WHERE id = $1
        """,
        client_id,
    )
    if row is None:
        return None
    return _client(row)


async def load_user(conn: asyncpg.Connection, user_id: uuid.UUID) -> User | None:
    row = await conn.fetchrow(
        """
        SELECT id, username, role, full_name, ask_name, avatar
        FROM users
        WHERE id = $1 AND is_active = TRUE
        """,
        user_id,
    )
    if row is None:
        return None
    return _user(row)


async def issue_pair(
    conn: asyncpg.Connection,
    *,
    user_id: uuid.UUID,
    client_id: str,
    refresh_seconds: int,
    user_agent: str | None,
    ip_address: str | None,
    family_id: uuid.UUID | None = None,
) -> Issued:
    family = family_id or uuid.uuid4()
    access_raw = secrets.token_urlsafe(32)
    refresh_raw = secrets.token_urlsafe(32)
    refresh_id = uuid.uuid4()
    agent = (user_agent or "")[:300]
    ip = (ip_address or "")[:64]
    await conn.execute(
        """
        INSERT INTO api_tokens (
            id, family_id, user_id, client_id, kind, token_hash, expires_at, user_agent, ip_address
        )
        VALUES
            ($1, $2, $3, $4, 'access', $5, now() + make_interval(secs => $6), $7, $8),
            ($9, $2, $3, $4, 'refresh', $10, now() + make_interval(secs => $11), $7, $8)
        """,
        uuid.uuid4(),
        family,
        user_id,
        client_id,
        token_digest(access_raw),
        ACCESS_SECONDS,
        agent,
        ip,
        refresh_id,
        token_digest(refresh_raw),
        refresh_seconds,
    )
    return Issued(
        access_token=access_raw,
        refresh_token=refresh_raw,
        refresh_id=refresh_id,
        family_id=family,
        access_seconds=ACCESS_SECONDS,
        refresh_seconds=refresh_seconds,
    )


async def find_access(conn: asyncpg.Connection, token_hash: str) -> Access | None:
    row = await conn.fetchrow(
        """
        SELECT t.family_id, t.client_id,
               u.id, u.username, u.role, u.full_name, u.ask_name, u.avatar
        FROM api_tokens AS t
        JOIN users AS u ON u.id = t.user_id
        JOIN api_clients AS c ON c.id = t.client_id
        WHERE t.token_hash = $1
          AND t.kind = 'access'
          AND t.revoked_at IS NULL
          AND t.expires_at > now()
          AND u.is_active = TRUE
          AND c.is_active = TRUE
        """,
        token_hash,
    )
    if row is None:
        return None
    return Access(family_id=row["family_id"], client_id=row["client_id"], user=_user(row))


async def rotate(
    conn: asyncpg.Connection,
    raw_refresh: str,
    *,
    refresh_seconds: int,
    user_agent: str | None,
    ip_address: str | None,
) -> tuple[Issued | None, bool]:
    """Возвращает новую пару либо признак, что погашенный refresh принесли ещё раз."""
    async with conn.transaction():
        row = await conn.fetchrow(
            """
            UPDATE api_tokens
            SET revoked_at = now()
            WHERE token_hash = $1
              AND kind = 'refresh'
              AND revoked_at IS NULL
              AND expires_at > now()
            RETURNING id, family_id, user_id, client_id
            """,
            token_digest(raw_refresh),
        )
        if row is None:
            stale = await conn.fetchrow(
                """
                SELECT family_id
                FROM api_tokens
                WHERE token_hash = $1 AND kind = 'refresh' AND revoked_at IS NOT NULL
                """,
                token_digest(raw_refresh),
            )
            if stale is None:
                return None, False
            await _revoke_family(conn, stale["family_id"])
            return None, True
        client = await get_client(conn, row["client_id"])
        user = await load_user(conn, row["user_id"])
        if client is None or not client.is_active or user is None:
            await _revoke_family(conn, row["family_id"])
            return None, False
        await _revoke_family(conn, row["family_id"])
        issued = await issue_pair(
            conn,
            user_id=user.id,
            client_id=client.id,
            refresh_seconds=refresh_seconds,
            user_agent=user_agent,
            ip_address=ip_address,
            family_id=row["family_id"],
        )
        await conn.execute(
            "UPDATE api_tokens SET replaced_by = $2 WHERE id = $1",
            row["id"],
            issued.refresh_id,
        )
        return issued, False


async def revoke_refresh(conn: asyncpg.Connection, raw_refresh: str) -> None:
    family = await conn.fetchval(
        "SELECT family_id FROM api_tokens WHERE token_hash = $1 AND kind = 'refresh'",
        token_digest(raw_refresh),
    )
    if family is not None:
        await _revoke_family(conn, family)


async def revoke_user(
    conn: asyncpg.Connection,
    user_id: uuid.UUID,
    *,
    keep_family: uuid.UUID | None = None,
) -> None:
    await conn.execute(
        """
        UPDATE api_tokens
        SET revoked_at = now()
        WHERE user_id = $1
          AND revoked_at IS NULL
          AND ($2::uuid IS NULL OR family_id <> $2)
        """,
        user_id,
        keep_family,
    )


async def revoke_all(conn: asyncpg.Connection) -> None:
    await conn.execute("UPDATE api_tokens SET revoked_at = now() WHERE revoked_at IS NULL")


async def _revoke_family(conn: asyncpg.Connection, family_id: uuid.UUID) -> None:
    await conn.execute(
        """
        UPDATE api_tokens
        SET revoked_at = now()
        WHERE family_id = $1 AND revoked_at IS NULL
        """,
        family_id,
    )


async def issue_code(
    conn: asyncpg.Connection,
    *,
    client_id: str,
    user_id: uuid.UUID,
    redirect_uri: str,
) -> str:
    raw = secrets.token_urlsafe(32)
    await conn.execute(
        """
        INSERT INTO api_grants (id, client_id, user_id, code_hash, redirect_uri, expires_at)
        VALUES ($1, $2, $3, $4, $5, now() + make_interval(secs => $6))
        """,
        uuid.uuid4(),
        client_id,
        user_id,
        token_digest(raw),
        redirect_uri,
        CODE_SECONDS,
    )
    return raw


async def take_code(
    conn: asyncpg.Connection,
    *,
    raw_code: str,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
) -> uuid.UUID | None:
    """Гасит код и возвращает пользователя, если клиент, адрес и секрет совпали."""
    async with conn.transaction():
        row = await conn.fetchrow(
            """
            SELECT id, user_id
            FROM api_grants
            WHERE code_hash = $1
              AND client_id = $2
              AND redirect_uri = $3
              AND used_at IS NULL
              AND expires_at > now()
            FOR UPDATE
            """,
            token_digest(raw_code),
            client_id,
            redirect_uri,
        )
        if row is None:
            return None
        client = await get_client(conn, client_id)
        if client is None or not client.is_active or client.kind != "third_party":
            return None
        if not secret_matches(client.secret_hash, client_secret):
            return None
        await conn.execute("UPDATE api_grants SET used_at = now() WHERE id = $1", row["id"])
        return row["user_id"]
