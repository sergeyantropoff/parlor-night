"""Домино в линию, набор double-six.

Двое получают по семь костей, трое и четверо — по пять. Остальное — базар.
Первым ходит тот, у кого старший дубль, и кладёт его. Если дублей нет,
ходит обладатель старшей кости и кладёт любую. Дальше кость ставят к открытому
концу с тем же числом. Нет подходящей — берут из базара, пока не появится ход
или базар не кончится. Кончился базар и ходить нечем — пас. Кто первым выложил
все кости, выиграл. Если пас обошёл стол, это рыба: победа у меньшей суммы очков.
Одинаковая меньшая сумма — ничья.
"""

from __future__ import annotations

import json
import secrets
from typing import Any

HAND = {2: 7, 3: 5, 4: 5}


def _pack() -> list[str]:
    return [f"{hi}-{lo}" for hi in range(6, -1, -1) for lo in range(hi, -1, -1)]


def _shuffled() -> list[str]:
    tiles = _pack()
    secrets.SystemRandom().shuffle(tiles)
    return tiles


def _split(tile: str) -> tuple[int, int]:
    hi, lo = tile.split("-", 1)
    return int(hi), int(lo)


def _pips(tile: str) -> int:
    hi, lo = _split(tile)
    return hi + lo


def _order(state: dict[str, Any]) -> list[str]:
    return [str(item) for item in state.get("order") or []]


def _next(state: dict[str, Any], seat: str) -> str:
    order = _order(state)
    return order[(order.index(seat) + 1) % len(order)]


def _lead(hands: dict[str, list[str]]) -> tuple[str, str, bool]:
    best: tuple[int, int, int] | None = None
    found = ("", "", False)
    for seat, hand in hands.items():
        for tile in hand:
            hi, lo = _split(tile)
            key = (1 if hi == lo else 0, hi if hi == lo else hi + lo, hi)
            if best is None or key > best:
                best = key
                found = (seat, tile, hi == lo)
    return found


def waiting(order: list[str] | None = None, variant: str = "draw") -> dict[str, Any]:
    seats = list(order or ["white", "black"])
    return _shell(seats, "waiting", variant)


def waiting_table(seat_keys: list[str], variant: str = "draw") -> dict[str, Any]:
    return waiting(seat_keys, variant)


def deal(
    order: list[str] | None = None,
    variant: str = "draw",
    purses: dict[str, int] | None = None,
    deck: list[str] | None = None,
) -> dict[str, Any]:
    del purses
    seats = list(order or ["white", "black"])
    if len(seats) not in HAND:
        raise ValueError("В домино играют от двух до четырёх игроков.")
    tiles = list(deck) if deck is not None else _shuffled()
    if sorted(tiles) != sorted(_pack()):
        raise ValueError("В наборе домино должно быть 28 костей.")
    size = HAND[len(seats)]
    hands = {seat: tiles[index * size : (index + 1) * size] for index, seat in enumerate(seats)}
    yard = tiles[len(seats) * size :]
    starter, tile, forced = _lead(hands)
    state = _shell(seats, "play", variant)
    state["hands"] = hands
    state["boneyard"] = yard
    state["to_move"] = starter
    state["must"] = tile if forced else ""
    return state


def deal_table(
    seat_keys: list[str],
    variant: str = "draw",
    purses: dict[str, int] | None = None,
) -> dict[str, Any]:
    return deal(seat_keys, variant, purses)


def _shell(seats: list[str], phase: str, variant: str) -> dict[str, Any]:
    del variant
    return {
        "kind": "domino",
        "variant": "draw",
        "phase": phase,
        "order": seats,
        "hands": {seat: [] for seat in seats},
        "boneyard": [],
        "line": [],
        "to_move": seats[0],
        "must": "",
        "passes": 0,
        "result": None,
        "reason": None,
        "line_text": "",
    }


def dumps(state: dict[str, Any]) -> str:
    return json.dumps(state, ensure_ascii=False, separators=(",", ":"))


def loads(text: str) -> dict[str, Any]:
    state = json.loads(text)
    if not isinstance(state, dict) or state.get("kind") != "domino":
        raise ValueError("Это не стол домино.")
    return state


def _ends(state: dict[str, Any]) -> tuple[int | None, int | None]:
    line = state.get("line") or []
    if not line:
        return None, None
    return int(line[0]["a"]), int(line[-1]["b"])


def _playable(tile: str, end: int) -> bool:
    hi, lo = _split(tile)
    return hi == end or lo == end


