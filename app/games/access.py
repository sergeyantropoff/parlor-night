"""Кто может ходить и отменять ход. Дополнительный разбор в запись партии не входит."""

from __future__ import annotations


def is_participant(user_id: str, creator_id: str, opponent_id: str | None) -> bool:
    if user_id == creator_id:
        return True
    return opponent_id is not None and user_id == opponent_id


def other_side(side: str) -> str:
    return "black" if side == "white" else "white"


def seat_of(
    user_id: str,
    creator_id: str,
    opponent_id: str | None,
    creator_side: str,
) -> str | None:
    if user_id == creator_id:
        return creator_side
    if opponent_id is not None and user_id == opponent_id:
        return other_side(creator_side)
    return None


def can_hint(role: str) -> bool:
    return role == "admin"


def user_may_move(mode: str, status: str, seat: str | None, side_to_move: str) -> bool:
    if status != "active" or seat is None:
        return False
    if mode in {"free", "analysis", "lesson"}:
        return True
    return seat == side_to_move


def durak_can_step_aside(seats: list[dict[str, object]], user_id: str) -> bool:
    """Человек может отдать место компьютеру и смотреть, как доигрывают остальные.

    Нужны хотя бы два компьютера и ни одного другого человека. Одному компьютеру
    доигрывать не с кем, а живого соперника так не оставляем.
    """
    mine = False
    computers = 0
    strangers = 0
    for item in seats:
        owner = str(item.get("user_id") or "")
        kind = str(item.get("kind") or "")
        if owner and owner == user_id:
            if kind == "computer":
                return False
            mine = True
            continue
        if kind == "computer":
            computers += 1
        else:
            strangers += 1
    return mine and computers >= 2 and strangers == 0


def user_may_request_engine(
    mode: str,
    status: str,
    seat: str | None,
    side_to_move: str,
    *,
    computer_turn: bool = False,
) -> bool:
    if computer_turn and status == "active" and seat is not None:
        return True
    if status != "active" or seat is None or mode == "online":
        return False
    if mode == "vs_computer":
        return seat != side_to_move
    return mode in {"free", "analysis", "lesson"}


def undo_count(
    mode: str,
    status: str,
    move_count: int,
    side_to_move: str,
    seat: str | None,
) -> int:
    if move_count <= 0 or seat is None or status == "waiting":
        return 0
    last_mover = other_side(side_to_move)
    if mode == "online":
        if status != "active":
            return 0
        return 1 if last_mover == seat else 0
    if status not in {"active", "finished"}:
        return 0
    if mode == "vs_computer":
        computer = other_side(seat)
        if last_mover == computer:
            return 2 if move_count >= 2 else 1
        return 1
    return 1


def black_at_bottom(seat: str | None, flipped: bool) -> bool:
    base = seat == "black"
    return base ^ flipped
