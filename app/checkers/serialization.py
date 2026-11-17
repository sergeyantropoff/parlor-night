"""Формат позиции RCP. Это не шахматная нотация FEN.

Строка: «сторона|белые|чёрные|счётчик».
Сторона — w или b. Дамка помечается префиксом K. Счётчик — число полуходов
подряд без взятия и без хода простой шашки.

Пример начальной позиции:
w|21,22,23,24,25,26,27,28,29,30,31,32|1,2,3,4,5,6,7,8,9,10,11,12|0
"""

from __future__ import annotations

import re

from app.checkers.model import (
    BLACK,
    BLACK_KING,
    BLACK_MAN,
    EMPTY,
    WHITE,
    WHITE_KING,
    WHITE_MAN,
    Position,
    empty_board,
)

INITIAL_RCP = "w|21,22,23,24,25,26,27,28,29,30,31,32|1,2,3,4,5,6,7,8,9,10,11,12|0"

_TOKEN = re.compile(r"^K?(?:[1-9]|[12][0-9]|3[0-2])$")
_LINE = re.compile(r"^([wb])\|([K0-9,]*)\|([K0-9,]*)\|(\d+)$")


def _parse_tokens(raw: str, piece_man: int, piece_king: int, board: list[int]) -> None:
    if not raw:
        return
    for token in raw.split(","):
        if not _TOKEN.fullmatch(token):
            raise ValueError("некорректный список шашек")
        king = token.startswith("K")
        square = int(token[1:] if king else token)
        if board[square] != EMPTY:
            raise ValueError("на одном поле две шашки")
        board[square] = piece_king if king else piece_man


def parse_rcp(text: str) -> Position:
    cleaned = text.strip()
    match = _LINE.fullmatch(cleaned)
    if match is None:
        raise ValueError("позиция шашек должна быть в формате RCP, а не FEN")
    side_token, white_raw, black_raw, clock_raw = match.groups()
    board = empty_board()
    _parse_tokens(white_raw, WHITE_MAN, WHITE_KING, board)
    _parse_tokens(black_raw, BLACK_MAN, BLACK_KING, board)
    white_count = sum(piece in (WHITE_MAN, WHITE_KING) for piece in board)
    black_count = sum(piece in (BLACK_MAN, BLACK_KING) for piece in board)
    if white_count > 12 or black_count > 12:
        raise ValueError("у стороны не может быть больше 12 шашек")
    return Position(tuple(board), WHITE if side_token == "w" else BLACK, int(clock_raw))


def _dump_side(board: tuple[int, ...], man: int, king: int) -> str:
    tokens: list[tuple[int, str]] = []
    for square in range(1, 33):
        piece = board[square]
        if piece == man:
            tokens.append((square, str(square)))
        elif piece == king:
            tokens.append((square, f"K{square}"))
    tokens.sort()
    return ",".join(token for _square, token in tokens)


def dump_rcp(pos: Position) -> str:
    side = "w" if pos.side == WHITE else "b"
    white = _dump_side(pos.board, WHITE_MAN, WHITE_KING)
    black = _dump_side(pos.board, BLACK_MAN, BLACK_KING)
    return f"{side}|{white}|{black}|{pos.clock}"


def initial_position() -> Position:
    return parse_rcp(INITIAL_RCP)
