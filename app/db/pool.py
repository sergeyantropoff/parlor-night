"""Пул соединений asyncpg. Запросы остаются параметризованными."""

from __future__ import annotations

import json

import asyncpg


async def _init_connection(conn: asyncpg.Connection) -> None:
    await conn.set_type_codec(
        "jsonb",
        schema="pg_catalog",
        encoder=lambda value: json.dumps(value, ensure_ascii=False),
        decoder=json.loads,
        format="text",
    )


async def create_pool(database_url: str) -> asyncpg.Pool:
    return await asyncpg.create_pool(
        database_url,
        min_size=1,
        max_size=10,
        init=_init_connection,
        command_timeout=30,
    )
