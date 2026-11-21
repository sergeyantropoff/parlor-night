"""Длинные и короткие нарды.

Короткие — западные: шашки бьют блот, бар, дом и куб удвоения.
Оин, гэммон и бэкгэммон умножают текущую ставку.

Длинные — оба идут в одну сторону. Чужое поле закрыто даже одной шашкой.
С головы за ход снимается одна шашка, в первый ход — две.
Шесть полей четверти нельзя закрыть, пока соперник их не прошёл.
Оин, марс и кокс. Куба удвоения нет.

Поля 0…23. Снизу справа налево 0…11, сверху слева направо 12…23.
Белые в коротких идут от 23 к 0, чёрные от 0 к 23.
В длинных оба идут вперёд по своему кругу: белые с 0, чёрные с 12.
"""

from __future__ import annotations

import json
import random
import secrets
from typing import Any

WHITE = "white"
BLACK = "black"
VARIANTS = ("long", "short")


def waiting(order: list[str] | None = None, variant: str = "long") -> dict[str, Any]:
    seats = list(order or [WHITE, BLACK])
    state = _shell(seats, "waiting", _variant(variant))
    return state


def waiting_table(seat_keys: list[str], variant: str = "long") -> dict[str, Any]:
    return waiting(seat_keys, variant)


def deal(
    order: list[str] | None = None,
    variant: str = "long",
    purses: dict[str, int] | None = None,
) -> dict[str, Any]:
    del purses
    seats = list(order or [WHITE, BLACK])
    if seats[:2] != [WHITE, BLACK] or len(seats) != 2:
        raise ValueError("В нардах играют двое: белые и чёрные.")
    state = _shell(seats, "roll", _variant(variant))
    state["points"] = _opening(_variant(variant))
    return state


def deal_table(
    seat_keys: list[str],
    variant: str = "long",
    purses: dict[str, int] | None = None,
) -> dict[str, Any]:
    return deal(seat_keys, variant, purses)


def dumps(state: dict[str, Any]) -> str:
    return json.dumps(state, ensure_ascii=False, separators=(",", ":"))


def loads(text: str) -> dict[str, Any]:
    state = json.loads(text)
    if not isinstance(state, dict) or state.get("kind") != "nardy":
        raise ValueError("Это не стол нард.")
    return state


def legal(state: dict[str, Any]) -> list[dict[str, Any]]:
    if state.get("phase") == "waiting" or state.get("result"):
        return []
    phase = str(state.get("phase") or "")
    seat = str(state.get("to_move") or "")
    if phase == "answer":
        return [
            {"path": ["dice", "take"], "notation": "Принять удвоение"},
            {"path": ["dice", "drop"], "notation": "Отказаться"},
        ]
    if phase == "roll":
        actions = [{"path": ["dice", "roll"], "notation": "Бросок"}]
        if _may_double(state, seat):
            actions.insert(0, {"path": ["dice", "double"], "notation": "Удвоить"})
        return actions
    if phase != "move":
        return []
    found: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for seq in _sequences(state):
        if not seq:
            continue
        move = seq[0]
        key = (move[0], move[1], move[2])
        if key in seen:
            continue
        seen.add(key)
        src, die, dest, _hit = move
        found.append(
            {
                "path": ["move", _token(src), str(die)],
                "notation": _step_text(src, dest, die, bool(move[3])),
            }
        )
    return found


