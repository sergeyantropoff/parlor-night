"""Ход компьютера через SimpleEngine из py-draughts.

Уровень по-прежнему задаётся глубиной и временем: движок один,
а новичок считает мельче, чем мастер. Если библиотеки нет или она
вернула ход, которого нет в наших правилах, поиск отдаётся своему движку.
"""

from __future__ import annotations

import time

from app.checkers.model import BLACK, BLACK_KING, BLACK_MAN, WHITE, WHITE_KING, WHITE_MAN, Position
from app.checkers.notation import format_move, format_move_algebraic
from app.checkers.rules import legal_moves
from app.checkers.serialization import parse_rcp

ENGINE_NAME = "py-draughts SimpleEngine"


def ready() -> bool:
    try:
        import draughts
    except ImportError:
        return False
    return hasattr(draughts, "SimpleEngine") and hasattr(draughts, "RussianBoard")


def _fen(position: Position) -> str:
    def tokens(man: int, king: int) -> str:
        parts: list[str] = []
        for square in range(1, 33):
            piece = position.board[square]
            if piece == man:
                parts.append(str(square))
            elif piece == king:
                parts.append(f"K{square}")
        return ",".join(parts)

    turn = "W" if position.side == WHITE else "B"
    return f"{turn}:W{tokens(WHITE_MAN, WHITE_KING)}:B{tokens(BLACK_MAN, BLACK_KING)}"


def _match(position: Position, raw: object):
    squares = getattr(raw, "square_list", None) or []
    path = tuple(int(square) + 1 for square in squares)
    captured = tuple(sorted(int(square) + 1 for square in (getattr(raw, "captured_list", None) or [])))
    moves = legal_moves(position)
    for move in moves:
        if move.path == path:
            return move
    if not path:
        return None
    for move in moves:
        if move.path[0] == path[0] and move.path[-1] == path[-1] and tuple(sorted(move.victims)) == captured:
            return move
    return None


def play_simple(
    rcp: str,
    max_depth: int,
    time_ms: int,
) -> dict[str, object] | None:
    if not ready() or max_depth <= 0 or time_ms <= 0:
        return None
    from draughts import RussianBoard, SimpleEngine

    position = parse_rcp(rcp)
    board = RussianBoard.from_fen(_fen(position))
    started = time.perf_counter()
    engine = SimpleEngine(depth_limit=max(1, int(max_depth)), time_limit=max(0.05, time_ms / 1000))
    found, score = engine.get_best_move(board, with_evaluation=True)
    move = _match(position, found)
    if move is None:
        return None
    white_score = int(round(float(score) * 100))
    if position.side == BLACK:
        white_score = -white_score
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    nodes = int(getattr(engine, "nodes", 0) or 0)
    return {
        "path": [str(square) for square in move.path],
        "notation": format_move(move),
        "algebraic": format_move_algebraic(move),
        "score_white": white_score,
        "depth": int(max_depth),
        "nodes": nodes,
        "pv": [format_move(move)],
        "elapsed_ms": elapsed_ms,
        "engine": ENGINE_NAME,
    }
