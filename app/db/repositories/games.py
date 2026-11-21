"""Партии и ходы. Изменение позиции идёт в транзакции с блокировкой строки."""

from __future__ import annotations

import json
import secrets
import uuid

import asyncpg

JOIN_ALPHABET = "abcdefghijkmnopqrstuvwxyz23456789"
WATCH_FRESH_SECONDS = 12


def new_join_code() -> str:
    return "".join(secrets.choice(JOIN_ALPHABET) for _ in range(8))


async def insert_game(
    conn: asyncpg.Connection,
    *,
    user_id: uuid.UUID,
    game_type: str,
    variant: str,
    mode: str,
    player_side: str,
    status: str,
    initial_position: str,
    current_position: str,
    result: str | None,
    result_reason: str | None,
    engine_level: int,
    engine_time_ms: int,
    join_code: str | None,
    audience: str,
    opponent_id: uuid.UUID | None = None,
) -> uuid.UUID:
    game_id = uuid.uuid4()
    await conn.execute(
        """
        INSERT INTO games (
            id, user_id, join_code, game_type, variant, mode, player_side, status,
            initial_position, current_position, result, result_reason,
            engine_level, engine_time_ms, audience, opponent_id
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16)
        """,
        game_id,
        user_id,
        join_code,
        game_type,
        variant,
        mode,
        player_side,
        status,
        initial_position,
        current_position,
        result,
        result_reason,
        engine_level,
        engine_time_ms,
        audience,
        opponent_id,
    )
    return game_id


async def get_visible(
    conn: asyncpg.Connection,
    game_id: uuid.UUID,
    user_id: uuid.UUID,
) -> asyncpg.Record | None:
    return await conn.fetchrow(
        """
        SELECT g.*, shown_name(cu.full_name, cu.username) AS creator_name,
               shown_name(ou.full_name, ou.username) AS opponent_name,
               cu.username AS creator_login, ou.username AS opponent_login,
               cu.avatar AS creator_avatar, ou.avatar AS opponent_avatar
        FROM games AS g
        JOIN users AS cu ON cu.id = g.user_id
        LEFT JOIN users AS ou ON ou.id = g.opponent_id
        WHERE g.id = $1 AND (
            g.user_id = $2 OR g.opponent_id = $2
            OR EXISTS (SELECT 1 FROM game_seats AS s WHERE s.game_id = g.id AND s.user_id = $2)
            OR EXISTS (SELECT 1 FROM watchers AS w WHERE w.game_id = g.id AND w.user_id = $2)
            OR (g.audience = 'open' AND g.mode IN ('online', 'vs_computer'))
        )
        """,
        game_id,
        user_id,
    )


async def lock_visible(
    conn: asyncpg.Connection,
    game_id: uuid.UUID,
    user_id: uuid.UUID,
) -> asyncpg.Record | None:
    return await conn.fetchrow(
        """
        SELECT g.*, shown_name(cu.full_name, cu.username) AS creator_name,
               shown_name(ou.full_name, ou.username) AS opponent_name,
               cu.username AS creator_login, ou.username AS opponent_login,
               cu.avatar AS creator_avatar, ou.avatar AS opponent_avatar
        FROM games AS g
        JOIN users AS cu ON cu.id = g.user_id
        LEFT JOIN users AS ou ON ou.id = g.opponent_id
        WHERE g.id = $1 AND (
            g.user_id = $2 OR g.opponent_id = $2
            OR EXISTS (SELECT 1 FROM game_seats AS s WHERE s.game_id = g.id AND s.user_id = $2)
        )
        FOR UPDATE OF g
        """,
        game_id,
        user_id,
    )


async def list_moves(conn: asyncpg.Connection, game_id: uuid.UUID) -> list[asyncpg.Record]:
    return await conn.fetch(
        """
        SELECT ply, notation, move_payload, position_before, position_after, created_at
        FROM game_moves
        WHERE game_id = $1
        ORDER BY ply
        """,
        game_id,
    )


async def insert_move(
    conn: asyncpg.Connection,
    *,
    game_id: uuid.UUID,
    ply: int,
    notation: str,
    payload: dict[str, object],
    position_before: str,
    position_after: str,
) -> None:
    await conn.execute(
        """
        INSERT INTO game_moves (
            id, game_id, ply, notation, move_payload, position_before, position_after
        )
        VALUES ($1, $2, $3, $4, $5::jsonb, $6, $7)
        """,
        uuid.uuid4(),
        game_id,
        ply,
        notation,
        json.dumps(payload, ensure_ascii=False),
        position_before,
        position_after,
    )


