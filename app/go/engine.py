"""Поиск хода в го.

Собственный движок: оценка площади, перебор ближайших пунктов и
альфа-бета с ограничением времени. Это учебный поиск. Новичок путает
близкие ходы, мастер смотрит шире и глубже. На уровень профессиональной
программы го он не претендует.
"""

from __future__ import annotations

import random
import time
from typing import Any

from app.errors import AnalysisIncomplete
from app.go.rules import (
    BLACK,
    CODE,
    EMPTY,
    WHITE,
    GoRuleError,
    area,
    group,
    neighbors,
    other,
    play_stone,
)

# Глубина, потолок времени и допуск слабого уровня.
# Очко площади стоит 20, поэтому допуск 36 путает ход, но не отдаёт группу.
LEVELS: dict[int, tuple[int, int, int]] = {
    1: (1, 250, 36),
    2: (2, 700, 0),
    3: (2, 1200, 0),
    4: (3, 2200, 0),
    5: (3, 4000, 0),
}


class _Timeout(Exception):
    pass


def computer_pending(state: dict[str, Any], color: str) -> bool:
    """Компьютер ещё должен поставить камень, пасовать или ответить в подсчёте."""

    if color not in {"black", "white"} or state.get("result"):
        return False
    phase = str(state.get("phase") or "play")
    if phase == "play":
        return str(state.get("to_play")) == color
    if phase != "score":
        return False
    version = int(state.get("score_version") or 0)
    agreed = state.get("agreed") or {}
    if agreed.get(color) == version:
        return False
    human = other(color)
    if agreed.get(human) == version:
        return True
    dead = _dead_set(state)
    return not dead and bool(suggested_dead(state))


def suggested_dead(state: dict[str, Any]) -> set[tuple[int, int]]:
    """Группы без глаз и не больше чем с одной свободой. Остальное не трогаем."""

    board = str(state["board"])
    size = int(state["size"])
    seen: set[tuple[int, int]] = set()
    dead: set[tuple[int, int]] = set()
    for row in range(size):
        for col in range(size):
            if board[row * size + col] == EMPTY or (col, row) in seen:
                continue
            stones, libs = group(board, size, col, row)
            seen.update(stones)
            if eye_count(board, size, stones) >= 1 or len(libs) > 1:
                continue
            dead.update(stones)
    return dead


def eye_count(board: str, size: int, stones: frozenset[tuple[int, int]]) -> int:
    sample = next(iter(stones))
    color = board[sample[1] * size + sample[0]]
    liberties: set[tuple[int, int]] = set()
    for col, row in stones:
        for near in neighbors(size, col, row):
            if board[near[1] * size + near[0]] == EMPTY:
                liberties.add(near)
    eyes = {
        point
        for point in liberties
        if all(board[near[1] * size + near[0]] == color for near in neighbors(size, point[0], point[1]))
    }
    remaining = set(eyes)
    count = 0
    while remaining:
        count += 1
        stack = [remaining.pop()]
        while stack:
            col, row = stack.pop()
            for near in neighbors(size, col, row):
                if near in remaining:
                    remaining.remove(near)
                    stack.append(near)
    return count


def plan(state: dict[str, Any], color: str, level: int, time_ms: int) -> dict[str, Any]:
    if str(state.get("phase")) == "score":
        return {"actions": _score_actions(state, color), "depth": 0, "nodes": 0}
    chosen = choose_move(state, level, time_ms)
    return {
        "actions": [chosen["action"]],
        "depth": chosen["depth"],
        "nodes": chosen["nodes"],
    }


def search_job(state: dict[str, Any], color: str, level: int, time_ms: int) -> dict[str, Any]:
    """Точка входа процесса-поиска. Аргументы только простые и сериализуемые."""

    return plan(state, color, level, time_ms)


