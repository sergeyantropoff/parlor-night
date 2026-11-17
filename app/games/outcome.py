"""Личный итог сидящего за столом: победа, поражение или ничья."""

from __future__ import annotations

import json
from typing import Any


def for_viewer(row: Any, user_id: object) -> str | None:
    result = str(row.get("result") or "")
    if not result:
        return None
    return personal_mark(
        str(row.get("game_type") or ""),
        result,
        _seat(row, user_id),
        position=_position(row.get("finish_position")),
    )


def personal_mark(
    game_type: str,
    result: str | None,
    seat: str | None,
    *,
    position: dict[str, Any] | None = None,
) -> str | None:
    if not result or not seat:
        return None
    if result.endswith("_win"):
        return "win" if result == f"{seat}_win" else "loss"
    if result != "draw":
        return None
    state = position or {}
    if game_type == "durak":
        return _durak_mark(seat, state)
    if game_type == "blackjack":
        return _stake_mark(seat, state)
    if game_type == "poker":
        return _poker_mark(seat, state)
    if game_type == "preferans":
        return _preferans_mark(seat, state)
    return "draw"


def _seat(row: Any, user_id: object) -> str | None:
    seated = str(row.get("seat_key") or "")
    if seated:
        return seated
    side = str(row.get("player_side") or "")
    if str(row.get("user_id") or "") == str(user_id):
        return side or None
    opponent = row.get("opponent_id")
    if opponent and str(opponent) == str(user_id) and side in {"white", "black"}:
        return "black" if side == "white" else "white"
    return None


def _position(value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str) or not value:
        return {}
    try:
        loaded = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _durak_mark(seat: str, state: dict[str, Any]) -> str:
    loser = str(state.get("loser") or "")
    if not loser:
        return "draw"
    return "loss" if seat == loser else "win"


def _amount(bag: object, seat: str) -> int | None:
    if not isinstance(bag, dict) or seat not in bag:
        return None
    try:
        return int(bag[seat])
    except (TypeError, ValueError):
        return None


def _stake_mark(seat: str, state: dict[str, Any]) -> str:
    bet = _amount(state.get("committed"), seat)
    back = _amount(state.get("payout"), seat)
    if bet is None and back is None:
        return "draw"
    profit = (back or 0) - (bet or 0)
    if profit > 0:
        return "win"
    if profit < 0:
        return "loss"
    return "draw"


def _poker_mark(seat: str, state: dict[str, Any]) -> str:
    paid = _amount(state.get("payout"), seat)
    if paid is None:
        return "draw"
    return "draw" if paid > 0 else "loss"


def _preferans_mark(seat: str, state: dict[str, Any]) -> str:
    from app.cards.preferans import _balance

    order = [str(item) for item in state.get("order") or []]
    if seat not in order or "bullet" not in state:
        return "draw"
    try:
        scores = {item: _balance(state, item) for item in order}
    except (TypeError, ValueError, KeyError):
        return "draw"
    best = max(scores.values())
    leaders = [item for item, score in scores.items() if score == best]
    if len(leaders) == len(order) or seat in leaders:
        return "draw"
    return "loss"