async def update_position(
    conn: asyncpg.Connection,
    *,
    game_id: uuid.UUID,
    user_id: uuid.UUID,
    version: int,
    current_position: str,
    status: str,
    result: str | None,
    result_reason: str | None,
) -> bool:
    result_row = await conn.execute(
        """
        UPDATE games
        SET current_position = $1,
            status = $2,
            result = $3,
            result_reason = $4,
            position_version = position_version + 1,
            updated_at = now()
        WHERE id = $5 AND (
            user_id = $6 OR opponent_id = $6
            OR EXISTS (SELECT 1 FROM game_seats AS s WHERE s.game_id = games.id AND s.user_id = $6)
        ) AND position_version = $7
        """,
        current_position,
        status,
        result,
        result_reason,
        game_id,
        user_id,
        version,
    )
    return result_row.endswith("1")


async def delete_last_moves(conn: asyncpg.Connection, game_id: uuid.UUID, count: int) -> str | None:
    rows = await conn.fetch(
        """
        SELECT id, position_before
        FROM game_moves
        WHERE game_id = $1
        ORDER BY ply DESC
        LIMIT $2
        """,
        game_id,
        count,
    )
    if len(rows) != count:
        return None
    await conn.execute(
        "DELETE FROM game_moves WHERE id = ANY($1::uuid[])",
        [row["id"] for row in rows],
    )
    return str(rows[-1]["position_before"])


_SEATED = """
    EXISTS (SELECT 1 FROM game_seats AS s WHERE s.game_id = g.id AND s.user_id = $1)
"""

_VISIBLE = f"""
    g.user_id = $1 OR g.opponent_id = $1
    OR {_SEATED}
    OR EXISTS (SELECT 1 FROM watchers AS w WHERE w.game_id = g.id AND w.user_id = $1)
"""

_RECENT_COLUMNS = """
    SELECT g.id, g.game_type, g.mode, g.player_side, g.status, g.result,
           g.updated_at, g.user_id, g.opponent_id, g.join_code,
           shown_name(cu.full_name, cu.username) AS creator_name,
           shown_name(ou.full_name, ou.username) AS opponent_name,
           cu.username AS creator_login, ou.username AS opponent_login,
           COALESCE(
               (SELECT s.seat_key FROM game_seats AS s
                WHERE s.game_id = g.id AND s.user_id = $1 LIMIT 1),
               CASE
                   WHEN g.user_id = $1 THEN g.player_side
                   WHEN g.opponent_id = $1 AND g.player_side = 'white' THEN 'black'
                   WHEN g.opponent_id = $1 THEN 'white'
               END
           ) AS seat_key,
           g.result_reason,
           CASE
               WHEN g.result = 'draw'
                AND g.game_type IN ('durak', 'blackjack', 'poker', 'preferans')
               THEN g.current_position
           END AS finish_position
    FROM games AS g
    JOIN users AS cu ON cu.id = g.user_id
    LEFT JOIN users AS ou ON ou.id = g.opponent_id
"""


async def count_recent(conn: asyncpg.Connection, user_id: uuid.UUID) -> int:
    value = await conn.fetchval(f"SELECT count(*) FROM games AS g WHERE {_VISIBLE}", user_id)
    return int(value or 0)


async def list_recent(
    conn: asyncpg.Connection,
    user_id: uuid.UUID,
    *,
    limit: int = 10,
    offset: int = 0,
) -> list[asyncpg.Record]:
    return await conn.fetch(
        f"""
        {_RECENT_COLUMNS}
        WHERE {_VISIBLE}
        ORDER BY g.updated_at DESC, g.id DESC
        LIMIT $2 OFFSET $3
        """,
        user_id,
        limit,
        offset,
    )


async def latest_open(conn: asyncpg.Connection, user_id: uuid.UUID) -> asyncpg.Record | None:
    return await conn.fetchrow(
        f"""
        {_RECENT_COLUMNS}
        WHERE ({_VISIBLE}) AND g.status IN ('active', 'waiting')
        ORDER BY g.updated_at DESC, g.id DESC
        LIMIT 1
        """,
        user_id,
    )


