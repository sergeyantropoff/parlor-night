"""Сводка партий одного гостя для страницы профиля."""

from __future__ import annotations

import calendar
import math
from datetime import UTC, datetime, timedelta
from typing import Any

from app.clock import current_zone
from app.games.outcome import for_viewer

TITLES = {
    "chess": "Шахматы",
    "checkers": "Шашки",
    "go": "Го",
    "uno": "Уно",
    "poker": "Покер",
    "domino": "Домино",
    "nardy": "Нарды",
    "yahtzy": "Яцзы",
    "bura": "Бура",
}


def tally(rows: list[dict[str, Any]], user_id: object, *, now: datetime | None = None) -> dict[str, Any]:
    moment = now or datetime.now(UTC)
    played = wins = losses = draws = 0
    by_game = {key: {"played": 0, "wins": 0, "losses": 0, "draws": 0} for key in TITLES}
    weeks = _months(moment, 3)
    for row in rows:
        kind = str(row.get("game_type") or "")
        bucket = by_game.get(kind)
        mark = _mark(row, user_id)
        if mark is None or bucket is None:
            continue
        played += 1
        bucket["played"] += 1
        if mark == "win":
            wins += 1
            bucket["wins"] += 1
        elif mark == "draw":
            draws += 1
            bucket["draws"] += 1
        else:
            losses += 1
            bucket["losses"] += 1
        week = _week_start(_aware(row.get("updated_at")))
        if week in weeks:
            weeks[week]["played"] += 1
            if mark == "win":
                weeks[week]["wins"] += 1
    peak = max((item["played"] for item in by_game.values()), default=0) or 1
    games = [
        {
            "key": key,
            "title": title,
            **by_game[key],
            "width": round(by_game[key]["played"] / peak * 100, 1),
        }
        for key, title in TITLES.items()
    ]
    return {
        "played": played,
        "wins": wins,
        "losses": losses,
        "draws": draws,
        "rate": 0 if played == 0 else round(wins / played * 100),
        "games": games,
        "weeks": list(weeks.values()),
        "line": _line(list(weeks.values())),
        "donut": _donut(wins, losses, draws),
    }


def _mark(row: dict[str, Any], user_id: object) -> str | None:
    result = str(row.get("result") or "")
    if not result:
        return None
    marked = dict(row)
    if not marked.get("seat_key"):
        side = str(row.get("player_side") or "white")
        if str(row.get("user_id")) == str(user_id):
            marked["seat_key"] = side
        else:
            marked["seat_key"] = "black" if side == "white" else "white"
    return for_viewer(marked, user_id) or ("draw" if result == "draw" else "loss")


def _months(moment: datetime, count: int) -> dict[datetime, dict[str, Any]]:
    names = ("янв", "фев", "мар", "апр", "мая", "июн", "июл", "авг", "сен", "окт", "ноя", "дек")
    local = _aware(moment).astimezone(current_zone())
    first = _week_start(_shift_months(local, -count))
    last = _week_start(local)
    bucket: dict[datetime, dict[str, Any]] = {}
    day = first
    while day <= last:
        bucket[day] = {
            "label": f"{day.day} {names[day.month - 1]}",
            "played": 0,
            "wins": 0,
        }
        day += timedelta(weeks=1)
    return bucket


def _shift_months(moment: datetime, count: int) -> datetime:
    index = moment.month - 1 + count
    year = moment.year + index // 12
    month = index % 12 + 1
    day = min(moment.day, calendar.monthrange(year, month)[1])
    return datetime(year, month, day, tzinfo=UTC)


def _week_start(moment: datetime) -> datetime:
    local = _aware(moment).astimezone(current_zone())
    monday = local.date() - timedelta(days=local.weekday())
    return datetime(monday.year, monday.month, monday.day, tzinfo=current_zone())


def _aware(value: object) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    return datetime.now(UTC)


def _line(weeks: list[dict[str, Any]]) -> dict[str, Any]:
    peak = max((int(item["played"]) for item in weeks), default=0) or 1
    count = max(len(weeks), 1)
    width = 640.0

    def place(index: int, value: int) -> tuple[float, float]:
        x = width * (index + 0.5) / count
        y = 124.0 - (value / peak) * 100.0
        return round(x, 1), round(y, 1)

    played: list[str] = []
    wins: list[str] = []
    dots: list[dict[str, Any]] = []
    for index, item in enumerate(weeks):
        px, py = place(index, int(item["played"]))
        wx, wy = place(index, int(item["wins"]))
        played.append(f"{px},{py}")
        wins.append(f"{wx},{wy}")
        dots.append(
            {
                "x": px,
                "y": py,
                "label": item["label"],
                "played": item["played"],
                "wins": item["wins"],
            }
        )
    return {"played": " ".join(played), "wins": " ".join(wins), "dots": dots, "peak": peak}


def _donut(wins: int, losses: int, draws: int) -> dict[str, float]:
    total = wins + losses + draws
    circle = round(2 * math.pi * 42, 2)
    if total == 0:
        return {"circle": circle, "win": 0, "loss": 0, "draw": 0, "rest": circle}
    win = round(circle * wins / total, 2)
    loss = round(circle * losses / total, 2)
    draw = round(max(0, circle - win - loss), 2)
    return {"circle": circle, "win": win, "loss": loss, "draw": draw, "rest": 0}