def legal(state: dict[str, Any]) -> list[dict[str, Any]]:
    if state.get("phase") != "play" or state.get("result"):
        return []
    seat = str(state.get("to_move") or "")
    hand = list(state.get("hands", {}).get(seat) or [])
    left, right = _ends(state)
    actions: list[dict[str, Any]] = []
    seen: set[tuple[str, ...]] = set()
    must = str(state.get("must") or "")
    if left is None:
        opening = [must] if must else hand
        for tile in opening:
            if tile not in hand:
                continue
            path = ("play", tile, "R")
            if path in seen:
                continue
            seen.add(path)
            actions.append({"path": ["play", tile, "R"], "notation": f"{_label(tile)} на стол", "promotion": None})
        return actions
    for tile in hand:
        if left is not None and _playable(tile, left):
            path = ("play", tile, "L")
            if path not in seen:
                seen.add(path)
                actions.append({"path": ["play", tile, "L"], "notation": f"{_label(tile)} влево", "promotion": None})
        if right is not None and _playable(tile, right):
            path = ("play", tile, "R")
            if path not in seen:
                seen.add(path)
                actions.append({"path": ["play", tile, "R"], "notation": f"{_label(tile)} вправо", "promotion": None})
    if actions:
        return actions
    if state.get("boneyard"):
        return [{"path": ["draw", "1"], "notation": "Взять из базара", "promotion": None}]
    return [{"path": ["pass", "1"], "notation": "Пас", "promotion": None}]


def _label(tile: str) -> str:
    hi, lo = _split(tile)
    return f"{hi}–{lo}"


def _lay(tile: str, end: int, *, left: bool) -> dict[str, int | str]:
    hi, lo = _split(tile)
    if hi != end and lo != end:
        raise ValueError("Кость не подходит к этому концу.")
    other = lo if hi == end else hi
    if left:
        return {"tile": tile, "a": other, "b": end}
    return {"tile": tile, "a": end, "b": other}


def _finish_block(state: dict[str, Any]) -> None:
    scores = {seat: sum(_pips(tile) for tile in state["hands"].get(seat) or []) for seat in _order(state)}
    best = min(scores.values())
    winners = [seat for seat, score in scores.items() if score == best]
    state["phase"] = "done"
    state["reason"] = "blocked"
    state["scores"] = scores
    if len(winners) == 1:
        state["result"] = f"{winners[0]}_win"
        state["line_text"] = ""
    else:
        state["result"] = "draw"
        state["line_text"] = "Рыба. Одинаковая сумма очков."


def apply(state: dict[str, Any], path: list[str]) -> dict[str, Any]:
    allowed = {tuple(item["path"]) for item in legal(state)}
    if tuple(path) not in allowed:
        raise ValueError("Такой ход в домино не принимается.")
    nxt = json.loads(dumps(state))
    seat = str(nxt["to_move"])
    if path[0] == "draw":
        nxt["hands"][seat].append(nxt["boneyard"].pop())
        nxt["passes"] = 0
        return nxt
    if path[0] == "pass":
        nxt["passes"] = int(nxt.get("passes") or 0) + 1
        if nxt["passes"] >= len(_order(nxt)):
            _finish_block(nxt)
            return nxt
        nxt["to_move"] = _next(nxt, seat)
        return nxt
    tile = path[1]
    side = path[2]
    hand = list(nxt["hands"][seat])
    hand.remove(tile)
    nxt["hands"][seat] = hand
    nxt["must"] = ""
    nxt["passes"] = 0
    if not nxt["line"]:
        hi, lo = _split(tile)
        nxt["line"] = [{"tile": tile, "a": hi, "b": lo}]
    else:
        left, right = _ends(nxt)
        end = left if side == "L" else right
        placed = _lay(tile, int(end), left=side == "L")
        if side == "L":
            nxt["line"].insert(0, placed)
        else:
            nxt["line"].append(placed)
    if not nxt["hands"][seat]:
        nxt["phase"] = "done"
        nxt["result"] = f"{seat}_win"
        nxt["reason"] = "empty"
        nxt["line_text"] = ""
        return nxt
    nxt["to_move"] = _next(nxt, seat)
    return nxt


