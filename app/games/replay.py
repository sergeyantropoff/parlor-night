"""Сборка позиции из записи ходов. Восстановление не доверяет присланному клиентом состоянию."""

from __future__ import annotations

import chess
from app.checkers.model import Position
from app.checkers.notation import parse_notation
from app.checkers.rules import apply_move, move_from_path, outcome
from app.checkers.serialization import dump_rcp, parse_rcp
from app.chess.rules import ChessOutcome, outcome_of, parse_board, push_user_move, replay


def replay_checkers(initial: str, payloads: list[dict[str, object]]) -> tuple[Position, list[str]]:
    position = parse_rcp(initial)
    keys = [position.placement_key()]
    for payload in payloads:
        path = tuple(int(square) for square in payload["path"])  # type: ignore[index]
        move = move_from_path(position, path)
        position = apply_move(position, move)
        keys.append(position.placement_key())
    return position, keys


def checkers_outcome(position: Position, keys: list[str]) -> object:
    return outcome(position, keys, len(keys) - 1)


def replay_chess(initial: str, payloads: list[dict[str, object]]) -> chess.Board:
    return replay(initial, [str(payload["uci"]) for payload in payloads])


def chess_outcome(board: chess.Board) -> ChessOutcome | None:
    return outcome_of(board)


def apply_checkers_notation(initial: str, notations: list[str]) -> tuple[str, list[dict[str, object]]]:
    position = parse_rcp(initial)
    stored: list[dict[str, object]] = []
    for notation in notations:
        path = parse_notation(notation)
        before = dump_rcp(position)
        move = move_from_path(position, path)
        position = apply_move(position, move)
        from app.checkers.notation import format_move, format_move_algebraic

        stored.append(
            {
                "notation": format_move(move),
                "before": before,
                "after": dump_rcp(position),
                "payload": {
                    "path": list(move.path),
                    "algebraic": format_move_algebraic(move),
                    "by": "human",
                },
            }
        )
    return dump_rcp(position), stored


def apply_chess_moves(initial: str, specs: list[tuple[list[str], str | None]]) -> tuple[str, list[dict[str, object]]]:
    board = parse_board(initial)
    stored: list[dict[str, object]] = []
    for path, promotion in specs:
        before = board.fen()
        record = push_user_move(board, path, promotion)
        stored.append(
            {
                "notation": record.san,
                "before": before,
                "after": board.fen(),
                "payload": {
                    "uci": record.uci,
                    "path": list(record.path),
                    "promotion": record.promotion,
                    "by": "human",
                },
            }
        )
    return board.fen(), stored