def apply(state: dict[str, Any], path: list[str], dice: tuple[int, int] | None = None) -> dict[str, Any]:
    nxt = _copy(state)
    if nxt.get("result") or nxt.get("phase") == "waiting":
        raise ValueError("Сейчас хода нет.")
    if len(path) < 2:
        raise ValueError("Такой ход не разобрать.")
    phase = str(nxt.get("phase") or "")
    if path[0] == "dice":
        action = path[1]
        if action == "roll":
            if phase != "roll":
                raise ValueError("Кости бросают в начале хода.")
            pair = dice
            if pair is None and len(path) >= 4:
                pair = (int(path[2]), int(path[3]))
            if pair is None:
                pair = (secrets.randbelow(6) + 1, secrets.randbelow(6) + 1)
            if not (1 <= pair[0] <= 6 and 1 <= pair[1] <= 6):
                raise ValueError("На кости выпадает от 1 до 6.")
            return _roll(nxt, pair)
        if action == "double":
            return _offer(nxt)
        if action == "take":
            return _take(nxt)
        if action == "drop":
            return _drop(nxt)
        raise ValueError("Такого действия с костями нет.")
    if path[0] != "move" or phase != "move" or len(path) < 3:
        raise ValueError("Сначала выберите шашку и кость.")
    src = _parse_src(path[1])
    try:
        die = int(path[2])
    except ValueError as exc:
        raise ValueError("Кость должна быть числом.") from exc
    for seq in _sequences(nxt):
        if not seq:
            continue
        move = seq[0]
        if move[0] == src and move[1] == die:
            _step(nxt, move)
            nxt["motion"] = {
                "kind": "checker",
                "seat": str(nxt.get("_actor") or state.get("to_move")),
                "from": _token(move[0]),
                "to": _token(move[2]),
                "hit": bool(move[3]),
            }
            nxt.pop("_actor", None)
            if int(nxt["off"][state["to_move"]]) >= 15:
                _award(nxt, str(state["to_move"]))
                return nxt
            if _sequences(nxt):
                nxt["phase"] = "move"
                return nxt
            _finish_turn(nxt)
            return nxt
    raise ValueError("Этот ход сейчас нельзя сделать.")


def stored_path(path: list[str], after: dict[str, Any]) -> list[str]:
    if list(path)[:2] == ["dice", "roll"]:
        rolled = [str(item) for item in after.get("dice") or []]
        if len(rolled) == 2:
            return ["dice", "roll", *rolled]
    return [str(item) for item in path]


def label(before: dict[str, Any], after: dict[str, Any], path: list[str]) -> str:
    del before
    if path[:2] == ["dice", "roll"]:
        dice = after.get("dice") or []
        if len(dice) == 2 and int(dice[0]) == int(dice[1]):
            text = f"Дубль {dice[0]}"
        elif len(dice) == 2:
            text = f"Кости {dice[0]} и {dice[1]}"
        else:
            text = "Бросок"
        motion = after.get("motion") or {}
        if motion.get("pass"):
            return f"{text}. Хода нет"
        return text
    if path[:2] == ["dice", "double"]:
        return "Удвоение"
    if path[:2] == ["dice", "take"]:
        return "Удвоение принято"
    if path[:2] == ["dice", "drop"]:
        return "Удвоение отклонено"
    motion = after.get("motion") or {}
    if motion.get("kind") == "checker":
        src = _parse_src(str(motion.get("from") or ""))
        dest = _parse_src(str(motion.get("to") or "off")) if motion.get("to") != "off" else "off"
        die = 0
        if len(path) >= 3 and path[0] == "move":
            die = int(path[2])
        return _step_text(src, dest, die, bool(motion.get("hit")))
    return ""


