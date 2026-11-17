"""Партия го: доска, пасы, подсчёт и повторяемые команды. Без базы."""

from __future__ import annotations

import json
from typing import Any

from app.go.rules import (
    BLACK,
    CODE,
    EMPTY,
    KOMI_HALF,
    RULES_ID,
    WHITE,
    GoRuleError,
    area,
    empty_board,
    format_half,
    group,
    legal_points,
    other,
    play_stone,
    point_name,
)


def new_match(size: int) -> dict[str, Any]:
    board = empty_board(size)
    return {
        "rules": RULES_ID,
        "size": size,
        "komi_half": KOMI_HALF,
        "board": board,
        "to_play": "black",
        "phase": "play",
        "passes": 0,
        "captures": {"black": 0, "white": 0},
        "seen": [board],
        "last": None,
        "dead": [],
        "score_version": 0,
        "agreed": {"black": None, "white": None},
        "resume_color": "black",
        "acks": [],
        "result": None,
        "reason": None,
        "margin_half": None,
    }


def dump_state(state: dict[str, Any]) -> str:
    return json.dumps(state, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def load_state(raw: str | dict[str, Any]) -> dict[str, Any]:
    data = json.loads(raw) if isinstance(raw, str) else dict(raw)
    size = int(data["size"])
    board = str(data["board"])
    if size not in {9, 13, 19} or len(board) != size * size:
        raise GoRuleError("Запись партии го повреждена.")
    if any(cell not in {EMPTY, BLACK, WHITE} for cell in board):
        raise GoRuleError("Запись партии го повреждена.")
    if str(data.get("rules")) != RULES_ID or int(data.get("komi_half") or 0) != KOMI_HALF:
        raise GoRuleError("Запись партии го повреждена.")
    return data


def same_bones(replayed: dict[str, Any], current: dict[str, Any]) -> None:
    """Доска, очередь, взятия и история суперко сходятся с журналом ходов."""
    if (
        replayed["board"] != current["board"]
        or replayed["to_play"] != current["to_play"]
        or replayed["captures"] != current["captures"]
        or replayed["seen"] != current["seen"]
    ):
        raise ValueError("запись партии го не сходится")


def replay(initial: str | dict[str, Any], payloads: list[dict[str, Any]]) -> dict[str, Any]:
    state = load_state(initial)
    for payload in payloads:
        kind = str(payload.get("kind") or "")
        if kind == "move":
            state = _move(state, int(payload["col"]), int(payload["row"]))
        elif kind == "pass":
            state = _pass(state)
    return state


def apply_action(
    state: dict[str, Any],
    action: str,
    seat: str | None,
    *,
    col: int | None = None,
    row: int | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if seat not in {"black", "white"}:
        raise GoRuleError("Наблюдатель не управляет партией.")
    if state.get("result"):
        raise GoRuleError("Партия уже завершена.")
    if action == "move":
        if state["phase"] != "play":
            raise GoRuleError("Сейчас идёт подсчёт, а не игра.")
        if seat != state["to_play"]:
            raise GoRuleError("Сейчас ход другой стороны.")
        if col is None or row is None:
            raise GoRuleError("Укажите пересечение.")
        nxt = _move(state, col, row)
        return nxt, {
            "notation": point_name(col, row, int(state["size"])),
            "payload": {"kind": "move", "col": col, "row": row, "color": seat},
            "result": None,
            "reason": None,
        }
    if action == "pass":
        if state["phase"] != "play":
            raise GoRuleError("Сейчас идёт подсчёт, а не игра.")
        if seat != state["to_play"]:
            raise GoRuleError("Сейчас ход другой стороны.")
        nxt = _pass(state)
        return nxt, {
            "notation": "Пас",
            "payload": {"kind": "pass", "color": seat},
            "result": None,
            "reason": None,
        }
    if action == "resign":
        if state["phase"] not in {"play", "score"}:
            raise GoRuleError("Сейчас сдаться нельзя.")
        winner = other(seat)
        nxt = _copy(state)
        nxt["result"] = f"{winner}_win"
        nxt["reason"] = "resign"
        nxt["margin_half"] = None
        return nxt, {"notation": None, "payload": None, "result": nxt["result"], "reason": "resign"}
    if action == "mark":
        return _mark(state, seat, col, row), {
            "notation": None,
            "payload": None,
            "result": None,
            "reason": None,
        }
    if action == "agree":
        return _agree(state, seat)
    if action == "resume":
        return _resume(state), {"notation": None, "payload": None, "result": None, "reason": None}
    raise GoRuleError("Неизвестное действие.")


def tally(state: dict[str, Any]) -> dict[str, object] | None:
    if state["phase"] != "score" and state.get("reason") != "score":
        return None
    dead = {(int(col), int(row)) for col, row in state.get("dead") or []}
    scored = area(str(state["board"]), int(state["size"]), dead, komi_half=KOMI_HALF)
    version = int(state.get("score_version") or 0)
    agreed = state.get("agreed") or {}
    scored["black_agreed"] = agreed.get("black") == version
    scored["white_agreed"] = agreed.get("white") == version
    scored["black_captures"] = int(state["captures"]["black"])
    scored["white_captures"] = int(state["captures"]["white"])
    return scored


def _copy(state: dict[str, Any]) -> dict[str, Any]:
    return json.loads(dump_state(state))


def _move(state: dict[str, Any], col: int, row: int) -> dict[str, Any]:
    color = CODE[str(state["to_play"])]
    board, taken = play_stone(
        str(state["board"]),
        int(state["size"]),
        set(state["seen"]),
        color,
        col,
        row,
    )
    nxt = _copy(state)
    captures = dict(nxt["captures"])
    captures[str(state["to_play"])] = int(captures[str(state["to_play"])]) + taken
    nxt["board"] = board
    nxt["captures"] = captures
    nxt["seen"] = [*list(state["seen"]), board]
    nxt["to_play"] = other(str(state["to_play"]))
    nxt["passes"] = 0
    nxt["phase"] = "play"
    nxt["last"] = {"kind": "move", "col": col, "row": row, "color": str(state["to_play"])}
    nxt["dead"] = []
    nxt["score_version"] = 0
    nxt["agreed"] = {"black": None, "white": None}
    nxt["resume_color"] = nxt["to_play"]
    return nxt


def _pass(state: dict[str, Any]) -> dict[str, Any]:
    nxt = _copy(state)
    color = str(state["to_play"])
    nxt["to_play"] = other(color)
    nxt["passes"] = int(state["passes"]) + 1
    nxt["last"] = {"kind": "pass", "color": color}
    nxt["resume_color"] = nxt["to_play"]
    if nxt["passes"] >= 2:
        nxt["phase"] = "score"
        nxt["dead"] = []
        nxt["score_version"] = 1
        nxt["agreed"] = {"black": None, "white": None}
    return nxt


def _mark(
    state: dict[str, Any],
    seat: str,
    col: int | None,
    row: int | None,
) -> dict[str, Any]:
    del seat
    if state["phase"] != "score":
        raise GoRuleError("Сейчас не подсчёт.")
    if col is None or row is None:
        raise GoRuleError("Укажите камень.")
    size = int(state["size"])
    if not (0 <= col < size and 0 <= row < size):
        raise GoRuleError("Точка вне доски.")
    board = str(state["board"])
    if board[row * size + col] == EMPTY:
        raise GoRuleError("Здесь нет камня.")
    stones, _liberties = group(board, size, col, row)
    dead = {(int(item[0]), int(item[1])) for item in state.get("dead") or []}
    if stones <= dead:
        dead -= set(stones)
    else:
        dead |= set(stones)
    nxt = _copy(state)
    nxt["dead"] = sorted([col_row[0], col_row[1]] for col_row in dead)
    nxt["score_version"] = int(state["score_version"]) + 1
    nxt["agreed"] = {"black": None, "white": None}
    return nxt


def _agree(state: dict[str, Any], seat: str) -> tuple[dict[str, Any], dict[str, Any]]:
    if state["phase"] != "score":
        raise GoRuleError("Сначала нужны два паса.")
    version = int(state["score_version"])
    nxt = _copy(state)
    agreed = {"black": nxt["agreed"].get("black"), "white": nxt["agreed"].get("white")}
    agreed[seat] = version
    nxt["agreed"] = agreed
    empty: dict[str, Any] = {"notation": None, "payload": None, "result": None, "reason": None}
    if agreed.get("black") != version or agreed.get("white") != version:
        return nxt, empty
    scored = area(
        str(state["board"]),
        int(state["size"]),
        {(int(col), int(row)) for col, row in state.get("dead") or []},
        komi_half=KOMI_HALF,
    )
    winner = str(scored["winner"])
    if winner not in {"black", "white"}:
        raise GoRuleError("При этих отметках очки равны. Продолжите игру.")
    nxt["result"] = f"{winner}_win"
    nxt["reason"] = "score"
    nxt["margin_half"] = int(scored["margin_half"])
    return nxt, {
        "notation": None,
        "payload": None,
        "result": nxt["result"],
        "reason": "score",
    }


def _resume(state: dict[str, Any]) -> dict[str, Any]:
    if state["phase"] != "score":
        raise GoRuleError("Партия и так идёт.")
    nxt = _copy(state)
    nxt["phase"] = "play"
    nxt["passes"] = 0
    nxt["dead"] = []
    nxt["score_version"] = 0
    nxt["agreed"] = {"black": None, "white": None}
    nxt["to_play"] = str(state["resume_color"])
    return nxt


def score_view(state: dict[str, Any]) -> dict[str, object] | None:
    scored = tally(state)
    if scored is None:
        return None
    owners = scored.pop("owners")
    territory = [
        {"col": col, "row": row, "owner": owner}
        for (col, row), owner in sorted(owners.items())
        if owner in {"black", "white"}
    ]
    scored["territory"] = territory
    scored["komi"] = format_half(KOMI_HALF)
    return scored


def points_for(state: dict[str, Any], seat: str | None) -> list[list[int]]:
    if state["phase"] != "play" or state.get("result") or seat != state["to_play"]:
        return []
    return legal_points(str(state["board"]), int(state["size"]), set(state["seen"]), CODE[str(state["to_play"])])