async def stats_rows(conn: asyncpg.Connection, user_id: uuid.UUID) -> list[asyncpg.Record]:
    return await conn.fetch(
        """
        SELECT game_type, mode, player_side, status, result, result_reason,
               user_id, opponent_id,
               (
                   SELECT s.seat_key FROM game_seats AS s
                   WHERE s.game_id = games.id AND s.user_id = $1
                   LIMIT 1
               ) AS seat_key,
               CASE
                   WHEN result = 'draw'
                    AND game_type IN ('durak', 'blackjack', 'poker', 'preferans')
                   THEN current_position
               END AS finish_position
        FROM games
        WHERE user_id = $1 OR opponent_id = $1
           OR EXISTS (SELECT 1 FROM game_seats AS s WHERE s.game_id = games.id AND s.user_id = $1)
        """,
        user_id,
    )


async def join_game(
    conn: asyncpg.Connection,
    *,
    code: str,
    user_id: uuid.UUID,
) -> asyncpg.Record | None:
    return await conn.fetchrow(
        """
        UPDATE games
        SET opponent_id = $2,
            status = 'active',
            position_version = position_version + 1,
            updated_at = now()
        WHERE join_code = $1
          AND mode = 'online'
          AND opponent_id IS NULL
          AND user_id <> $2
          AND status = 'waiting'
          AND NOT EXISTS (SELECT 1 FROM game_seats AS s WHERE s.game_id = games.id)
        RETURNING id
        """,
        code,
        user_id,
    )


async def find_by_code(conn: asyncpg.Connection, code: str) -> asyncpg.Record | None:
    return await conn.fetchrow(
        """
        SELECT id, user_id, opponent_id, status, game_type, audience
        FROM games
        WHERE join_code = $1 AND mode = 'online'
        """,
        code,
    )


async def set_flip(
    conn: asyncpg.Connection,
    *,
    game_id: uuid.UUID,
    user_id: uuid.UUID,
    creator: bool,
    flipped: bool,
) -> None:
    column = "creator_flipped" if creator else "opponent_flipped"
    await conn.execute(
        f"""
        UPDATE games
        SET {column} = $3, updated_at = now()
        WHERE id = $1 AND (user_id = $2 OR opponent_id = $2)
        """,
        game_id,
        user_id,
        flipped,
    )


async def replace_deal(conn: asyncpg.Connection, game_id: uuid.UUID, position: str) -> None:
    await conn.execute(
        """
        UPDATE games
        SET initial_position = $2,
            current_position = $2,
            status = 'active',
            position_version = position_version + 1,
            updated_at = now()
        WHERE id = $1
        """,
        game_id,
        position,
    )


async def list_live_tables(conn: asyncpg.Connection, user_id: uuid.UUID) -> list[asyncpg.Record]:
    return await conn.fetch(
        """
        SELECT g.id, g.game_type, g.mode, g.status, g.audience, g.created_at, g.updated_at,
               g.user_id, g.opponent_id, g.player_side,
               CASE
                   WHEN EXISTS (SELECT 1 FROM game_seats AS s WHERE s.game_id = g.id)
                   THEN (
                       SELECT count(*) FROM game_seats AS s
                       WHERE s.game_id = g.id AND s.kind = 'human' AND s.user_id IS NULL
                   )
                   WHEN g.mode = 'online' AND g.opponent_id IS NULL AND g.status = 'waiting' THEN 1
                   ELSE 0
               END AS vacancies,
               EXISTS (
                   SELECT 1 FROM game_seats AS s WHERE s.game_id = g.id AND s.user_id = $1
               ) AS seated,
               shown_name(cu.full_name, cu.username) AS creator_name,
               shown_name(ou.full_name, ou.username) AS opponent_name,
               cu.full_name AS creator_full, ou.full_name AS opponent_full,
               cu.username AS creator_login, ou.username AS opponent_login,
               cu.avatar AS creator_avatar, ou.avatar AS opponent_avatar,
               (SELECT count(*) FROM game_seats AS s WHERE s.game_id = g.id) AS seats,
               (SELECT count(*) FROM game_moves AS m WHERE m.game_id = g.id) AS moves,
               (SELECT count(*) FROM watchers AS w WHERE w.game_id = g.id) AS watchers,
               (
                   SELECT string_agg(s.seat_key, ',' ORDER BY s.seat_key)
                   FROM game_seats AS s
                   WHERE s.game_id = g.id AND s.kind = 'computer'
               ) AS cpu_seats,
               (
                   SELECT string_agg(shown_name(u.full_name, u.username), E'\x1f')
                   FROM game_seats AS s
                   JOIN users AS u ON u.id = s.user_id
                   WHERE s.game_id = g.id AND s.kind = 'human'
               ) AS human_names,
               (
                   SELECT string_agg(
                       COALESCE(u.full_name, '') || E'\x1e' || u.username,
                       E'\x1d' ORDER BY s.seat_key
                   )
                   FROM game_seats AS s
                   JOIN users AS u ON u.id = s.user_id
                   WHERE s.game_id = g.id AND s.kind = 'human'
               ) AS human_roster,
               EXISTS (
                   SELECT 1 FROM watchers AS w WHERE w.game_id = g.id AND w.user_id = $1
               ) AS watching
        FROM games AS g
        JOIN users AS cu ON cu.id = g.user_id
        LEFT JOIN users AS ou ON ou.id = g.opponent_id
        WHERE g.mode IN ('online', 'vs_computer')
          AND g.status IN ('waiting', 'active')
        ORDER BY CASE WHEN g.audience = 'open' THEN 0 ELSE 1 END, g.updated_at DESC, g.id DESC
        LIMIT 80
        """,
        user_id,
    )