def suggest(state: dict[str, Any], level: int = 3) -> list[str] | None:
    phase = str(state.get("phase") or "")
    seat = str(state.get("to_move") or "")
    rank = max(1, min(5, int(level)))
    if phase == "answer":
        return ["dice", "drop"] if _should_drop(state, rank) else ["dice", "take"]
    if phase == "roll":
        if rank >= 4 and _may_double(state, seat) and _should_double(state, rank):
            return ["dice", "double"]
        return ["dice", "roll"]
    if phase != "move":
        return None
    sequences = [item for item in _sequences(state) if item]
    if not sequences:
        return None
    rng = random.Random()
    if rank <= 1:
        chosen = rng.choice(sequences)
    else:
        def score(seq: list[tuple[Any, ...]]) -> int:
            sample = _copy(state)
            for move in seq:
                _step(sample, move)
            return _value(sample, seat, rank)

        if rank == 2:
            chosen = max(sequences, key=score)
        else:
            ranked = sorted(sequences, key=score, reverse=True)
            band = ranked if rank >= 5 else ranked[: max(1, (len(ranked) + 2) // 3)]
            chosen = band[0] if rank >= 5 else rng.choice(band)
    src, die, _dest, _hit = chosen[0]
    return ["move", _token(src), str(die)]


def leave(state: dict[str, Any], seat: str) -> dict[str, Any]:
    nxt = _copy(state)
    if nxt.get("result"):
        return nxt
    if seat not in {WHITE, BLACK}:
        raise ValueError("За этими нардами нет такого места.")
    winner = _other(seat)
    nxt["result"] = f"{winner}_win"
    nxt["reason"] = "left" if nxt.get("phase") == "waiting" else "resign"
    nxt["score"] = int(nxt.get("cube") or 1)
    nxt["phase"] = "done"
    nxt["to_move"] = seat
    nxt["line_text"] = _win_line(nxt, winner)
    return nxt


def replay(initial: str, payloads: list[dict[str, Any]]) -> dict[str, Any]:
    state = loads(initial)
    for payload in payloads:
        if payload.get("leave"):
            state = leave(state, str(payload.get("seat") or ""))
        else:
            raw = payload.get("path") or []
            state = apply(state, [str(item) for item in raw])
    return state


def chronicle(
    initial: str,
    payloads: list[dict[str, Any]],
    final: dict[str, Any] | None = None,
) -> dict[str, Any]:
    state = final if isinstance(final, dict) and final.get("kind") == "nardy" else replay(initial, payloads)
    if not state.get("result"):
        return {"done": False, "line": "", "winner": "", "reason": ""}
    winner = str(state["result"]).removesuffix("_win")
    return {
        "done": True,
        "winner": winner,
        "reason": state.get("reason") or "",
        "line": str(state.get("line_text") or ""),
        "score": int(state.get("score") or 1),
        "counts": state.get("off") or {},
    }


def view(state: dict[str, Any], seat: str | None) -> dict[str, Any]:
    phase = str(state.get("phase") or "")
    actor = str(state.get("to_move") or "")
    yours = bool(seat) and seat == actor and phase in {"roll", "move", "answer"} and not state.get("result")
    off = state.get("off") or {}
    roster = [
        {"key": key, "count": 15 - int(off.get(key) or 0), "folded": False}
        for key in state.get("order") or [WHITE, BLACK]
    ]
    if phase == "waiting":
        message = "Ждём второго игрока."
    elif phase == "done":
        message = str(state.get("line_text") or "Партия окончена.")
    elif phase == "answer":
        message = "Соперник предлагает удвоить ставку."
    elif phase == "roll":
        message = "Можно удвоить ставку, затем бросить кости." if _may_double(state, actor) else "Бросьте кости."
    else:
        dice = state.get("dice") or []
        shown = " и ".join(str(item) for item in dice) if dice else ""
        message = f"Кости {shown}. Выберите шашку." if shown else "Выберите шашку."
    picture = {
        "variant": state.get("variant") or "long",
        "points": [int(item) for item in state.get("points") or [0] * 24],
        "bar": {
            WHITE: int((state.get("bar") or {}).get(WHITE) or 0),
            BLACK: int((state.get("bar") or {}).get(BLACK) or 0),
        },
        "off": {WHITE: int(off.get(WHITE) or 0), BLACK: int(off.get(BLACK) or 0)},
        "dice": [int(item) for item in state.get("dice") or []],
        "remaining": [int(item) for item in state.get("remaining") or []],
        "cube": int(state.get("cube") or 1),
        "cube_owner": str(state.get("cube_owner") or ""),
        "phase": phase,
        "offer": str(state.get("offer") or ""),
        "targets": _targets(state) if yours and phase == "move" else [],
        "motion": state.get("motion") if isinstance(state.get("motion"), dict) else None,
        "score": int(state.get("score") or 1),
    }
    return {
        "hand": [],
        "top": "",
        "color": None,
        "phase": phase,
        "roster": roster,
        "opponent_count": sum(item["count"] for item in roster if item["key"] != seat),
        "deck": 0,
        "actions": legal(state) if yours else [],
        "message": message,
        "pot": int(state.get("score") or 1) if phase == "done" else int(state.get("cube") or 1),
        "shown": {},
        "board": [],
        "nardy": picture,
    }


def _shell(seats: list[str], phase: str, variant: str) -> dict[str, Any]:
    return {
        "kind": "nardy",
        "variant": variant,
        "phase": phase,
        "order": seats,
        "points": [0] * 24,
        "bar": {WHITE: 0, BLACK: 0},
        "off": {WHITE: 0, BLACK: 0},
        "to_move": seats[0],
        "dice": [],
        "remaining": [],
        "head_left": 0,
        "debut": {WHITE: True, BLACK: True},
        "cube": 1,
        "cube_owner": "",
        "offer": "",
        "motion": None,
        "result": None,
        "reason": None,
        "score": 1,
        "line_text": "",
    }


def _variant(value: str) -> str:
    if value not in VARIANTS:
        raise ValueError("Выберите длинные или короткие нарды.")
    return value


def _opening(variant: str) -> list[int]:
    points = [0] * 24
    if variant == "long":
        points[0] = 15
        points[12] = -15
        return points
    points[23] = 2
    points[12] = 5
    points[7] = 3
    points[5] = 5
    points[0] = -2
    points[11] = -5
    points[16] = -3
    points[18] = -5
    return points


def _copy(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": "nardy",
        "variant": state.get("variant") or "long",
        "phase": state.get("phase"),
        "order": list(state.get("order") or [WHITE, BLACK]),
        "points": [int(item) for item in state.get("points") or [0] * 24],
        "bar": {
            WHITE: int((state.get("bar") or {}).get(WHITE) or 0),
            BLACK: int((state.get("bar") or {}).get(BLACK) or 0),
        },
        "off": {
            WHITE: int((state.get("off") or {}).get(WHITE) or 0),
            BLACK: int((state.get("off") or {}).get(BLACK) or 0),
        },
        "to_move": state.get("to_move") or WHITE,
        "dice": [int(item) for item in state.get("dice") or []],
        "remaining": [int(item) for item in state.get("remaining") or []],
        "head_left": int(state.get("head_left") or 0),
        "debut": {
            WHITE: bool((state.get("debut") or {}).get(WHITE, True)),
            BLACK: bool((state.get("debut") or {}).get(BLACK, True)),
        },
        "cube": int(state.get("cube") or 1),
        "cube_owner": str(state.get("cube_owner") or ""),
        "offer": str(state.get("offer") or ""),
        "motion": state.get("motion"),
        "result": state.get("result"),
        "reason": state.get("reason"),
        "score": int(state.get("score") or 1),
        "line_text": str(state.get("line_text") or ""),
    }


def _other(seat: str) -> str:
    return BLACK if seat == WHITE else WHITE


def _sign(seat: str) -> int:
    return 1 if seat == WHITE else -1


def _route(variant: str, seat: str) -> list[int]:
    if variant == "short":
        return list(range(23, -1, -1)) if seat == WHITE else list(range(24))
    if seat == WHITE:
        return list(range(24))
    return [*range(12, 24), *range(12)]


def _head(variant: str, seat: str) -> int | None:
    if variant != "long":
        return None
    return 0 if seat == WHITE else 12


def _token(point: Any) -> str:
    if point == "bar":
        return "bar"
    if point == "off":
        return "off"
    return str(int(point))


def _parse_src(token: str) -> Any:
    if token == "bar":
        return "bar"
    if token == "off":
        return "off"
    point = int(token)
    if not 0 <= point <= 23:
        raise ValueError("Такого поля на доске нет.")
    return point


def _may_double(state: dict[str, Any], seat: str) -> bool:
    if state.get("variant") != "short" or int(state.get("cube") or 1) >= 64:
        return False
    if str(state.get("phase") or "") != "roll" or state.get("result"):
        return False
    owner = str(state.get("cube_owner") or "")
    return owner in {"", seat}


def _offer(state: dict[str, Any]) -> dict[str, Any]:
    seat = str(state.get("to_move") or "")
    if not _may_double(state, seat):
        raise ValueError("Сейчас удвоить нельзя.")
    state["offer"] = seat
    state["to_move"] = _other(seat)
    state["phase"] = "answer"
    state["motion"] = {"kind": "double", "by": seat}
    return state


def _take(state: dict[str, Any]) -> dict[str, Any]:
    if state.get("phase") != "answer":
        raise ValueError("Удвоение сейчас не предложено.")
    seat = str(state.get("to_move") or "")
    doubler = str(state.get("offer") or "")
    state["cube"] = min(64, int(state.get("cube") or 1) * 2)
    state["cube_owner"] = seat
    state["offer"] = ""
    state["to_move"] = doubler or _other(seat)
    state["phase"] = "roll"
    state["motion"] = {"kind": "take", "cube": state["cube"]}
    return state


def _drop(state: dict[str, Any]) -> dict[str, Any]:
    if state.get("phase") != "answer":
        raise ValueError("Удвоение сейчас не предложено.")
    winner = str(state.get("offer") or _other(str(state.get("to_move") or "")))
    state["result"] = f"{winner}_win"
    state["reason"] = "drop"
    state["score"] = int(state.get("cube") or 1)
    state["phase"] = "done"
    state["offer"] = ""
    state["motion"] = {"kind": "drop"}
    state["line_text"] = _win_line(state, winner)
    return state


def _roll(state: dict[str, Any], pair: tuple[int, int]) -> dict[str, Any]:
    left, right = pair
    seat = str(state.get("to_move") or "")
    state["dice"] = [left, right]
    state["remaining"] = [left, left, left, left] if left == right else [left, right]
    if state.get("variant") == "long":
        state["head_left"] = 2 if state["debut"].get(seat) else 1
    else:
        state["head_left"] = 99
    state["motion"] = {"kind": "dice", "dice": [left, right], "pass": False}
    if _sequences(state):
        state["phase"] = "move"
        return state
    state["motion"]["pass"] = True
    _finish_turn(state)
    return state


def _finish_turn(state: dict[str, Any]) -> None:
    seat = str(state.get("to_move") or "")
    if seat in {WHITE, BLACK}:
        state["debut"][seat] = False
    state["to_move"] = _other(seat)
    state["phase"] = "roll"
    state["remaining"] = []
    state["head_left"] = 0


def _own(points: list[int], seat: str, point: int) -> int:
    return int(points[point]) * _sign(seat)


def _home(points: list[int], bar: dict[str, int], seat: str, variant: str) -> bool:
    if int(bar.get(seat) or 0):
        return False
    route = _route(variant, seat)
    house = set(route[18:])
    for point in range(24):
        if _own(points, seat, point) > 0 and point not in house:
            return False
    return True


def _sequences(state: dict[str, Any]) -> list[list[tuple[Any, ...]]]:
    if state.get("phase") not in {"roll", "move"} or state.get("result"):
        return []
    dice = [int(item) for item in state.get("remaining") or []]
    if not dice:
        return []
    seat = str(state.get("to_move") or "")
    variant = str(state.get("variant") or "long")
    best: list[list[tuple[Any, ...]]] = []
    best_len = -1
    nodes = 0

    def walk(
        points: list[int],
        bar: dict[str, int],
        off: dict[str, int],
        left: list[int],
        head: int,
        steps: list[tuple[Any, ...]],
    ) -> None:
        nonlocal best_len, best, nodes
        nodes += 1
        if nodes > 20000:
            return
        if len(steps) + len(left) < best_len:
            return
        options = _options(points, bar, off, left, head, seat, variant)
        if not options:
            if len(steps) > best_len:
                best_len = len(steps)
                best = [list(steps)]
            elif len(steps) == best_len:
                if len(best) < 240:
                    best.append(list(steps))
            return
        seen: set[tuple[Any, ...]] = set()
        for move in options:
            key = (move[0], move[1], move[2])
            if key in seen:
                continue
            seen.add(key)
            played = _pushed(points, bar, off, left, head, move, seat, variant)
            if played is None:
                continue
            walk(*played, steps + [move])

    walk(
        list(state["points"]),
        dict(state["bar"]),
        dict(state["off"]),
        dice,
        int(state.get("head_left") or 0),
        [],
    )
    if best_len <= 0:
        return []
    if best_len == 1 and len(set(dice)) > 1:
        larger = max(move[1] for seq in best for move in seq)
        best = [seq for seq in best if seq and seq[0][1] == larger]
    return [seq for seq in best if seq]


def _options(
    points: list[int],
    bar: dict[str, int],
    off: dict[str, int],
    dice: list[int],
    head: int,
    seat: str,
    variant: str,
) -> list[tuple[Any, ...]]:
    del off
    if not dice:
        return []
    found: list[tuple[Any, ...]] = []
    seen: set[tuple[Any, ...]] = set()
    values = sorted(set(dice), reverse=True)
    sources: list[Any]
    if int(bar.get(seat) or 0) > 0:
        sources = ["bar"]
    else:
        head_point = _head(variant, seat)
        sources = [point for point in range(24) if _own(points, seat, point) > 0]
        if head_point is not None and head <= 0:
            sources = [point for point in sources if point != head_point]
    for src in sources:
        for die in values:
            move = _aim(points, bar, src, die, seat, variant)
            if move is None:
                continue
            key = (move[0], move[1], move[2])
            if key in seen:
                continue
            trial = _pushed(points, bar, {"white": 0, "black": 0}, dice, head, move, seat, variant)
            if trial is None:
                continue
            seen.add(key)
            found.append(move)
    return found


def _aim(
    points: list[int],
    bar: dict[str, int],
    src: Any,
    die: int,
    seat: str,
    variant: str,
) -> tuple[Any, ...] | None:
    route = _route(variant, seat)
    if src == "bar":
        if int(bar.get(seat) or 0) <= 0 or not 1 <= die <= 6:
            return None
        dest = route[die - 1]
        landed = _land(points, dest, seat, variant)
        if landed is None:
            return None
        return ("bar", die, dest, landed)
    index = route.index(int(src))
    nxt = index + die
    if nxt < 24:
        dest = route[nxt]
        landed = _land(points, dest, seat, variant)
        if landed is None:
            return None
        return (int(src), die, dest, landed)
    if not _home(points, bar, seat, variant):
        return None
    if nxt > 24 and any(_own(points, seat, route[pos]) > 0 for pos in range(index)):
        return None
    return (int(src), die, "off", False)


def _land(points: list[int], dest: int, seat: str, variant: str) -> bool | None:
    other = _own(points, _other(seat), dest)
    if other <= 0:
        return False
    if variant == "long" or other >= 2:
        return None
    return True


def _pushed(
    points: list[int],
    bar: dict[str, int],
    off: dict[str, int],
    dice: list[int],
    head: int,
    move: tuple[Any, ...],
    seat: str,
    variant: str,
) -> tuple[list[int], dict[str, int], dict[str, int], list[int], int] | None:
    src, die, dest, hit = move
    if die not in dice:
        return None
    sign = _sign(seat)
    nxt_points = list(points)
    nxt_bar = dict(bar)
    nxt_off = dict(off)
    nxt_dice = list(dice)
    nxt_dice.remove(die)
    nxt_head = head
    head_point = _head(variant, seat)
    if src == "bar":
        nxt_bar[seat] = int(nxt_bar.get(seat) or 0) - 1
    else:
        nxt_points[int(src)] -= sign
        if head_point is not None and int(src) == head_point:
            if nxt_head <= 0:
                return None
            nxt_head -= 1
    if dest == "off":
        nxt_off[seat] = int(nxt_off.get(seat) or 0) + 1
    else:
        if hit:
            nxt_bar[_other(seat)] = int(nxt_bar.get(_other(seat)) or 0) + 1
            nxt_points[int(dest)] = sign
        else:
            nxt_points[int(dest)] += sign
    if variant == "long" and _prime(nxt_points, nxt_bar, seat):
        return None
    return nxt_points, nxt_bar, nxt_off, nxt_dice, nxt_head


def _prime(points: list[int], bar: dict[str, int], seat: str) -> bool:
    opponent = _other(seat)
    route = _route("long", opponent)
    sign = _sign(seat)
    for start in (0, 6, 12, 18):
        if not all(int(points[point]) * sign > 0 for point in range(start, start + 6)):
            continue
        last = max(route.index(point) for point in range(start, start + 6))
        if int(bar.get(opponent) or 0) > 0:
            return True
        for point in range(24):
            if _own(points, opponent, point) > 0 and route.index(point) <= last:
                return True
    return False


def _step(state: dict[str, Any], move: tuple[Any, ...]) -> None:
    seat = str(state.get("to_move") or "")
    variant = str(state.get("variant") or "long")
    state["_actor"] = seat
    played = _pushed(
        state["points"],
        state["bar"],
        state["off"],
        state["remaining"],
        int(state.get("head_left") or 0),
        move,
        seat,
        variant,
    )
    if played is None:
        raise ValueError("Этот ход сейчас нельзя сделать.")
    points, bar, off, dice, head = played
    state["points"] = points
    state["bar"] = bar
    state["off"] = off
    state["remaining"] = dice
    state["head_left"] = head


def _targets(state: dict[str, Any]) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for seq in _sequences(state):
        if not seq:
            continue
        src, die, dest, hit = seq[0]
        key = (src, die, dest)
        if key in seen:
            continue
        seen.add(key)
        found.append({"from": _token(src), "die": die, "to": _token(dest), "hit": bool(hit)})
    return found


def _award(state: dict[str, Any], seat: str) -> None:
    opponent = _other(seat)
    cube = int(state.get("cube") or 1)
    if state.get("variant") == "long":
        if int(state["off"].get(opponent) or 0) > 0:
            reason, mult = "oin", 1
        elif _still_home(state, opponent):
            reason, mult = "cox", 3
        else:
            reason, mult = "mars", 2
    elif int(state["off"].get(opponent) or 0) > 0:
        reason, mult = "single", 1
    elif _backgammon(state, seat, opponent):
        reason, mult = "backgammon", 3
    else:
        reason, mult = "gammon", 2
    state["result"] = f"{seat}_win"
    state["reason"] = reason
    state["score"] = cube * mult
    state["phase"] = "done"
    state["line_text"] = _win_line(state, seat)


def _still_home(state: dict[str, Any], seat: str) -> bool:
    route = _route("long", seat)
    house = set(route[:6])
    for point in range(24):
        if _own(state["points"], seat, point) > 0 and point not in house:
            return False
    return int(state["off"].get(seat) or 0) == 0


def _backgammon(state: dict[str, Any], winner: str, loser: str) -> bool:
    if int(state["bar"].get(loser) or 0) > 0:
        return True
    house = set(_route(str(state.get("variant") or "short"), winner)[18:])
    return any(point in house and _own(state["points"], loser, point) > 0 for point in range(24))


def _win_line(state: dict[str, Any], winner: str) -> str:
    who = "белых" if winner == WHITE else "чёрных"
    reason = str(state.get("reason") or "")
    names = {
        "single": "Все шашки сняты",
        "oin": "Все шашки сняты",
        "gammon": "Гэммон",
        "backgammon": "Бэкгэммон",
        "mars": "Марс",
        "cox": "Кокс",
        "drop": "Удвоение не принято",
        "resign": "Соперник сдался",
        "left": "Соперник вышел из-за стола",
    }
    title = names.get(reason, "Партия окончена")
    score = int(state.get("score") or 1)
    stake = f" Счёт партии — {score}." if score > 1 else ""
    return f"{title}. Победа {who}.{stake}"


def _step_text(src: Any, dest: Any, die: int, hit: bool) -> str:
    del die
    if src == "bar":
        where = "в дом" if dest == "off" else f"на поле {int(dest) + 1}"
        return f"С бара {where}"
    start = f"Поле {int(src) + 1}"
    if dest == "off":
        text = f"Снятие с поля {int(src) + 1}"
    else:
        text = f"{start} → поле {int(dest) + 1}"
    if hit:
        text += ", бой"
    return text


def _pips(state: dict[str, Any], seat: str) -> int:
    variant = str(state.get("variant") or "long")
    route = _route(variant, seat)
    total = int(state["bar"].get(seat) or 0) * 25
    for point in range(24):
        count = _own(state["points"], seat, point)
        if count > 0:
            total += count * (24 - route.index(point))
    return total


def _value(state: dict[str, Any], seat: str, level: int) -> int:
    opponent = _other(seat)
    score = (_pips(state, opponent) - _pips(state, seat)) * 3
    score += int(state["off"].get(seat) or 0) * 18
    score -= int(state["off"].get(opponent) or 0) * 18
    score -= int(state["bar"].get(seat) or 0) * 45
    score += int(state["bar"].get(opponent) or 0) * 30
    if state.get("variant") == "short":
        blot_weight = 8 if level < 4 else 15
        score -= _blots(state, seat) * blot_weight
        score += _blots(state, opponent) * (blot_weight - 3)
        score += _anchors(state, seat) * 5
    else:
        score += _anchors(state, seat) * 2
    if int(state["off"].get(seat) or 0) >= 15:
        score += 1000
    return score


def _blots(state: dict[str, Any], seat: str) -> int:
    return sum(1 for point in range(24) if _own(state["points"], seat, point) == 1)


def _anchors(state: dict[str, Any], seat: str) -> int:
    return sum(1 for point in range(24) if _own(state["points"], seat, point) >= 2)


def _should_double(state: dict[str, Any], level: int) -> bool:
    seat = str(state.get("to_move") or "")
    lead = _pips(state, _other(seat)) - _pips(state, seat)
    return lead > 12 + (5 - level) * 8 and int(state.get("cube") or 1) < 32


def _should_drop(state: dict[str, Any], level: int) -> bool:
    if level <= 2:
        return False
    seat = str(state.get("to_move") or "")
    behind = _pips(state, seat) - _pips(state, _other(seat))
    return behind > 36
