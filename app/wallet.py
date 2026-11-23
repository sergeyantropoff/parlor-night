"""Игровые фишки. На деньги здесь не играют."""

from __future__ import annotations

import uuid
from datetime import date, datetime

import asyncpg

from app.errors import AppError


async def ensure(conn: asyncpg.Connection, user_id: uuid.UUID) -> None:
    await conn.execute(
        "INSERT INTO wallets (user_id) VALUES ($1) ON CONFLICT (user_id) DO NOTHING",
        user_id,
    )


async def balance(conn: asyncpg.Connection, user_id: uuid.UUID) -> int:
    await ensure(conn, user_id)
    value = await conn.fetchval("SELECT balance FROM wallets WHERE user_id = $1", user_id)
    return int(value or 0)


async def charge(
    conn: asyncpg.Connection,
    user_id: uuid.UUID,
    amount: int,
    *,
    reason: str,
    game_id: uuid.UUID | None,
) -> None:
    if amount <= 0 or user_id is None:
        return
    await ensure(conn, user_id)
    row = await conn.fetchrow(
        """
        UPDATE wallets
        SET balance = balance - $2, updated_at = now()
        WHERE user_id = $1 AND balance >= $2
        RETURNING balance
        """,
        user_id,
        amount,
    )
    if row is None:
        raise AppError(409, "no_chips", "Не хватает игровых фишек.")
    await conn.execute(
        "INSERT INTO ledger (user_id, amount, reason, game_id) VALUES ($1, $2, $3, $4)",
        user_id,
        -amount,
        reason,
        game_id,
    )


async def take(
    conn: asyncpg.Connection,
    user_id: uuid.UUID | None,
    amount: int,
    *,
    reason: str,
    game_id: uuid.UUID | None,
) -> int:
    """Списывает фишки, но не больше остатка и не срывает уже законченную партию."""
    if amount <= 0 or user_id is None:
        return 0
    await ensure(conn, user_id)
    row = await conn.fetchrow(
        "SELECT balance FROM wallets WHERE user_id = $1 FOR UPDATE",
        user_id,
    )
    have = int(row["balance"] or 0) if row else 0
    taken = min(have, amount)
    if taken <= 0:
        return 0
    await conn.execute(
        "UPDATE wallets SET balance = balance - $2, updated_at = now() WHERE user_id = $1",
        user_id,
        taken,
    )
    await conn.execute(
        "INSERT INTO ledger (user_id, amount, reason, game_id) VALUES ($1, $2, $3, $4)",
        user_id,
        -taken,
        reason,
        game_id,
    )
    return taken


async def credit(
    conn: asyncpg.Connection,
    user_id: uuid.UUID,
    amount: int,
    *,
    reason: str,
    game_id: uuid.UUID | None,
) -> None:
    if amount <= 0 or user_id is None:
        return
    await ensure(conn, user_id)
    await conn.execute(
        "UPDATE wallets SET balance = balance + $2, updated_at = now() WHERE user_id = $1",
        user_id,
        amount,
    )
    await conn.execute(
        "INSERT INTO ledger (user_id, amount, reason, game_id) VALUES ($1, $2, $3, $4)",
        user_id,
        amount,
        reason,
        game_id,
    )


async def set_balance(conn: asyncpg.Connection, user_id: uuid.UUID, amount: int) -> None:
    await ensure(conn, user_id)
    current = await balance(conn, user_id)
    delta = amount - current
    if delta == 0:
        return
    await conn.execute(
        "UPDATE wallets SET balance = $2, updated_at = now() WHERE user_id = $1",
        user_id,
        amount,
    )
    await conn.execute(
        "INSERT INTO ledger (user_id, amount, reason, game_id) VALUES ($1, $2, 'admin', NULL)",
        user_id,
        delta,
    )


async def already_paid(conn: asyncpg.Connection, game_id: uuid.UUID, reason: str) -> bool:
    found = await conn.fetchval(
        "SELECT 1 FROM ledger WHERE game_id = $1 AND reason = $2 LIMIT 1",
        game_id,
        reason,
    )
    return found is not None


def seat_user(
    game: dict[str, object],
    seat: str,
    seats: list[dict[str, object]] | None = None,
) -> uuid.UUID | None:
    for item in seats or []:
        if str(item.get("seat_key")) != seat:
            continue
        chosen = item.get("user_id")
        if chosen is None:
            return None
        return chosen if isinstance(chosen, uuid.UUID) else uuid.UUID(str(chosen))
    creator = game.get("user_id")
    opponent = game.get("opponent_id")
    side = str(game.get("player_side") or "white")
    chosen = creator if seat == side else opponent
    if chosen is None:
        return None
    return chosen if isinstance(chosen, uuid.UUID) else uuid.UUID(str(chosen))


_MONTHS = (
    "января",
    "февраля",
    "марта",
    "апреля",
    "мая",
    "июня",
    "июля",
    "августа",
    "сентября",
    "октября",
    "ноября",
    "декабря",
)


def age_years(born: date, today: date | None = None) -> int:
    current = today or date.today()
    return current.year - born.year - ((current.month, current.day) < (born.month, born.day))


def years_phrase(years: int) -> str:
    tail = years % 10
    hundred = years % 100
    if tail == 1 and hundred != 11:
        word = "год"
    elif 2 <= tail <= 4 and not 12 <= hundred <= 14:
        word = "года"
    else:
        word = "лет"
    return f"{years} {word}"


def format_born(born: date) -> str:
    return f"{born.day} {_MONTHS[born.month - 1]} {born.year}"


def born_from_parts(day: str, month: str, year: str, today: date | None = None) -> date | None:
    if not day and not month and not year:
        return None
    if not (day and month and year):
        raise ValueError("Укажите день, месяц и год рождения.")
    try:
        born = date(int(year), int(month), int(day))
    except ValueError as exc:
        raise ValueError("Такой даты не бывает.") from exc
    current = today or date.today()
    if born > current or born.year < 1900:
        raise ValueError("Проверьте дату рождения.")
    return born


def parse_born_text(value: str, today: date | None = None) -> date:
    text = value.strip()
    born: date | None = None
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y"):
        try:
            born = datetime.strptime(text, fmt).date()
        except ValueError:
            continue
        else:
            break
    current = today or date.today()
    if born is None or born > current or born.year < 1900:
        raise ValueError("Проверьте дату рождения.")
    return born


_ADULT_TITLES = {"poker": "Покер", "blackjack": "Блэкджек", "preferans": "Преферанс"}


def adult_title(game_type: str) -> str:
    return _ADULT_TITLES.get(game_type, "Эта игра")


def adult_message(born: date | None, game_type: str = "poker", today: date | None = None) -> str | None:
    title = _ADULT_TITLES.get(game_type)
    if title is None or (isinstance(born, date) and age_years(born, today) >= 18):
        return None
    return f"{title} доступен с 18 лет. Сесть за стол и смотреть партию нельзя."


async def adult_denial(
    conn: asyncpg.Connection,
    user_id: uuid.UUID,
    game_type: str = "poker",
    today: date | None = None,
) -> str | None:
    born = await conn.fetchval("SELECT born_on FROM users WHERE id = $1", user_id)
    return adult_message(born if isinstance(born, date) else None, game_type, today)


async def poker_denial(conn: asyncpg.Connection, user_id: uuid.UUID, today: date | None = None) -> str | None:
    return await adult_denial(conn, user_id, "poker", today)


async def is_adult(conn: asyncpg.Connection, user_id: uuid.UUID, today: date | None = None) -> bool:
    return await poker_denial(conn, user_id, today) is None
