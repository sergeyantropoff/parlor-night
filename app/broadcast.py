"""Одно сообщение для всех, кто вошёл. Новый текст — новая ревизия."""

from __future__ import annotations

import uuid

from app.errors import AppError

TONES = {
    "info": "Информация",
    "warning": "Внимание",
    "ok": "Все хорошо!",
    "error": "Критическая ошибка!",
}
_LIMIT = 500


def clean_broadcast(body: str, tone: str) -> tuple[str, str]:
    text = body.strip()
    if len(text) > _LIMIT:
        raise AppError(422, "broadcast", "Сообщение не длиннее 500 символов.")
    if not text:
        return "", "info"
    if tone not in TONES:
        raise AppError(422, "broadcast", "Выберите тип сообщения.")
    return text, tone


async def current(conn) -> dict[str, str]:
    row = await conn.fetchrow("SELECT body, tone FROM site_broadcast WHERE id")
    if row is None:
        return {"body": "", "tone": "info"}
    tone = row["tone"] if row["tone"] in TONES else "info"
    return {"body": str(row["body"] or ""), "tone": tone}


async def for_user(conn, user_id: uuid.UUID) -> dict[str, str] | None:
    row = await conn.fetchrow("SELECT body, tone, revision FROM site_broadcast WHERE id")
    if row is None or not str(row["body"] or "").strip() or row["tone"] not in TONES:
        return None
    seen = await conn.fetchval("SELECT revision FROM broadcast_seen WHERE user_id = $1", user_id)
    if seen == row["revision"]:
        return None
    return {"revision": str(row["revision"]), "tone": str(row["tone"]), "text": str(row["body"])}


async def publish(conn, body: str, tone: str) -> None:
    await conn.execute(
        """
        INSERT INTO site_broadcast (id, body, tone, revision)
        VALUES (TRUE, $1, $2, $3)
        ON CONFLICT (id) DO UPDATE
        SET body = EXCLUDED.body,
            tone = EXCLUDED.tone,
            revision = EXCLUDED.revision,
            updated_at = now()
        """,
        body,
        tone,
        uuid.uuid4(),
    )


async def dismiss(conn, user_id: uuid.UUID, revision: uuid.UUID) -> None:
    current_revision = await conn.fetchval("SELECT revision FROM site_broadcast WHERE id")
    if current_revision != revision:
        return
    await conn.execute(
        """
        INSERT INTO broadcast_seen (user_id, revision)
        VALUES ($1, $2)
        ON CONFLICT (user_id) DO UPDATE SET revision = EXCLUDED.revision
        """,
        user_id,
        revision,
    )
