"""Локальные учётные записи на время разработки."""

from __future__ import annotations

import asyncpg

from app.auth.passwords import Passwords
from app.db.repositories.users import create_user, get_auth_record


async def ensure_local_accounts(pool: asyncpg.Pool, passwords: Passwords) -> None:
    async with pool.acquire() as conn:
        for username, password, role in (
            ("admin", "admin", "admin"),
            ("user", "user", "user"),
        ):
            digest = passwords.hash_password(password)
            existing = await get_auth_record(conn, username)
            if existing is None:
                try:
                    await create_user(conn, username=username, password_hash=digest, role=role)
                except asyncpg.UniqueViolationError:
                    pass
                continue
            await conn.execute(
                "UPDATE users SET password_hash = $2, role = $3, is_active = TRUE, updated_at = now() WHERE id = $1",
                existing.id,
                digest,
                role,
            )
