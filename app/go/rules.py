"""Правила постановки камня, свобод и подсчёта площади. Без сети и базы."""

from __future__ import annotations

EMPTY = "0"
BLACK = "1"
WHITE = "2"
SIZES = (9, 13, 19)
RULES_ID = "parlor-area-psk-v1"
KOMI_HALF = 15

CODE = {"black": BLACK, "white": WHITE}
NAME = {BLACK: "black", WHITE: "white"}


class GoRuleError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def other(color: str) -> str:
    if color == "black":
        return "white"
    if color == "white":
        return "black"
    raise GoRuleError("Неизвестная сторона.")


def empty_board(size: int) -> str:
    if size not in SIZES:
        raise GoRuleError("Размер доски: 9, 13 или 19.")
    return EMPTY * (size * size)


def neighbors(size: int, col: int, row: int) -> tuple[tuple[int, int], ...]:
    found: list[tuple[int, int]] = []
    for delta_col, delta_row in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        next_col = col + delta_col
        next_row = row + delta_row
        if 0 <= next_col < size and 0 <= next_row < size:
            found.append((next_col, next_row))
    return tuple(found)


def point_name(col: int, row: int, size: int) -> str:
    letter = col if col < 8 else col + 1
    return f"{chr(ord('A') + letter)}{size - row}"


def group(
    board: str,
    size: int,
    col: int,
    row: int,
) -> tuple[frozenset[tuple[int, int]], frozenset[tuple[int, int]]]:
    color = board[row * size + col]
    if color == EMPTY:
        return frozenset(), frozenset()
    stones: set[tuple[int, int]] = set()
    liberties: set[tuple[int, int]] = set()
    stack = [(col, row)]
    while stack:
        current_col, current_row = stack.pop()
        if (current_col, current_row) in stones:
            continue
        stones.add((current_col, current_row))
        for next_col, next_row in neighbors(size, current_col, current_row):
            cell = board[next_row * size + next_col]
            if cell == EMPTY:
                liberties.add((next_col, next_row))
            elif cell == color and (next_col, next_row) not in stones:
                stack.append((next_col, next_row))
    return frozenset(stones), frozenset(liberties)


def play_stone(
    board: str,
    size: int,
    seen: set[str],
    color: str,
    col: int,
    row: int,
) -> tuple[str, int]:
    if size not in SIZES or len(board) != size * size:
        raise GoRuleError("Размер доски: 9, 13 или 19.")
    if color not in {BLACK, WHITE}:
        raise GoRuleError("Неизвестная сторона.")
    if not (0 <= col < size and 0 <= row < size):
        raise GoRuleError("Точка вне доски.")
    if board[row * size + col] != EMPTY:
        raise GoRuleError("Это пересечение занято.")
    chars = list(board)
    chars[row * size + col] = color
    placed = "".join(chars)
    opponent = WHITE if color == BLACK else BLACK
    captured: set[tuple[int, int]] = set()
    for next_col, next_row in neighbors(size, col, row):
        if placed[next_row * size + next_col] != opponent:
            continue
        stones, liberties = group(placed, size, next_col, next_row)
        if not liberties:
            captured.update(stones)
    if captured:
        chars = list(placed)
        for stone_col, stone_row in captured:
            chars[stone_row * size + stone_col] = EMPTY
        placed = "".join(chars)
    _stones, own_liberties = group(placed, size, col, row)
    if not own_liberties:
        raise GoRuleError("Этот ход снимает собственные камни.")
    if placed in seen:
        raise GoRuleError("Эта позиция уже была.")
    return placed, len(captured)


def legal_points(board: str, size: int, seen: set[str], color: str) -> list[list[int]]:
    found: list[list[int]] = []
    for row in range(size):
        for col in range(size):
            if board[row * size + col] != EMPTY:
                continue
            try:
                play_stone(board, size, seen, color, col, row)
            except GoRuleError:
                continue
            found.append([col, row])
    return found


def _flood(
    board: str,
    size: int,
    col: int,
    row: int,
) -> tuple[frozenset[tuple[int, int]], frozenset[str]]:
    region: set[tuple[int, int]] = set()
    touches: set[str] = set()
    stack = [(col, row)]
    while stack:
        current_col, current_row = stack.pop()
        if (current_col, current_row) in region:
            continue
        if board[current_row * size + current_col] != EMPTY:
            continue
        region.add((current_col, current_row))
        for next_col, next_row in neighbors(size, current_col, current_row):
            cell = board[next_row * size + next_col]
            if cell == EMPTY:
                stack.append((next_col, next_row))
            else:
                touches.add(cell)
    return frozenset(region), frozenset(touches)


def format_half(half: int) -> str:
    sign = "-" if half < 0 else ""
    whole, remainder = divmod(abs(half), 2)
    if remainder:
        return f"{sign}{whole},5"
    return f"{sign}{whole}"


def format_sgf_half(half: int) -> str:
    whole, remainder = divmod(abs(half), 2)
    if remainder:
        return f"{whole}.5"
    return str(whole)


def area(
    board: str,
    size: int,
    dead: set[tuple[int, int]],
    *,
    komi_half: int = KOMI_HALF,
) -> dict[str, object]:
    chars = list(board)
    for col, row in dead:
        if 0 <= col < size and 0 <= row < size and chars[row * size + col] != EMPTY:
            chars[row * size + col] = EMPTY
    cleared = "".join(chars)
    black_alive = cleared.count(BLACK)
    white_alive = cleared.count(WHITE)
    visited: set[tuple[int, int]] = set()
    black_territory = 0
    white_territory = 0
    neutral = 0
    owners: dict[tuple[int, int], str] = {}
    for row in range(size):
        for col in range(size):
            if (col, row) in visited or cleared[row * size + col] != EMPTY:
                continue
            region, touches = _flood(cleared, size, col, row)
            visited.update(region)
            if touches == {BLACK}:
                owner = "black"
                black_territory += len(region)
            elif touches == {WHITE}:
                owner = "white"
                white_territory += len(region)
            else:
                owner = "neutral"
                neutral += len(region)
            for point in region:
                owners[point] = owner
    black_half = 2 * (black_alive + black_territory)
    white_half = 2 * (white_alive + white_territory) + komi_half
    if black_half > white_half:
        winner = "black"
    elif white_half > black_half:
        winner = "white"
    else:
        winner = "draw"
    margin = abs(black_half - white_half)
    if winner == "black":
        lead = f"Чёрные ведут на {format_half(margin)}"
    elif winner == "white":
        lead = f"Белые ведут на {format_half(margin)}"
    else:
        lead = "Очки равны"
    return {
        "black_alive": black_alive,
        "white_alive": white_alive,
        "black_territory": black_territory,
        "white_territory": white_territory,
        "neutral": neutral,
        "black_half": black_half,
        "white_half": white_half,
        "black_text": format_half(black_half),
        "white_text": format_half(white_half),
        "margin_half": margin,
        "margin_text": format_half(margin),
        "winner": winner,
        "lead": lead,
        "owners": owners,
    }
