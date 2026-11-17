"""Настройки пользователя."""

from __future__ import annotations

import json
import uuid

import asyncpg


def as_preferences(value: object) -> dict[str, object]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str) and value:
        loaded = json.loads(value)
        if isinstance(loaded, dict):
            return loaded
    return {}


DEFAULT_ANALYSIS = {
    "chess_depth": 12,
    "chess_time_ms": 1000,
    "chess_multipv": 3,
    "checkers_level": 3,
    "checkers_time_ms": 1000,
    "variety": False,
}


async def get_settings(conn: asyncpg.Connection, user_id: uuid.UUID) -> asyncpg.Record:
    row = await conn.fetchrow(
        """
        SELECT theme, board_style, default_game, default_side, analysis_preferences
        FROM user_settings
        WHERE user_id = $1
        """,
        user_id,
    )
    if row is None:
        await conn.execute("INSERT INTO user_settings (user_id) VALUES ($1)", user_id)
        row = await conn.fetchrow(
            """
            SELECT theme, board_style, default_game, default_side, analysis_preferences
            FROM user_settings
            WHERE user_id = $1
            """,
            user_id,
        )
    assert row is not None
    return row


async def update_settings(
    conn: asyncpg.Connection,
    user_id: uuid.UUID,
    *,
    theme: str,
    board_style: str,
    default_game: str,
    default_side: str,
    analysis_preferences: dict[str, object],
) -> None:
    await conn.execute(
        """
        INSERT INTO user_settings (
            user_id, theme, board_style, default_game, default_side, analysis_preferences, updated_at
        )
        VALUES ($1, $2, $3, $4, $5, $6::jsonb, now())
        ON CONFLICT (user_id) DO UPDATE
        SET theme = EXCLUDED.theme,
            board_style = EXCLUDED.board_style,
            default_game = EXCLUDED.default_game,
            default_side = EXCLUDED.default_side,
            analysis_preferences = EXCLUDED.analysis_preferences,
            updated_at = now()
        """,
        user_id,
        theme,
        board_style,
        default_game,
        default_side,
        json.dumps(analysis_preferences, ensure_ascii=False),
    )