async def list_open_tables(conn: asyncpg.Connection) -> list[asyncpg.Record]:
    return await conn.fetch(
        """
        SELECT g.id, g.game_type, g.mode, g.status, g.updated_at,
               shown_name(cu.full_name, cu.username) AS creator_name,
               shown_name(ou.full_name, ou.username) AS opponent_name
        FROM games AS g
        JOIN users AS cu ON cu.id = g.user_id
        LEFT JOIN users AS ou ON ou.id = g.opponent_id
        WHERE g.mode IN ('online', 'vs_computer')
          AND g.audience = 'open'
          AND g.status IN ('waiting', 'active')
        ORDER BY g.updated_at DESC, g.id DESC
        LIMIT 30
        """
    )


async def list_watchers(conn: asyncpg.Connection, game_id: uuid.UUID) -> list[asyncpg.Record]:
    await conn.execute(
        """
        DELETE FROM watchers
        WHERE seen_at <= now() - make_interval(secs => $1)
        """,
        WATCH_FRESH_SECONDS,
    )
    return await conn.fetch(
        """
        SELECT w.user_id,
               u.username,
               u.avatar,
               shown_name(u.full_name, u.username) AS name
        FROM watchers AS w
        JOIN users AS u ON u.id = w.user_id
        WHERE w.game_id = $1
          AND w.seen_at > now() - make_interval(secs => $2)
        ORDER BY w.created_at, u.username
        """,
        game_id,
        WATCH_FRESH_SECONDS,
    )


async def add_watcher(conn: asyncpg.Connection, game_id: uuid.UUID, user_id: uuid.UUID) -> None:
    await conn.execute(
        """
        INSERT INTO watchers (game_id, user_id, seen_at)
        VALUES ($1, $2, now())
        ON CONFLICT (game_id, user_id) DO UPDATE
        SET seen_at = now()
        """,
        game_id,
        user_id,
    )


async def drop_watcher(conn: asyncpg.Connection, game_id: uuid.UUID, user_id: uuid.UUID) -> None:
    await conn.execute(
        "DELETE FROM watchers WHERE game_id = $1 AND user_id = $2",
        game_id,
        user_id,
    )


async def get_rematch(conn: asyncpg.Connection, game_id: uuid.UUID) -> asyncpg.Record | None:
    return await conn.fetchrow(
        """
        SELECT offered_by, status, new_game_id
        FROM rematch_offers
        WHERE game_id = $1
        """,
        game_id,
    )


async def lock_rematch(conn: asyncpg.Connection, game_id: uuid.UUID) -> asyncpg.Record | None:
    return await conn.fetchrow(
        """
        SELECT offered_by, status, new_game_id
        FROM rematch_offers
        WHERE game_id = $1
        FOR UPDATE
        """,
        game_id,
    )


async def place_rematch(conn: asyncpg.Connection, game_id: uuid.UUID, user_id: uuid.UUID) -> None:
    await conn.execute(
        """
        INSERT INTO rematch_offers (game_id, offered_by, status)
        VALUES ($1, $2, 'pending')
        ON CONFLICT (game_id) DO UPDATE
        SET offered_by = EXCLUDED.offered_by,
            status = 'pending',
            new_game_id = NULL,
            created_at = now()
        WHERE rematch_offers.status <> 'accepted'
        """,
        game_id,
        user_id,
    )


