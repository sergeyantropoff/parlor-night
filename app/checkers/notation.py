"""Числовая и алгебраическая запись хода русских шашек.

Тихий ход: 22-18. Взятие и серия: 21:14:7. Разделитель x тоже принимается.
"""

from __future__ import annotations

from app.checkers.captures import Move
from app.checkers.model import algebraic


def format_numeric(path: tuple[int, ...], capture: bool) -> str:
    separator = ":" if capture else "-"
    return separator.join(str(square) for square in path)


def format_algebraic(path: tuple[int, ...], capture: bool) -> str:
    separator = ":" if capture else "-"
    return separator.join(algebraic(square) for square in path)


def format_move(move: Move) -> str:
    return format_numeric(move.path, move.is_capture)


def format_move_algebraic(move: Move) -> str:
    return format_algebraic(move.path, move.is_capture)


def parse_notation(text: str) -> tuple[int, ...]:
    cleaned = text.strip().lower().replace("×", ":").replace("x", ":")
    if ":" in cleaned:
        parts = cleaned.split(":")
    elif "-" in cleaned:
        parts = cleaned.split("-")
    else:
        raise ValueError("ход записывается как 22-18 или 21:14:7")
    if len(parts) < 2 or any(not part.isdigit() for part in parts):
        raise ValueError("ход записывается номерами полей")
    path = tuple(int(part) for part in parts)
    if any(square < 1 or square > 32 for square in path):
        raise ValueError("номер поля должен быть от 1 до 32")
    return path


def dump_game_record(initial: str, notations: list[str], result: str | None) -> str:
    mapped = {"white_win": "2-0", "black_win": "0-2", "draw": "1-1"}
    score = mapped.get(result or "", "*")
    lines = [
        '[Game "Russian checkers"]',
        '[Variant "russian-8x8"]',
        f'[Position "{initial}"]',
        f'[Result "{score}"]',
        "",
    ]
    pairs: list[str] = []
    number = 1
    index = 0
    while index < len(notations):
        white = notations[index]
        black = notations[index + 1] if index + 1 < len(notations) else ""
        pairs.append(f"{number}. {white}" + (f" {black}" if black else ""))
        number += 1
        index += 2
    if pairs:
        lines.append(" ".join(pairs))
    lines.append(score)
    return "\n".join(lines) + "\n"
