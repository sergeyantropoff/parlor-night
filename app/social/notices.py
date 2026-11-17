"""Счётчики сайдбара и свежие сообщения с заявками в друзья."""

from __future__ import annotations

import re
import uuid

import asyncpg

from app.names import shown

_INVITE_LINE = re.compile(r"зову за стол", re.IGNORECASE)
_TABLE_READY = {
    "доска уже накрыта, жду вас за столом.",
    "заходите, партия уже ждёт.",
}


async def nav_counts(conn: asyncpg.Connection, user_id: uuid.UUID) -> dict[str, int]:
    row = await conn.fetchrow(
        """
        SELECT
            (
                SELECT count(*)
                FROM friendships
                WHERE addressee_id = $1 AND status = 'pending'
            ) AS requests,
            (
                SELECT count(*)
                FROM (
                    SELECT m.sender_id
                    FROM messages AS m
                    LEFT JOIN chat_reads AS r
                      ON r.user_id = $1 AND r.peer_id = m.sender_id
                    WHERE m.recipient_id = $1
                      AND m.game_id IS NULL
                      AND m.created_at > COALESCE(r.read_at, '-infinity'::timestamptz)
                    GROUP BY m.sender_id
                ) AS unread
            ) AS chats,
            (
                SELECT count(*)
                FROM games
                WHERE mode IN ('online', 'vs_computer')
                  AND status IN ('waiting', 'active')
            ) AS live
        """,
        user_id,
    )
    return {"requests": int(row["requests"]), "chats": int(row["chats"]), "live": int(row["live"])}


async def unread_threads(conn: asyncpg.Connection, user_id: uuid.UUID) -> list[dict[str, object]]:
    rows = await conn.fetch(
        """
        SELECT u.username, count(*) AS unread
        FROM messages AS m
        JOIN users AS u ON u.id = m.sender_id
        LEFT JOIN chat_reads AS r
          ON r.user_id = $1 AND r.peer_id = m.sender_id
        WHERE m.recipient_id = $1
          AND m.game_id IS NULL
          AND m.created_at > COALESCE(r.read_at, '-infinity'::timestamptz)
        GROUP BY u.username
        """,
        user_id,
    )
    return [{"username": str(row["username"]), "unread": int(row["unread"])} for row in rows]


def clip_notice(body: object, limit: int = 160) -> str:
    text = " ".join(str(body or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def notice_text(body: object) -> str:
    text = " ".join(str(body or "").split())
    if _INVITE_LINE.search(text) or text.casefold() in _TABLE_READY:
        return "Приглашение в партию"
    return clip_notice(text)


async def fresh_notices(conn: asyncpg.Connection, user_id: uuid.UUID) -> list[dict[str, str]]:
    messages = await conn.fetch(
        """
        SELECT m.id, m.body, m.created_at, u.username, u.full_name, u.avatar
        FROM messages AS m
        JOIN users AS u ON u.id = m.sender_id
        LEFT JOIN chat_reads AS r
          ON r.user_id = $1 AND r.peer_id = m.sender_id
        WHERE m.recipient_id = $1
          AND m.game_id IS NULL
          AND m.created_at > COALESCE(r.read_at, '-infinity'::timestamptz)
        ORDER BY m.created_at DESC, m.id DESC
        LIMIT 6
        """,
        user_id,
    )
    requests = await conn.fetch(
        """
        SELECT f.id, f.created_at, u.username, u.full_name, u.avatar
        FROM friendships AS f
        JOIN users AS u ON u.id = f.requester_id
        WHERE f.addressee_id = $1 AND f.status = 'pending'
        ORDER BY f.created_at DESC, f.id DESC
        LIMIT 5
        """,
        user_id,
    )
    pending: list[tuple[object, dict[str, str]]] = []
    for row in messages:
        login = str(row["username"])
        pending.append(
            (
                row["created_at"],
                {
                    "kind": "message",
                    "id": str(row["id"]),
                    "name": shown(row["full_name"], login),
                    "username": login,
                    "avatar": row["avatar"] or "",
                    "text": notice_text(row["body"]),
                    "action": "Прочитать",
                    "href": f"/chats/{login}",
                },
            )
        )
    for row in requests:
        login = str(row["username"])
        pending.append(
            (
                row["created_at"],
                {
                    "kind": "request",
                    "id": str(row["id"]),
                    "name": shown(row["full_name"], login),
                    "username": login,
                    "avatar": row["avatar"] or "",
                    "text": "Хочет добавить вас в друзья",
                    "action": "Посмотреть",
                    "href": "/friends#requests",
                },
            )
        )
    pending.sort(key=lambda item: (item[0], item[1]["id"]), reverse=True)
    return [item for _, item in pending[:6]]


async def mark_chat_read(conn: asyncpg.Connection, user_id: uuid.UUID, peer_id: uuid.UUID) -> None:
    await conn.execute(
        """
        INSERT INTO chat_reads (user_id, peer_id, read_at)
        VALUES ($1, $2, now())
        ON CONFLICT (user_id, peer_id)
        DO UPDATE SET read_at = excluded.read_at
        """,
        user_id,
        peer_id,
    )
