"""Поиск хода в русских шашках.

Собственный движок: negamax, альфа-бета, итеративное углубление,
упорядочивание ходов и таблица транспозиций. Это учебный поиск.
Его сила зависит от глубины, лимита времени и эвристик и не претендует
на уровень профессиональной шашечной программы.

Поиск детерминирован, пока выключены variety и допуск слабого уровня.
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass

from app.checkers.captures import Move
from app.checkers.evaluation import DEFAULT_WEIGHTS, EvalWeights, evaluate
from app.checkers.model import Position
from app.checkers.rules import apply_move, legal_moves
from app.errors import AnalysisIncomplete

MATE = 100_000
MATE_LIMIT = 90_000
EXACT = 0
LOWER = 1
UPPER = 2

# Глубина, время и допуск: новичок играет в один полуход и путает близкие ходы.
# Простая шашка стоит 100, поэтому допуск 60 не отдаёт шашку, но не видит ответ.
LEVELS: dict[int, tuple[int, int, int]] = {
    1: (1, 150, 60),
    2: (2, 400, 15),
    3: (4, 900, 0),
    4: (7, 2000, 0),
    5: (10, 3500, 0),
}


class _Timeout(Exception):
    pass


@dataclass(slots=True)
class _TTEntry:
    depth: int
    score: int
    flag: int
    move: Move | None


@dataclass(frozen=True, slots=True)
class SearchResult:
    move: Move
    score_white: int
    depth: int
    nodes: int
    pv: tuple[Move, ...]
    elapsed_ms: int


def _order(moves: list[Move], hint: Move | None) -> list[Move]:
    def key(move: Move) -> tuple[int, int, int, tuple[int, ...]]:
        preferred = 0 if hint is not None and move.path == hint.path else 1
        capture_rank = 0 if move.is_capture else 1
        return (preferred, capture_rank, -len(move.victims), move.path)

    return sorted(moves, key=key)


def _store(table: dict[int, _TTEntry], key: int, entry: _TTEntry) -> None:
    if len(table) > 100_000:
        table.clear()
    current = table.get(key)
    if current is None or entry.depth >= current.depth:
        table[key] = entry


def _lookup(table: dict[int, _TTEntry], key: int, depth: int, alpha: int, beta: int) -> int | None:
    entry = table.get(key)
    if entry is None or entry.depth < depth or abs(entry.score) >= MATE_LIMIT:
        return None
    if entry.flag == EXACT:
        return entry.score
    if entry.flag == LOWER and entry.score >= beta:
        return entry.score
    if entry.flag == UPPER and entry.score <= alpha:
        return entry.score
    return None


def _qsearch(
    pos: Position,
    alpha: int,
    beta: int,
    ply: int,
    remaining: int,
    weights: EvalWeights,
    deadline: float,
    nodes: list[int],
) -> int:
    nodes[0] += 1
    if nodes[0] % 64 == 0 and time.perf_counter() >= deadline:
        raise _Timeout
    moves = legal_moves(pos)
    if not moves:
        return -MATE + ply
    stand = evaluate(pos, weights)
    if stand >= beta:
        return stand
    if stand > alpha:
        alpha = stand
    if remaining == 0:
        return stand
    captures = [move for move in moves if move.is_capture]
    for move in captures:
        score = -_qsearch(
            apply_move(pos, move),
            -beta,
            -alpha,
            ply + 1,
            remaining - 1,
            weights,
            deadline,
            nodes,
        )
        if score >= beta:
            return score
        if score > alpha:
            alpha = score
    return alpha


def _negamax(
    pos: Position,
    depth: int,
    alpha: int,
    beta: int,
    ply: int,
    weights: EvalWeights,
    table: dict[int, _TTEntry],
    deadline: float,
    nodes: list[int],
) -> int:
    nodes[0] += 1
    if nodes[0] % 64 == 0 and time.perf_counter() >= deadline:
        raise _Timeout
    key = pos.key()
    cached = _lookup(table, key, depth, alpha, beta)
    if cached is not None:
        return cached
    if depth == 0:
        score = _qsearch(pos, alpha, beta, ply, 4, weights, deadline, nodes)
        _store(table, key, _TTEntry(0, score, EXACT, None))
        return score
    moves = legal_moves(pos)
    if not moves:
        score = -MATE + ply
        _store(table, key, _TTEntry(depth, score, EXACT, None))
        return score
    hint = table.get(key).move if key in table else None
    ordered = _order(moves, hint)
    best = -MATE
    best_move = ordered[0]
    original_alpha = alpha
    for move in ordered:
        score = -_negamax(
            apply_move(pos, move),
            depth - 1,
            -beta,
            -alpha,
            ply + 1,
            weights,
            table,
            deadline,
            nodes,
        )
        if score > best:
            best = score
            best_move = move
        if score > alpha:
            alpha = score
        if alpha >= beta:
            break
    if best <= original_alpha:
        flag = UPPER
    elif best >= beta:
        flag = LOWER
    else:
        flag = EXACT
    _store(table, key, _TTEntry(depth, best, flag, best_move))
    return best


def _principal_variation(
    pos: Position,
    table: dict[int, _TTEntry],
    depth: int,
) -> tuple[Move, ...]:
    line: list[Move] = []
    current = pos
    seen: set[tuple[int, ...]] = set()
    for _ in range(depth):
        entry = table.get(current.key())
        if entry is None or entry.move is None or entry.move.path in seen:
            break
        line.append(entry.move)
        seen.add(entry.move.path)
        current = apply_move(current, entry.move)
    return tuple(line)


def search(
    pos: Position,
    *,
    max_depth: int,
    time_ms: int,
    weights: EvalWeights = DEFAULT_WEIGHTS,
    variety: bool = False,
    slack: int = 0,
) -> SearchResult:
    if time_ms <= 0 or max_depth <= 0:
        raise AnalysisIncomplete("Движок не завершил анализ и не выбрал ход.")
    started = time.perf_counter()
    deadline = started + time_ms / 1000
    table: dict[int, _TTEntry] = {}
    nodes = [0]
    completed: tuple[Move, int, int] | None = None
    for depth in range(1, max_depth + 1):
        if time.perf_counter() >= deadline and depth > 1:
            break
        try:
            score = _negamax(pos, depth, -MATE, MATE, 0, weights, table, deadline, nodes)
        except _Timeout:
            break
        entry = table.get(pos.key())
        move = entry.move if entry and entry.move is not None else None
        if move is None:
            break
        completed = (move, score, depth)
        if abs(score) >= MATE_LIMIT:
            break
    if completed is None:
        raise AnalysisIncomplete("Движок не завершил анализ и не выбрал ход.")
    move, score, depth = completed
    if slack > 0:
        move = _slack_move(pos, weights, slack)
        score = -evaluate(apply_move(pos, move), weights)
        pv: tuple[Move, ...] = (move,)
    else:
        if variety:
            move = _varied_move(pos, weights, move)
        pv = _principal_variation(pos, table, depth)
        if not pv or pv[0].path != move.path:
            pv = (move, *pv[1:]) if pv else (move,)
    white_score = score if pos.side == 0 else -score
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    return SearchResult(move, white_score, depth, nodes[0], pv, elapsed_ms)


def _slack_move(pos: Position, weights: EvalWeights, slack: int) -> Move:
    ranked: list[tuple[int, Move]] = []
    for move in legal_moves(pos):
        after = apply_move(pos, move)
        ranked.append((-evaluate(after, weights), move))
    if not ranked:
        raise AnalysisIncomplete("Движок не завершил анализ и не выбрал ход.")
    top = max(score for score, _move in ranked)
    pool = [move for score, move in ranked if top - score <= slack]
    return random.choice(pool)


def _varied_move(pos: Position, weights: EvalWeights, best: Move) -> Move:
    ranked: list[tuple[int, Move]] = []
    for move in legal_moves(pos):
        child = apply_move(pos, move)
        ranked.append((evaluate(child, weights), move))
    if not ranked:
        return best
    top = max(score for score, _move in ranked)
    window = [move for score, move in ranked if top - score <= 30]
    if len(window) == 1:
        return window[0]
    return random.choice(window)


def search_job(
    rcp: str,
    max_depth: int,
    time_ms: int,
    weights: dict[str, int],
    variety: bool,
    slack: int = 0,
) -> dict[str, object]:
    """Точка входа процесса-поиска. Аргументы только простые и сериализуемые."""

    from app.checkers.notation import format_move, format_move_algebraic
    from app.checkers.serialization import parse_rcp

    from app.checkers.simple import play_simple

    found = None
    try:
        found = play_simple(rcp, max_depth, time_ms)
    except Exception:
        found = None
    position = parse_rcp(rcp)
    if found is not None:
        if variety:
            matched = next(
                (item for item in legal_moves(position) if [str(square) for square in item.path] == found["path"]),
                None,
            )
            if matched is not None:
                varied = _varied_move(position, EvalWeights(**weights), matched)
                found["path"] = [str(square) for square in varied.path]
                found["notation"] = format_move(varied)
                found["algebraic"] = format_move_algebraic(varied)
                found["pv"] = [found["notation"]]
        return found
    result = search(
        position,
        max_depth=max_depth,
        time_ms=time_ms,
        weights=EvalWeights(**weights),
        variety=variety,
        slack=slack,
    )
    return {
        "path": [str(square) for square in result.move.path],
        "notation": format_move(result.move),
        "algebraic": format_move_algebraic(result.move),
        "score_white": result.score_white,
        "depth": result.depth,
        "nodes": result.nodes,
        "pv": [format_move(item) for item in result.pv],
        "elapsed_ms": result.elapsed_ms,
        "engine": "boardmentor-checkers 1.0.0",
    }


def search_level(
    pos: Position,
    level: int,
    *,
    weights: EvalWeights = DEFAULT_WEIGHTS,
    variety: bool = False,
    time_ms: int | None = None,
) -> SearchResult:
    depth, budget, slack = LEVELS[max(1, min(5, level))]
    return search(
        pos,
        max_depth=depth,
        time_ms=time_ms if time_ms is not None else budget,
        weights=weights,
        variety=variety,
        slack=0 if variety else slack,
    )
