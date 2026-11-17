"""Применение правил русских шашек: легальные ходы, проведение хода, итог."""

from __future__ import annotations

from dataclasses import dataclass

from app.checkers.captures import Move, capture_sequences, quiet_moves
from app.checkers.draws import nonprogress_draw, repetition_draw, technical_draw
from app.checkers.model import EMPTY, Position, is_man, opposite, owner
from app.errors import IllegalMove


@dataclass(frozen=True, slots=True)
class Outcome:
    result: str
    reason: str


def legal_moves(pos: Position) -> list[Move]:
    captures: list[Move] = []
    for square in range(1, 33):
        piece = pos.board[square]
        if owner(piece) != pos.side:
            continue
        captures.extend(capture_sequences(pos.board, square, piece))
    if captures:
        unique = {move.path: move for move in captures}
        return [unique[path] for path in sorted(unique)]
    quiets: list[Move] = []
    for square in range(1, 33):
        piece = pos.board[square]
        if owner(piece) != pos.side:
            continue
        quiets.extend(quiet_moves(pos.board, square, piece))
    return sorted(quiets, key=lambda move: move.path)


def move_from_path(pos: Position, path: tuple[int, ...]) -> Move:
    for move in legal_moves(pos):
        if move.path == path:
            return move
    raise IllegalMove("Этот ход не допускается правилами.")


def apply_move(pos: Position, move: Move) -> Position:
    piece = pos.board[move.path[0]]
    if owner(piece) != pos.side:
        raise IllegalMove("Сейчас ход другой стороны.")
    board = list(pos.board)
    board[move.path[0]] = EMPTY
    for victim in move.victims:
        board[victim] = EMPTY
    board[move.path[-1]] = move.final_piece
    clock = 0 if move.victims or is_man(piece) else pos.clock + 1
    return Position(tuple(board), opposite(pos.side), clock)


def outcome(pos: Position, history: list[str], ply: int) -> Outcome | None:
    if not legal_moves(pos):
        winner = "white_win" if pos.side == 1 else "black_win"
        return Outcome(winner, "no_moves")
    if technical_draw(ply):
        return Outcome("draw", "technical_limit")
    if nonprogress_draw(pos.clock):
        return Outcome("draw", "nonprogress")
    if repetition_draw(history):
        return Outcome("draw", "repetition")
    return None
