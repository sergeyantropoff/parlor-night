"""Экспорт реальной партии в SGF FF[4]. Без внешнего анализа."""

from __future__ import annotations

from typing import Any

from app.go.rules import RULES_ID, format_sgf_half


def export_sgf(
    *,
    size: int,
    moves: list[dict[str, Any]],
    black_name: str,
    white_name: str,
    played_on: str,
    result: str | None,
    reason: str | None,
    margin_half: int | None,
) -> str:
    properties = [
        "GM[1]",
        "FF[4]",
        "CA[UTF-8]",
        f"SZ[{size}]",
        "KM[7.5]",
        f"PB[{_escape(black_name)}]",
        f"PW[{_escape(white_name)}]",
        f"RU[{RULES_ID}]",
        f"DT[{_escape(played_on)}]",
    ]
    outcome = _result(result, reason, margin_half)
    if outcome:
        properties.append(f"RE[{outcome}]")
    nodes = [";" + "".join(properties)]
    for move in moves:
        kind = str(move.get("kind") or "")
        color = "B" if move.get("color") == "black" else "W"
        if kind == "pass":
            nodes.append(f";{color}[]")
        elif kind == "move":
            col = int(move["col"])
            row = int(move["row"])
            point = chr(ord("a") + col) + chr(ord("a") + row)
            nodes.append(f";{color}[{point}]")
    return "(" + "".join(nodes) + ")\n"


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("]", "\\]")


def _result(result: str | None, reason: str | None, margin_half: int | None) -> str | None:
    if result == "black_win" and reason == "resign":
        return "B+R"
    if result == "white_win" and reason == "resign":
        return "W+R"
    if reason == "score" and result in {"black_win", "white_win"} and margin_half is not None:
        prefix = "B+" if result == "black_win" else "W+"
        return prefix + format_sgf_half(margin_half)
    return None
