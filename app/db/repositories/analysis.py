"""Кэш разбора позиции."""

from __future__ import annotations

import json
import uuid

import asyncpg


async def get_cached(
    conn: asyncpg.Connection,
    *,
    game_type: str,
    variant: str,
    position_hash: str,
    engine_name: str,
    engine_version: str,
    settings_hash: str,
) -> asyncpg.Record | None:
    return await conn.fetchrow(
        """
        SELECT best_move, evaluation, principal_variation, depth, nodes
        FROM analysis_cache
        WHERE game_type = $1 AND variant = $2 AND position_hash = $3
          AND engine_name = $4 AND engine_version = $5 AND engine_settings_hash = $6
        """,
        game_type,
        variant,
        position_hash,
        engine_name,
        engine_version,
        settings_hash,
    )


async def put_cached(
    conn: asyncpg.Connection,
    *,
    game_type: str,
    variant: str,
    position_hash: str,
    engine_name: str,
    engine_version: str,
    settings_hash: str,
    best_move: dict[str, object],
    evaluation: dict[str, object],
    principal_variation: list[object],
    depth: int,
    nodes: int,
) -> None:
    await conn.execute(
        """
        INSERT INTO analysis_cache (
            id, game_type, variant, position_hash, engine_name, engine_version,
            engine_settings_hash, best_move, evaluation, principal_variation, depth, nodes
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb, $9::jsonb, $10::jsonb, $11, $12)
        ON CONFLICT (
            game_type, variant, position_hash, engine_name, engine_version, engine_settings_hash
        )
        DO NOTHING
        """,
        uuid.uuid4(),
        game_type,
        variant,
        position_hash,
        engine_name,
        engine_version,
        settings_hash,
        json.dumps(best_move, ensure_ascii=False),
        json.dumps(evaluation, ensure_ascii=False),
        json.dumps(principal_variation, ensure_ascii=False),
        depth,
        nodes,
    )