def suggest(state: dict[str, Any], level: int = 3) -> list[str] | None:
    actions = legal(state)
    if not actions:
        return None
    plays = [item for item in actions if item["path"][0] == "play"]
    if not plays:
        return list(actions[0]["path"])
    strength = max(1, min(5, int(level)))
    if strength == 1:
        return list(secrets.choice(plays)["path"])
    seat = str(state.get("to_move") or "")
    hand = list(state.get("hands", {}).get(seat) or [])

    def rank(item: dict[str, Any]) -> tuple[int, int, int]:
        tile = str(item["path"][1])
        hi, lo = _split(tile)
        return (1 if len(hand) == 1 else 0, 1 if hi == lo else 0, hi + lo)

    plays.sort(key=rank)
    return list(plays[-1]["path"])


def leave(state: dict[str, Any], seat: str) -> dict[str, Any]:
    nxt = json.loads(dumps(state))
    if nxt.get("result"):
        return nxt
    others = [item for item in _order(nxt) if item != seat]
    nxt["phase"] = "done"
    nxt["reason"] = "left"
    nxt["result"] = f"{others[0]}_win" if len(others) == 1 else "draw"
    nxt["line_text"] = "Вышел из-за стола."
    return nxt


def replay(initial: str, payloads: list[dict[str, Any]]) -> dict[str, Any]:
    state = loads(initial)
    for payload in payloads:
        if payload.get("leave"):
            state = leave(state, str(payload.get("seat") or state.get("to_move") or "white"))
            continue
        path = payload.get("path") or []
        state = apply(state, [str(item) for item in path])
    return state


def chronicle(
    initial: str,
    payloads: list[dict[str, Any]],
    final: dict[str, Any] | None = None,
) -> dict[str, Any]:
    state = final if isinstance(final, dict) else replay(initial, payloads)
    result = str(state.get("result") or "")
    winner = result[:-4] if result.endswith("_win") else ""
    scores = state.get("scores") if isinstance(state.get("scores"), dict) else {}
    notes = {}
    for seat in _order(state):
        if scores:
            notes[seat] = f"{int(scores.get(seat) or 0)} очков"
        elif seat == winner:
            notes[seat] = "вышел"
        else:
            notes[seat] = f"{sum(_pips(tile) for tile in state.get('hands', {}).get(seat) or [])} очков"
    return {
        "done": bool(result),
        "winner": winner,
        "loser": "",
        "line": str(state.get("line_text") or ""),
        "reason": str(state.get("reason") or ""),
        "board": [str(item.get("tile") or "") for item in state.get("line") or []],
        "pot": 0,
        "counts": {"play": len(payloads)},
        "hands": {seat: list(cards) for seat, cards in (state.get("hands") or {}).items()} if result else {},
        "notes": notes,
        "last": {},
    }


def _sorted(hand: list[str]) -> list[str]:
    return sorted(hand, key=lambda tile: (_split(tile)[0] != _split(tile)[1], -_split(tile)[0], -_split(tile)[1], tile))


def _public_line(state: dict[str, Any]) -> list[dict[str, object]]:
    shown = []
    for item in state.get("line") or []:
        tile = str(item.get("tile") or "")
        hi, _lo = _split(tile)
        left = int(item.get("a"))
        right = int(item.get("b"))
        shown.append({"tile": tile, "spin": hi == left == right, "hi_left": left == hi})
    return shown


def view(state: dict[str, Any], seat: str | None) -> dict[str, Any]:
    phase = state.get("phase")
    hand = _sorted(list(state.get("hands", {}).get(seat, []))) if seat and phase != "waiting" else []
    left, right = _ends(state)
    if phase == "waiting":
        message = "Ждём игроков за свободные места."
    elif phase == "done":
        message = str(state.get("line_text") or "Партия окончена.")
    elif not state.get("line"):
        message = "Первый ход. Положите кость на стол."
    elif str(state.get("to_move") or "") == seat and not legal(state)[:1]:
        message = "Домино в линию."
    else:
        ends = f"{left} и {right}" if left != right else str(left)
        message = f"Открытые концы: {ends}."
    roster = [
        {"key": key, "count": len(state.get("hands", {}).get(key, [])), "folded": False}
        for key in _order(state)
    ]
    your_turn = bool(seat) and str(state.get("to_move") or "") == seat and phase == "play"
    return {
        "hand": hand,
        "top": "",
        "color": None,
        "phase": phase,
        "roster": roster,
        "opponent_count": sum(item["count"] for item in roster if item["key"] != seat),
        "deck": len(state.get("boneyard") or []),
        "actions": legal(state) if your_turn else [],
        "message": message,
        "pot": 0,
        "shown": {},
        "chain": _public_line(state),
        "board": [str(item.get("tile") or "") for item in state.get("line") or []],
    }
