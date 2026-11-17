"""Генерация ходов русских шашек.

Побитые шашки остаются на доске до конца серии и не бьются повторно.
Простая шашка, достигшая последней горизонтали во время взятия, сразу
получает права дамки и продолжает серию, если продолжение есть.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.checkers.model import (
    BLACK_MAN,
    DIRECTIONS,
    EMPTY,
    FORWARD,
    RAYS,
    RC,
    WHITE_MAN,
    is_king,
    owner,
)


@dataclass(frozen=True, slots=True)
class Move:
    path: tuple[int, ...]
    victims: tuple[int, ...]
    final_piece: int

    @property
    def is_capture(self) -> bool:
        return bool(self.victims)


def promote(piece: int, square: int) -> int:
    rank, _file = RC[square]  # type: ignore[misc]
    if piece == WHITE_MAN and rank == 7:
        return piece + 1
    if piece == BLACK_MAN and rank == 0:
        return piece + 1
    return piece


def _capture_landings(
    board: tuple[int, ...] | list[int],
    square: int,
    piece: int,
    captured: frozenset[int],
) -> list[tuple[int, int]]:
    result: list[tuple[int, int]] = []
    rays = RAYS[square]
    assert rays is not None
    piece_owner = owner(piece)
    for delta in DIRECTIONS:
        ray = rays[delta]
        if is_king(piece):
            victim: int | None = None
            for target in ray:
                occupied = board[target]
                if victim is None:
                    if occupied == EMPTY:
                        continue
                    if owner(occupied) == piece_owner or target in captured:
                        break
                    victim = target
                    continue
                if occupied != EMPTY:
                    break
                result.append((victim, target))
            continue
        if len(ray) < 2:
            continue
        victim_sq = ray[0]
        land_sq = ray[1]
        occupied = board[victim_sq]
        if occupied == EMPTY or owner(occupied) == piece_owner or victim_sq in captured:
            continue
        if board[land_sq] != EMPTY:
            continue
        result.append((victim_sq, land_sq))
    return result


def capture_sequences(
    board: tuple[int, ...],
    square: int,
    piece: int,
    captured: frozenset[int] | None = None,
) -> list[Move]:
    taken = captured or frozenset()
    moves: list[Move] = []
    for victim, landing in _capture_landings(board, square, piece, taken):
        updated = list(board)
        updated[square] = EMPTY
        new_piece = promote(piece, landing)
        updated[landing] = new_piece
        continued = capture_sequences(tuple(updated), landing, new_piece, taken | {victim})
        if continued:
            moves.extend(
                Move((square, *item.path), (victim, *item.victims), item.final_piece)
                for item in continued
            )
        else:
            moves.append(Move((square, landing), (victim,), new_piece))
    return moves


def quiet_moves(board: tuple[int, ...], square: int, piece: int) -> list[Move]:
    moves: list[Move] = []
    rays = RAYS[square]
    assert rays is not None
    deltas = DIRECTIONS if is_king(piece) else FORWARD[owner(piece)]  # type: ignore[index]
    for delta in deltas:
        for target in rays[delta]:
            if board[target] != EMPTY:
                break
            moves.append(Move((square, target), (), promote(piece, target)))
            if not is_king(piece):
                break
    return moves


def has_immediate_capture(board: tuple[int, ...], square: int, piece: int) -> bool:
    return bool(_capture_landings(board, square, piece, frozenset()))
