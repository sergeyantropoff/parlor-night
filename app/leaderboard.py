"""Общий зачёт гостей: победы, процент, партии и фишки."""

from __future__ import annotations

import asyncpg


def wins_word(count: int) -> str:
    tail = count % 100
    if 11 <= tail <= 14:
        return "побед"
    last = count % 10
    if last == 1:
        return "победа"
    if last in {2, 3, 4}:
        return "победы"
    return "побед"


def rank(guests: list[dict[str, object]]) -> list[dict[str, object]]:
    ranked: list[dict[str, object]] = []
    for person in guests:
        finished = int(person["finished"] or 0)
        wins = int(person["wins"] or 0)
        ranked.append(
            {
                **person,
                "wins": wins,
                "finished": finished,
                "games": int(person["games"] or 0),
                "balance": int(person["balance"] or 0),
                "rate": 0 if finished <= 0 else round(100 * wins / finished),
                "wins_word": wins_word(wins),
            }
        )
    ranked.sort(
        key=lambda item: (
            -int(item["wins"]),
            -int(item["rate"]),
            -int(item["games"]),
            -int(item["balance"]),
            str(item["username"]).casefold(),
        )
    )
    for index, person in enumerate(ranked, start=1):
        person["place"] = index
    return ranked


async def fetch_people(conn: asyncpg.Connection) -> list[dict[str, object]]:
    rows = await conn.fetch(
        """
        SELECT shown_name(u.full_name, u.username) AS username,
               u.username AS login, u.avatar,
               u.role, u.created_at, u.last_seen, u.last_ip, u.last_country,
               u.last_user_agent, u.born_on,
               shown_name(inv.full_name, inv.username) AS invited_by,
               inv.username AS invited_login,
               COALESCE(w.balance, 0) AS balance,
               (SELECT count(*) FROM games AS g WHERE g.user_id = u.id OR g.opponent_id = u.id) AS games,
               (SELECT count(*) FROM games AS g
                 WHERE (g.user_id = u.id OR g.opponent_id = u.id) AND g.status = 'finished') AS finished,
               (SELECT count(*) FROM games AS g
                 WHERE g.result IS NOT NULL AND (
                    (g.user_id = u.id AND (
                        (g.player_side = 'white' AND g.result = 'white_win')
                        OR (g.player_side = 'black' AND g.result = 'black_win')
                    ))
                    OR (g.opponent_id = u.id AND (
                        (g.player_side = 'white' AND g.result = 'black_win')
                        OR (g.player_side = 'black' AND g.result = 'white_win')
                    ))
                 )) AS wins
        FROM users AS u
        LEFT JOIN wallets AS w ON w.user_id = u.id
        LEFT JOIN users AS inv ON inv.id = u.referred_by
        ORDER BY games DESC, u.created_at
        """
    )
    return [dict(row) for row in rows]