async def accept_rematch(conn: asyncpg.Connection, game_id: uuid.UUID, new_game_id: uuid.UUID) -> None:
    await conn.execute(
        """
        UPDATE rematch_offers
        SET status = 'accepted', new_game_id = $2
        WHERE game_id = $1
        """,
        game_id,
        new_game_id,
    )


async def decline_rematch(conn: asyncpg.Connection, game_id: uuid.UUID) -> None:
    await conn.execute(
        "UPDATE rematch_offers SET status = 'declined' WHERE game_id = $1",
        game_id,
    )


async def touch(conn: asyncpg.Connection, game_id: uuid.UUID, user_id: uuid.UUID) -> None:
    await conn.execute(
        """
        UPDATE games
        SET updated_at = now()
        WHERE id = $1 AND (
            user_id = $2 OR opponent_id = $2
            OR EXISTS (SELECT 1 FROM game_seats AS s WHERE s.game_id = games.id AND s.user_id = $2)
        )
        """,
        game_id,
        user_id,
    )


async def insert_seats(
    conn: asyncpg.Connection,
    game_id: uuid.UUID,
    rows: list[tuple[str, str, uuid.UUID | None]],
) -> None:
    await conn.executemany(
        """
        INSERT INTO game_seats (game_id, seat_key, kind, user_id)
        VALUES ($1, $2, $3, $4)
        """,
        [(game_id, key, kind, user_id) for key, kind, user_id in rows],
    )


async def set_seat_kind(conn: asyncpg.Connection, game_id: uuid.UUID, seat_key: str, kind: str) -> None:
    await conn.execute(
        """
        UPDATE game_seats
        SET kind = $3
        WHERE game_id = $1 AND seat_key = $2
        """,
        game_id,
        seat_key,
        kind,
    )


async def list_seats(conn: asyncpg.Connection, game_id: uuid.UUID) -> list[asyncpg.Record]:
    return await conn.fetch(
        """
        SELECT s.seat_key, s.kind, s.user_id,
               shown_name(u.full_name, u.username) AS username,
               u.username AS login, u.avatar
        FROM game_seats AS s
        LEFT JOIN users AS u ON u.id = s.user_id
        WHERE s.game_id = $1
        ORDER BY s.seat_key
        """,
        game_id,
    )


async def claim_seat(conn: asyncpg.Connection, game_id: uuid.UUID, user_id: uuid.UUID) -> str | None:
    row = await conn.fetchrow(
        """
        SELECT id, user_id, opponent_id, mode, status
        FROM games
        WHERE id = $1 AND status = 'waiting'
        FOR UPDATE
        """,
        game_id,
    )
    if row is None:
        return None
    if row["user_id"] == user_id:
        await drop_watcher(conn, game_id, user_id)
        return "self"
    seated = await conn.fetchval(
        "SELECT 1 FROM game_seats WHERE game_id = $1 AND user_id = $2",
        game_id,
        user_id,
    )
    if seated:
        await drop_watcher(conn, game_id, user_id)
        return "self"
    claimed = await conn.fetchrow(
        """
        UPDATE game_seats
        SET user_id = $2
        WHERE game_id = $1
          AND user_id IS NULL
          AND kind = 'human'
          AND seat_key = (
              SELECT seat_key FROM game_seats
              WHERE game_id = $1 AND kind = 'human' AND user_id IS NULL
              ORDER BY seat_key
              LIMIT 1
          )
        RETURNING seat_key
        """,
        game_id,
        user_id,
    )
    if claimed is not None:
        await drop_watcher(conn, game_id, user_id)
        return "multi"
    has_plan = await conn.fetchval("SELECT 1 FROM game_seats WHERE game_id = $1", game_id)
    if has_plan or row["mode"] != "online" or row["opponent_id"] is not None:
        return None
    updated = await conn.execute(
        """
        UPDATE games
        SET opponent_id = $2, updated_at = now()
        WHERE id = $1 AND opponent_id IS NULL AND user_id <> $2
        """,
        game_id,
        user_id,
    )
    if updated.endswith("1"):
        await drop_watcher(conn, game_id, user_id)
        return "legacy"
    return None


async def vacancies(conn: asyncpg.Connection, game_id: uuid.UUID) -> int:
    value = await conn.fetchval(
        """
        SELECT count(*) FROM game_seats
        WHERE game_id = $1 AND kind = 'human' AND user_id IS NULL
        """,
        game_id,
    )
    return int(value or 0)
