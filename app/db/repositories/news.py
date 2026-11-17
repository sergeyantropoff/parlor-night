"""Новости и акции главной страницы."""

from __future__ import annotations

import uuid
from datetime import date

import asyncpg


async def count_news(conn: asyncpg.Connection) -> int:
    value = await conn.fetchval("SELECT count(*) FROM news_posts")
    return int(value or 0)


async def list_news(conn: asyncpg.Connection, limit: int = 12, offset: int = 0) -> list[asyncpg.Record]:
    return await conn.fetch(
        """
        SELECT id, title, summary, body, kind, cover, published_on
        FROM news_posts
        ORDER BY published_on DESC, created_at DESC
        LIMIT $1 OFFSET $2
        """,
        limit,
        offset,
    )


async def get_news(conn: asyncpg.Connection, news_id: uuid.UUID) -> asyncpg.Record | None:
    return await conn.fetchrow(
        """
        SELECT id, title, summary, body, kind, cover, published_on
        FROM news_posts
        WHERE id = $1
        """,
        news_id,
    )


async def add_news(
    conn: asyncpg.Connection,
    *,
    title: str,
    summary: str,
    body: str,
    kind: str,
    published_on: date,
    cover: str | None = None,
) -> None:
    await conn.execute(
        """
        INSERT INTO news_posts (id, title, summary, body, kind, published_on, cover)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        """,
        uuid.uuid4(),
        title,
        summary,
        body,
        kind,
        published_on,
        cover,
    )


async def update_news(
    conn: asyncpg.Connection,
    news_id: uuid.UUID,
    *,
    title: str,
    summary: str,
    body: str,
    kind: str,
    published_on: date,
    cover: str | None,
) -> bool:
    status = await conn.execute(
        """
        UPDATE news_posts
        SET title = $2,
            summary = $3,
            body = $4,
            kind = $5,
            published_on = $6,
            cover = $7
        WHERE id = $1
        """,
        news_id,
        title,
        summary,
        body,
        kind,
        published_on,
        cover,
    )
    return status == "UPDATE 1"


async def delete_news(conn: asyncpg.Connection, news_id: uuid.UUID) -> None:
    await conn.execute("DELETE FROM news_posts WHERE id = $1", news_id)
