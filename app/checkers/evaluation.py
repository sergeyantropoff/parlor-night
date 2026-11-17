"""Оценка позиции. Коэффициенты можно заменить, не меняя правила."""

from __future__ import annotations

from dataclasses import dataclass

from app.checkers.captures import _capture_landings
from app.checkers.model import (
    BLACK,
    BLACK_MAN,
    DIRECTIONS,
    EMPTY,
    RAYS,
    RC,
    WHITE,
    WHITE_MAN,
    Position,
    is_king,
    owner,
)

CENTER = {10, 11, 14, 15, 18, 19, 22, 23}


@dataclass(frozen=True, slots=True)
class EvalWeights:
    man: int = 100
    king: int = 300
    advancement: int = 4
    center: int = 3
    mobility: int = 2
    capture_threat: int = 6
    back_rank: int = 2
    exposure: int = 5


DEFAULT_WEIGHTS = EvalWeights()


def _mobility(board: tuple[int, ...], square: int, piece: int) -> int:
    rays = RAYS[square]
    assert rays is not None
    score = 0
    for delta in DIRECTIONS:
        empty_run = 0
        for target in rays[delta]:
            if board[target] != EMPTY:
                break
            empty_run += 1
            if not is_king(piece):
                break
        score += min(empty_run, 4)
    return score


def _captures_victim(board: tuple[int, ...], origin: int, piece: int, victim: int) -> bool:
    return any(found == victim for found, _land in _capture_landings(board, origin, piece, frozenset()))


def _is_hanging(board: tuple[int, ...], square: int) -> bool:
    piece = board[square]
    side = owner(piece)
    if side is None:
        return False
    opponent = BLACK if side == WHITE else WHITE
    for origin in range(1, 33):
        attacker = board[origin]
        if owner(attacker) != opponent:
            continue
        if _captures_victim(board, origin, attacker, square):
            return True
    return False


def evaluate_white(pos: Position, weights: EvalWeights = DEFAULT_WEIGHTS) -> int:
    score = 0
    for square in range(1, 33):
        piece = pos.board[square]
        if piece == EMPTY:
            continue
        rank, _file = RC[square]  # type: ignore[misc]
        sign = 1 if owner(piece) == WHITE else -1
        if piece in (WHITE_MAN, BLACK_MAN):
            advance = rank if piece == WHITE_MAN else 7 - rank
            on_back = (piece == WHITE_MAN and rank == 0) or (piece == BLACK_MAN and rank == 7)
            material = weights.man + advance * weights.advancement
            if on_back:
                material += weights.back_rank
        else:
            material = weights.king
        center = weights.center if square in CENTER else 0
        mobile = _mobility(pos.board, square, piece) * weights.mobility
        threat = (
            weights.capture_threat
            if _capture_landings(pos.board, square, piece, frozenset())
            else 0
        )
        hanging = weights.exposure if _is_hanging(pos.board, square) else 0
        score += sign * (material + center + mobile + threat - hanging)
    return score


def evaluate(pos: Position, weights: EvalWeights = DEFAULT_WEIGHTS) -> int:
    """Оценка со стороны игрока, которому принадлежит ход."""

    white_score = evaluate_white(pos, weights)
    return white_score if pos.side == WHITE else -white_score
