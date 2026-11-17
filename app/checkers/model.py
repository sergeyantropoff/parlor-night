"""Геометрия 64-клеточной доски и позиция русских шашек.

Нумерация 1–32: белые внизу, слева направо, сверху вниз.
Белые простые шашки начинают на полях 21–32, чёрные — на 1–12.
Поле a1 тёмное и имеет номер 29.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

WHITE = 0
BLACK = 1

EMPTY = 0
WHITE_MAN = 1
WHITE_KING = 2
BLACK_MAN = 3
BLACK_KING = 4

FILES = "abcdefgh"

NE = (1, 1)
NW = (1, -1)
SE = (-1, 1)
SW = (-1, -1)
DIRECTIONS = (NE, NW, SE, SW)
FORWARD = {
    WHITE: (NE, NW),
    BLACK: (SE, SW),
}


def opposite(side: int) -> int:
    return BLACK if side == WHITE else WHITE


def owner(piece: int) -> int | None:
    if piece in (WHITE_MAN, WHITE_KING):
        return WHITE
    if piece in (BLACK_MAN, BLACK_KING):
        return BLACK
    return None


def is_king(piece: int) -> bool:
    return piece in (WHITE_KING, BLACK_KING)


def is_man(piece: int) -> bool:
    return piece in (WHITE_MAN, BLACK_MAN)


def number_to_rc(number: int) -> tuple[int, int]:
    if not 1 <= number <= 32:
        raise ValueError(f"square out of range: {number}")
    index = number - 1
    row_from_top = index // 4
    pos = index % 4
    rank = 7 - row_from_top
    file = pos * 2 + (rank % 2)
    return rank, file


def _build_tables() -> tuple[
    list[tuple[int, int] | None],
    dict[tuple[int, int], int],
    list[dict[tuple[int, int], tuple[int, ...]] | None],
]:
    rc: list[tuple[int, int] | None] = [None]
    square_of: dict[tuple[int, int], int] = {}
    for number in range(1, 33):
        coords = number_to_rc(number)
        rc.append(coords)
        square_of[coords] = number
    rays: list[dict[tuple[int, int], tuple[int, ...]] | None] = [None]
    for number in range(1, 33):
        rank, file = rc[number]  # type: ignore[misc]
        bucket: dict[tuple[int, int], tuple[int, ...]] = {}
        for delta_rank, delta_file in DIRECTIONS:
            ray: list[int] = []
            row = rank + delta_rank
            col = file + delta_file
            while 0 <= row < 8 and 0 <= col < 8:
                ray.append(square_of[(row, col)])
                row += delta_rank
                col += delta_file
            bucket[(delta_rank, delta_file)] = tuple(ray)
        rays.append(bucket)
    return rc, square_of, rays


RC, SQUARE_OF, RAYS = _build_tables()


def algebraic(number: int) -> str:
    rank, file = RC[number]  # type: ignore[misc]
    return f"{FILES[file]}{rank + 1}"


def square_from_algebraic(text: str) -> int:
    cleaned = text.strip().lower()
    if len(cleaned) != 2 or cleaned[0] not in FILES or cleaned[1] not in "12345678":
        raise ValueError("некорректное поле")
    square = SQUARE_OF.get((int(cleaned[1]) - 1, FILES.index(cleaned[0])))
    if square is None:
        raise ValueError("в русских шашках используется только тёмное поле")
    return square


_RNG = random.Random(0x5A175EED)
_Z_PIECE = [[0] * 33]
for _piece in range(4):
    _Z_PIECE.append([_RNG.getrandbits(64) for _ in range(33)])
_Z_BLACK = _RNG.getrandbits(64)
_Z_CLOCK = [_RNG.getrandbits(64) for _ in range(64)]


def zobrist(board: tuple[int, ...], side: int, clock: int) -> int:
    value = 0
    for square in range(1, 33):
        piece = board[square]
        if piece:
            value ^= _Z_PIECE[piece][square]
    if side == BLACK:
        value ^= _Z_BLACK
    value ^= _Z_CLOCK[min(max(clock, 0), 63)]
    return value


def placement_key(board: tuple[int, ...], side: int) -> str:
    white: list[str] = []
    black: list[str] = []
    for square in range(1, 33):
        piece = board[square]
        if piece == WHITE_MAN:
            white.append(str(square))
        elif piece == WHITE_KING:
            white.append(f"K{square}")
        elif piece == BLACK_MAN:
            black.append(str(square))
        elif piece == BLACK_KING:
            black.append(f"K{square}")
    side_token = "w" if side == WHITE else "b"
    return f"{side_token}|{','.join(white)}|{','.join(black)}"


@dataclass(frozen=True, slots=True)
class Position:
    board: tuple[int, ...]
    side: int
    clock: int

    def key(self) -> int:
        return zobrist(self.board, self.side, self.clock)

    def placement_key(self) -> str:
        return placement_key(self.board, self.side)


def empty_board() -> list[int]:
    return [EMPTY] * 33