def choose_move(state: dict[str, Any], level: int, time_ms: int) -> dict[str, Any]:
    if str(state.get("phase")) != "play":
        raise AnalysisIncomplete("Движок го выбирает ход только во время игры.")
    depth, budget, slack = LEVELS[max(1, min(5, level))]
    size = int(state["size"])
    if size == 9 and level >= 4:
        depth += 1
    think = max(50, min(int(time_ms), budget))
    board = str(state["board"])
    seen = set(state.get("seen") or [board])
    color = CODE[str(state["to_play"])]
    passes = int(state.get("passes") or 0)
    cap, radius = _width(level, size)
    started = time.perf_counter()
    deadline = started + think / 1000
    nodes = [0]
    cache: dict[tuple[str, str], int] = {}
    ranked = _rank_root(board, size, seen, color, passes, cap, radius, cache)
    if not ranked:
        raise AnalysisIncomplete("Движок го не нашёл допустимый ход.")
    chosen = ranked[0][1]
    reached = 1
    if slack > 0:
        best = ranked[0][0]
        window = [action for score, action in ranked if best - score <= slack]
        chosen = random.choice(window)
    elif depth > 1:
        ordered = [action for _score, action in ranked]
        for current_depth in range(1, depth + 1):
            if current_depth > 1 and time.perf_counter() >= deadline:
                break
            try:
                found = _search_root(
                    board,
                    size,
                    seen,
                    color,
                    passes,
                    current_depth,
                    ordered,
                    deadline,
                    nodes,
                    cache,
                )
            except _Timeout:
                break
            if found is None:
                break
            chosen = found
            reached = current_depth
    return {"action": chosen, "depth": reached, "nodes": nodes[0]}


def _width(level: int, size: int) -> tuple[int, int]:
    cap = {1: 8, 2: 10, 3: 14, 4: 14, 5: 16}[level]
    if size >= 19:
        cap = max(8, cap - 4)
    radius = 1 if level == 1 else 2 if level < 5 else 3
    return cap, radius


def _score_actions(state: dict[str, Any], color: str) -> list[dict[str, Any]]:
    version = int(state.get("score_version") or 0)
    agreed = state.get("agreed") or {}
    human = other(color)
    if agreed.get(human) == version:
        if _marked_has_two_eyes(state):
            return [{"action": "resume"}]
        return [{"action": "agree"}]
    suggestion = suggested_dead(state)
    dead = _dead_set(state)
    if not suggestion or dead:
        return [{"action": "agree"}] if agreed.get(human) == version else []
    actions: list[dict[str, Any]] = []
    covered = set(dead)
    board = str(state["board"])
    size = int(state["size"])
    for col, row in sorted(suggestion):
        if (col, row) in covered:
            continue
        actions.append({"action": "mark", "col": col, "row": row})
        stones, _libs = group(board, size, col, row)
        covered.update(stones)
    return actions


def _marked_has_two_eyes(state: dict[str, Any]) -> bool:
    board = str(state["board"])
    size = int(state["size"])
    seen: set[tuple[int, int]] = set()
    for col, row in _dead_set(state):
        if (col, row) in seen or board[row * size + col] == EMPTY:
            continue
        stones, _libs = group(board, size, col, row)
        seen.update(stones)
        if eye_count(board, size, stones) >= 2:
            return True
    return False


def _dead_set(state: dict[str, Any]) -> set[tuple[int, int]]:
    return {(int(point[0]), int(point[1])) for point in state.get("dead") or []}


def _material(board: str, size: int, color: str, cache: dict[tuple[str, str], int]) -> int:
    key = (board, color)
    cached = cache.get(key)
    if cached is not None:
        return cached
    scored = area(board, size, set())
    diff = int(scored["black_half"]) - int(scored["white_half"])
    signed = diff if color == BLACK else -diff
    cache[key] = signed * 10
    return cache[key]


def _rank_root(
    board: str,
    size: int,
    seen: set[str],
    color: str,
    passes: int,
    cap: int,
    radius: int,
    cache: dict[tuple[str, str], int],
) -> list[tuple[int, dict[str, Any]]]:
    ranked: list[tuple[int, dict[str, Any]]] = []
    for col, row in _candidates(board, size, seen, color, cap, radius):
        try:
            placed, captured = play_stone(board, size, seen, color, col, row)
        except GoRuleError:
            continue
        score = -_material(placed, size, WHITE if color == BLACK else BLACK, cache)
        _stones, libs = group(placed, size, col, row)
        if len(libs) <= 1:
            score -= 30
        if captured:
            score += captured
        mid = (size - 1) / 2
        score -= int(max(abs(col - mid), abs(row - mid)))
        ranked.append((score, {"action": "move", "col": col, "row": row}))
    pass_score = _material(board, size, color, cache) if passes + 1 >= 2 else -_material(
        board,
        size,
        WHITE if color == BLACK else BLACK,
        cache,
    )
    ranked.append((pass_score, {"action": "pass"}))
    ranked.sort(
        key=lambda item: (
            -item[0],
            item[1]["action"] != "pass",
            item[1].get("col", -1),
            item[1].get("row", -1),
        )
    )
    return ranked


