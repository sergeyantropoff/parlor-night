"""Фишки за победу, ничью и лимиты стола. Числа задаёт администратор."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

import asyncpg
from starlette.requests import Request

from app.errors import AppError

GAMES = (
    "chess",
    "checkers",
    "go",
    "domino",
    "nardy",
    "yahtzy",
    "uno",
    "durak",
    "bura",
    "poker",
    "blackjack",
    "preferans",
)
_TITLES = {
    "chess": "Шахматы",
    "checkers": "Русские шашки",
    "go": "Го",
    "domino": "Домино",
    "nardy": "Нарды",
    "yahtzy": "Яцзы",
    "uno": "Уно",
    "durak": "Дурак",
    "bura": "Бура",
    "poker": "Покер",
    "blackjack": "Блэкджек",
    "preferans": "Преферанс",
}


@dataclass(frozen=True, slots=True)
class Field:
    key: str
    label: str
    value: str


@dataclass(frozen=True, slots=True)
class Term:
    game: str
    title: str
    kind: str
    win: int
    draw: int
    share: int
    stack: int
    small: int
    big: int
    points: int
    bets: tuple[int, ...]
    prices: tuple[int, ...]
    loss: int = 0

    def fields(self) -> tuple[Field, ...]:
        if self.kind == "poker":
            return (
                Field("stack", "Стек на стол", str(self.stack)),
                Field("small", "Малый блайнд", str(self.small)),
                Field("big", "Большой блайнд", str(self.big)),
                Field("loss", "За проигрыш", str(self.loss)),
            )
        if self.kind == "blackjack":
            shown = ", ".join(str(item) for item in self.bets)
            return (
                Field("stack", "Стек раздачи", str(self.stack)),
                Field("bets", "Ставки через запятую", shown),
                Field("loss", "За проигрыш", str(self.loss)),
            )
        if self.kind == "preferans":
            shown = ", ".join(str(item) for item in self.prices)
            return (
                Field("points", "Очков в стеке", str(self.points)),
                Field("prices", "Цена очка через запятую", shown),
                Field("loss", "За проигрыш", str(self.loss)),
            )
        if self.kind == "durak":
            return (
                Field("win", "Победа вдвоём", str(self.win)),
                Field("share", "Остальным, если один остался с картами", str(self.share)),
                Field("draw", "Если вышли все", str(self.draw)),
                Field("loss", "За проигрыш", str(self.loss)),
            )
        return (
            Field("win", "За победу", str(self.win)),
            Field("draw", "За ничью", str(self.draw)),
            Field("loss", "За проигрыш", str(self.loss)),
        )


@dataclass(frozen=True, slots=True)
class Book:
    rows: tuple[Term, ...]

    def of(self, game: str) -> Term:
        for row in self.rows:
            if row.game == game:
                return row
        return _term(game)

    def __getattr__(self, name: str) -> Term:
        if name in GAMES:
            return self.of(name)
        raise AttributeError(name)

    def note(self, game: str) -> str:
        row = self.of(game)
        if game == "durak":
            return (
                f"При двоих победитель получает {row.win} фишек. "
                f"Если за столом больше и с картами остался один, остальные получают по {row.share}. "
                f"Если вышли все, каждый получает по {row.draw}. "
                f"Проигравший отдаёт {row.loss}."
            )
        if game == "yahtzy":
            return (
                f"Победитель получает {row.win} фишек, при ничьей лидеры — по {row.draw}. "
                f"Остальные отдают по {row.loss}."
            )
        if game == "poker":
            return (
                f"На стол садится стек в {row.stack} фишек. "
                f"Малый блайнд — {row.small}, большой — {row.big}. "
                f"Сверх ставки проигравший отдаёт {row.loss}."
            )
        if game == "blackjack":
            bets = ", ".join(str(item) for item in row.bets)
            return (
                f"Стек раздачи — {row.stack} фишек. Ставки: {bets}. "
                "Блэкджек платит три к двум, обычная победа — один к одному, ничья возвращает ставку. "
                f"Сверх ставки проигравший отдаёт {row.loss}."
            )
        if game == "preferans":
            prices = ", ".join(str(item) for item in row.prices)
            return (
                f"На стол садится стек в {row.points} очков. "
                f"Цена очка выбирается перед партией: {prices}. "
                f"Сверх ставки проигравший отдаёт {row.loss}."
            )
        return (
            f"Победителю гостиная начисляет {row.win} фишек, "
            f"при ничьей — по {row.draw} каждому из двоих. "
            f"Проигравший отдаёт {row.loss}."
        )


def _kind(game: str) -> str:
    if game in {"poker", "blackjack", "preferans", "durak"}:
        return game
    return "award"


def _term(
    game: str,
    *,
    win: int = 30,
    draw: int = 10,
    limits: dict[str, Any] | None = None,
) -> Term:
    bag = limits or {}
    bets = bag.get("bets") if isinstance(bag.get("bets"), list) else [10, 25, 50, 100]
    return Term(
        game=game,
        title=_TITLES.get(game, game),
        kind=_kind(game),
        win=win if game not in {"poker", "blackjack", "preferans"} else 0,
        draw=draw if game not in {"poker", "blackjack", "preferans"} else 0,
        share=int(bag.get("share") or 20) if game == "durak" else 0,
        stack=int(bag.get("stack") or (1000 if game == "poker" else 200)),
        small=int(bag.get("small") or 5),
        big=int(bag.get("big") or 10),
        points=int(bag.get("points") or 100),
        bets=tuple(int(item) for item in bets),
        prices=_price_list(bag.get("prices")),
        loss=_loss(game, bag),
    )


def defaults() -> Book:
    rows = []
    for game in GAMES:
        if game == "durak":
            rows.append(_term(game, limits={"share": 20}))
        elif game == "poker":
            rows.append(_term(game, win=0, draw=0, limits={"stack": 1000, "small": 5, "big": 10}))
        elif game == "blackjack":
            rows.append(_term(game, win=0, draw=0, limits={"stack": 200, "bets": [10, 25, 50, 100]}))
        elif game == "preferans":
            rows.append(_term(game, win=0, draw=0, limits={"points": 100, "prices": [1, 2, 5, 10]}))
        else:
            rows.append(_term(game))
    return Book(tuple(rows))


def _bounds(value: object, low: int, high: int, label: str) -> int:
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        raise AppError(422, "bad_terms", f"В поле «{label}» нужно целое число.") from None
    if not low <= number <= high:
        raise AppError(422, "bad_terms", f"«{label}» — от {low} до {high}.")
    return number


def _loss(game: str, bag: dict[str, Any]) -> int:
    if "loss" not in bag:
        return 0 if game in {"poker", "blackjack", "preferans"} else 10
    try:
        number = int(bag["loss"])
    except (TypeError, ValueError):
        return 10
    return number if 0 <= number <= 100_000 else 10


def _price_list(value: object) -> tuple[int, ...]:
    if not isinstance(value, list) or not value:
        return (1, 2, 5, 10)
    return tuple(int(item) for item in value)


def _bets(value: object, stack: int) -> tuple[int, ...]:
    parts = [item.strip() for item in str(value or "").replace(";", ",").split(",") if item.strip()]
    if not 1 <= len(parts) <= 6:
        raise AppError(422, "bad_terms", "У блэкджека от одной до шести ставок.")
    numbers = [_bounds(item, 1, stack, "Ставка") for item in parts]
    if len(set(numbers)) != len(numbers) or numbers != sorted(numbers):
        raise AppError(422, "bad_terms", "Ставки блэкджека пишут по возрастанию, без повторов.")
    return tuple(numbers)


def _prices(value: object) -> tuple[int, ...]:
    parts = [item.strip() for item in str(value or "").replace(";", ",").split(",") if item.strip()]
    if not 1 <= len(parts) <= 6:
        raise AppError(422, "bad_terms", "У преферанса от одной до шести цен очка.")
    numbers = [_bounds(item, 1, 10_000, "Цена очка") for item in parts]
    if len(set(numbers)) != len(numbers) or numbers != sorted(numbers):
        raise AppError(422, "bad_terms", "Цены очка пишут по возрастанию, без повторов.")
    return tuple(numbers)


def read_form(form: Any) -> Book:
    rows: list[Term] = []
    for game in GAMES:
        kind = _kind(game)
        title = _TITLES[game]
        if kind == "poker":
            stack = _bounds(form.get(f"{game}_stack"), 10, 1_000_000, "Стек на стол")
            small = _bounds(form.get(f"{game}_small"), 1, stack, "Малый блайнд")
            big = _bounds(form.get(f"{game}_big"), 1, stack, "Большой блайнд")
            if small >= big:
                raise AppError(422, "bad_terms", "Малый блайнд меньше большого.")
            loss = _bounds(form.get(f"{game}_loss"), 0, 100_000, "За проигрыш")
            rows.append(
                _term(game, win=0, draw=0, limits={"stack": stack, "small": small, "big": big, "loss": loss})
            )
        elif kind == "blackjack":
            stack = _bounds(form.get(f"{game}_stack"), 1, 1_000_000, "Стек раздачи")
            bets = _bets(form.get(f"{game}_bets"), stack)
            loss = _bounds(form.get(f"{game}_loss"), 0, 100_000, "За проигрыш")
            rows.append(_term(game, win=0, draw=0, limits={"stack": stack, "bets": list(bets), "loss": loss}))
        elif kind == "preferans":
            points = _bounds(form.get(f"{game}_points"), 1, 10_000, "Очков в стеке")
            prices = _prices(form.get(f"{game}_prices"))
            loss = _bounds(form.get(f"{game}_loss"), 0, 100_000, "За проигрыш")
            rows.append(
                _term(game, win=0, draw=0, limits={"points": points, "prices": list(prices), "loss": loss})
            )
        elif kind == "durak":
            win = _bounds(form.get(f"{game}_win"), 0, 100_000, "Победа вдвоём")
            share = _bounds(form.get(f"{game}_share"), 0, 100_000, "Остальным, если один остался с картами")
            draw = _bounds(form.get(f"{game}_draw"), 0, 100_000, "Если вышли все")
            loss = _bounds(form.get(f"{game}_loss"), 0, 100_000, "За проигрыш")
            rows.append(_term(game, win=win, draw=draw, limits={"share": share, "loss": loss}))
        else:
            win = _bounds(form.get(f"{game}_win"), 0, 100_000, f"{title}: за победу")
            draw = _bounds(form.get(f"{game}_draw"), 0, 100_000, f"{title}: за ничью")
            loss = _bounds(form.get(f"{game}_loss"), 0, 100_000, f"{title}: за проигрыш")
            rows.append(_term(game, win=win, draw=draw, limits={"loss": loss}))
    return Book(tuple(rows))


def _limits(row: Term) -> dict[str, Any]:
    if row.kind == "poker":
        return {"stack": row.stack, "small": row.small, "big": row.big, "loss": row.loss}
    if row.kind == "blackjack":
        return {"stack": row.stack, "bets": list(row.bets), "loss": row.loss}
    if row.kind == "preferans":
        return {"points": row.points, "prices": list(row.prices), "loss": row.loss}
    if row.kind == "durak":
        return {"share": row.share, "loss": row.loss}
    return {"loss": row.loss}


def _from_records(records: list[Any]) -> Book:
    found: dict[str, Term] = {}
    for record in records:
        game = str(record["game_type"])
        if game not in GAMES:
            continue
        raw = record["limits"]
        limits = json.loads(raw) if isinstance(raw, str) else dict(raw or {})
        found[game] = _term(game, win=int(record["win_chips"]), draw=int(record["draw_chips"]), limits=limits)
    base = defaults()
    return Book(tuple(found.get(row.game, row) for row in base.rows))


async def load_terms(conn: asyncpg.Connection) -> Book:
    records = await conn.fetch("SELECT game_type, win_chips, draw_chips, limits FROM game_terms")
    return _from_records(list(records))


async def save_terms(conn: asyncpg.Connection, book: Book) -> None:
    for row in book.rows:
        await conn.execute(
            """
            INSERT INTO game_terms (game_type, win_chips, draw_chips, limits)
            VALUES ($1, $2, $3, $4::jsonb)
            ON CONFLICT (game_type) DO UPDATE
            SET win_chips = EXCLUDED.win_chips,
                draw_chips = EXCLUDED.draw_chips,
                limits = EXCLUDED.limits
            """,
            row.game,
            row.win,
            row.draw,
            json.dumps(_limits(row)),
        )


def remember(app: Any, book: Book) -> None:
    app.state.game_terms = book
    app.state.game_terms_until = time.monotonic() + 5


async def current(request: Request) -> Book:
    state = request.app.state
    cached = getattr(state, "game_terms", None)
    until = float(getattr(state, "game_terms_until", 0.0))
    if isinstance(cached, Book) and time.monotonic() < until:
        return cached
    async with request.app.state.pool.acquire() as conn:
        book = await load_terms(conn)
    remember(request.app, book)
    return book
