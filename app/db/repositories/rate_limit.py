"""Ограничение частоты входа и запросов к движкам."""

from __future__ import annotations

import asyncpg


async def login_blocked(
    conn: asyncpg.Connection,
    *,
    username: str,
    ip_address: str,
    limit: int,
    window_seconds: int,
) -> bool:
    count = await conn.fetchval(
        """
        SELECT count(*)
        FROM login_attempts
        WHERE username = $1
          AND ip_address = $2
          AND success = FALSE
          AND created_at > now() - ($3::int * interval '1 second')
        """,
        username,
        ip_address,
        window_seconds,
    )
    return int(count or 0) >= limit


async def login_failures(
    conn: asyncpg.Connection,
    *,
    username: str | None,
    ip_address: str | None,
    window_seconds: int,
) -> int:
    filters = ["success = FALSE", "created_at > now() - ($1::int * interval '1 second')"]
    values: list[object] = [window_seconds]
    if username is not None:
        values.append(username)
        filters.append(f"username = ${len(values)}")
    if ip_address is not None:
        values.append(ip_address)
        filters.append(f"ip_address = ${len(values)}")
    count = await conn.fetchval(
        f"SELECT count(*) FROM login_attempts WHERE {' AND '.join(filters)}",
        *values,
    )
    return int(count or 0)


async def record_login(
    conn: asyncpg.Connection,
    *,
    username: str,
    ip_address: str,
    success: bool,
) -> None:
    await conn.execute(
        """
        INSERT INTO login_attempts (username, ip_address, success)
        VALUES ($1, $2, $3)
        """,
        username[:64],
        ip_address[:64],
        success,
    )
    await conn.execute(
        """
        DELETE FROM login_attempts
        WHERE username = $1 AND created_at < now() - interval '2 days'
        """,
        username[:64],
    )


async def clear_login_failures(conn: asyncpg.Connection) -> None:
    await conn.execute("DELETE FROM login_attempts WHERE success = FALSE")


async def consume_rate(
    conn: asyncpg.Connection,
    *,
    bucket: str,
    limit: int,
    window_seconds: int,
) -> bool:
    async with conn.transaction():
        await conn.execute(
            """
            DELETE FROM rate_events
            WHERE bucket = $1 AND created_at < now() - interval '1 day'
            """,
            bucket,
        )
        count = await conn.fetchval(
            """
            SELECT count(*)
            FROM rate_events
            WHERE bucket = $1
              AND created_at > now() - ($2::int * interval '1 second')
            """,
            bucket,
            window_seconds,
        )
        if int(count or 0) >= limit:
            return False
        await conn.execute("INSERT INTO rate_events (bucket) VALUES ($1)", bucket)
        return True