def _candidates(
    board: str,
    size: int,
    seen: set[str],
    color: str,
    cap: int,
    radius: int,
) -> list[tuple[int, int]]:
    stones = [index for index, cell in enumerate(board) if cell != EMPTY]
    found: list[tuple[int, int]] = []
    used: set[tuple[int, int]] = set()

    def add(col: int, row: int) -> None:
        if not (0 <= col < size and 0 <= row < size):
            return
        if board[row * size + col] != EMPTY or (col, row) in used:
            return
        used.add((col, row))
        found.append((col, row))

    if not stones:
        mid = size // 2
        margin = 2 if size == 9 else 3
        coords = (margin, mid, size - 1 - margin)
        add(mid, mid)
        for col in coords:
            for row in coords:
                add(col, row)
        return found
    opponent = WHITE if color == BLACK else BLACK
    seen_groups: set[frozenset[tuple[int, int]]] = set()
    for index, cell in enumerate(board):
        if cell != opponent:
            continue
        col, row = index % size, index // size
        group_stones, libs = group(board, size, col, row)
        if group_stones in seen_groups or len(libs) != 1:
            continue
        seen_groups.add(group_stones)
        liberty = next(iter(libs))
        add(liberty[0], liberty[1])
    urgent_keys = set(found)
    for index in stones:
        col, row = index % size, index // size
        for step_col in range(-radius, radius + 1):
            for step_row in range(-radius, radius + 1):
                if max(abs(step_col), abs(step_row)) == 0:
                    continue
                add(col + step_col, row + step_row)
    urgent: list[tuple[int, int]] = []
    nearby: list[tuple[int, int]] = []
    for col, row in found:
        try:
            play_stone(board, size, seen, color, col, row)
        except GoRuleError:
            continue
        if (col, row) in urgent_keys:
            urgent.append((col, row))
        else:
            nearby.append((col, row))
    if len(urgent) >= cap:
        return urgent[:cap]
    mid = (size - 1) / 2
    nearby.sort(key=lambda point: max(abs(point[0] - mid), abs(point[1] - mid)))
    return urgent + nearby[: cap - len(urgent)]


def _search_root(
    board: str,
    size: int,
    seen: set[str],
    color: str,
    passes: int,
    depth: int,
    ordered: list[dict[str, Any]],
    deadline: float,
    nodes: list[int],
    cache: dict[tuple[str, str], int],
) -> dict[str, Any] | None:
    best = -10**9
    chosen: dict[str, Any] | None = None
    opponent = WHITE if color == BLACK else BLACK
    for action in ordered:
        if time.perf_counter() >= deadline:
            raise _Timeout
        if action["action"] == "pass":
            if passes + 1 >= 2:
                score = _material(board, size, color, cache)
            else:
                score = -_negamax(
                    board, size, seen, opponent, passes + 1, depth - 1, -10**9, 10**9, deadline, nodes, cache
                )
        else:
            try:
                placed, _captured = play_stone(board, size, seen, color, int(action["col"]), int(action["row"]))
            except GoRuleError:
                continue
            seen.add(placed)
            try:
                score = -_negamax(placed, size, seen, opponent, 0, depth - 1, -10**9, 10**9, deadline, nodes, cache)
            finally:
                seen.remove(placed)
        if score > best:
            best = score
            chosen = action
    return chosen


def _negamax(
    board: str,
    size: int,
    seen: set[str],
    color: str,
    passes: int,
    depth: int,
    alpha: int,
    beta: int,
    deadline: float,
    nodes: list[int],
    cache: dict[tuple[str, str], int],
) -> int:
    nodes[0] += 1
    if nodes[0] % 24 == 0 and time.perf_counter() >= deadline:
        raise _Timeout
    if nodes[0] > 20000:
        raise _Timeout
    if depth <= 0 or passes >= 2:
        return _material(board, size, color, cache)
    opponent = WHITE if color == BLACK else BLACK
    best = -10**9
    moves = _candidates(board, size, seen, color, 8, 1)
    tried = False
    for col, row in moves:
        try:
            placed, _captured = play_stone(board, size, seen, color, col, row)
        except GoRuleError:
            continue
        tried = True
        seen.add(placed)
        try:
            score = -_negamax(placed, size, seen, opponent, 0, depth - 1, -beta, -alpha, deadline, nodes, cache)
        finally:
            seen.remove(placed)
        if score > best:
            best = score
        if score > alpha:
            alpha = score
        if alpha >= beta:
            return best
    if passes + 1 >= 2:
        pass_score = _material(board, size, color, cache)
    else:
        pass_score = -_negamax(
            board, size, seen, opponent, passes + 1, depth - 1, -beta, -alpha, deadline, nodes, cache
        )
    if pass_score > best:
        best = pass_score
    if not tried and best < -10**8:
        return _material(board, size, color, cache)
    return best
