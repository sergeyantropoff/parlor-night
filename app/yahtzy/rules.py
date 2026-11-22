"""Яцзы.

Верх — единицы до шестёрок, бонус 35, если там уже 63.
Низ — три и четыре одинаковых, фул-хаус 25, стриты 30 и 40, яцзы 50, шанс.
Вторая и следующие яцзы, когда клетка яцзы уже взята за 50, дают по 100
и закрывают подходящую клетку по правилам джокера.
За столом от двух до четырёх. У каждого три броска и тринадцать клеток.
"""

from __future__ import annotations

import json
import secrets
from collections import Counter
from typing import Any

UPPER = ("ones", "twos", "threes", "fours", "fives", "sixes")
LOWER = ("three", "four", "house", "small", "large", "yahtzy", "chance")
CATEGORIES = UPPER + LOWER
FACES = {"ones": 1, "twos": 2, "threes": 3, "fours": 4, "fives": 5, "sixes": 6}
UPPER_OF = {face: name for name, face in FACES.items()}
NAMES = {
    "ones": "Единицы",
    "twos": "Двойки",
    "threes": "Тройки",
    "fours": "Четвёрки",
    "fives": "Пятёрки",
    "sixes": "Шестёрки",
    "three": "Три одинаковых",
    "four": "Четыре одинаковых",
    "house": "Фул-хаус",
    "small": "Малый стрит",
    "large": "Большой стрит",
    "yahtzy": "Яцзы",
    "chance": "Шанс",
}
SACRIFICE = (
    "ones",
    "twos",
    "threes",
    "fours",
    "chance",
    "three",
    "fives",
    "four",
    "small",
    "sixes",
    "house",
    "large",
    "yahtzy",
)


def waiting(order: list[str] | None = None, variant: str = "classic") -> dict[str, Any]:
    del variant
    seats = list(order or ["white", "black"])
    _check_table(seats)
    return _shell(seats, "waiting")


def waiting_table(seat_keys: list[str], variant: str = "classic") -> dict[str, Any]:
    return waiting(seat_keys, variant)


def deal(
    order: list[str] | None = None,
    variant: str = "classic",
    purses: dict[str, int] | None = None,
) -> dict[str, Any]:
    del variant, purses
    seats = list(order or ["white", "black"])
    _check_table(seats)
    return _shell(seats, "play")


def deal_table(
    seat_keys: list[str],
    variant: str = "classic",
    purses: dict[str, int] | None = None,
) -> dict[str, Any]:
    return deal(seat_keys, variant, purses)


def dumps(state: dict[str, Any]) -> str:
    return json.dumps(state, ensure_ascii=False, separators=(",", ":"))


def loads(text: str) -> dict[str, Any]:
    state = json.loads(text)
    if not isinstance(state, dict) or state.get("kind") != "yahtzy":
        raise ValueError("Это не партия яцзы.")
    return state


def legal(state: dict[str, Any]) -> list[dict[str, Any]]:
    if state.get("result") or state.get("phase") != "play":
        return []
    actions: list[dict[str, Any]] = []
    if int(state.get("rolls_left") or 0) > 0:
        actions.append({"path": ["roll"], "notation": "Бросок"})
    if len(state.get("dice") or []) == 5:
        seat = str(state.get("to_move") or "")
        for category in _score_choices(state, seat):
            actions.append({"path": ["score", category], "notation": NAMES[category]})
    return actions


def apply(state: dict[str, Any], path: list[str]) -> dict[str, Any]:
    nxt = _copy(state)
    if nxt.get("result") or nxt.get("phase") != "play":
        raise ValueError("Сейчас ход сделать нельзя.")
    if not path:
        raise ValueError("Пустой ход.")
    head = str(path[0])
    if head == "roll":
        return _throw(nxt, [str(item) for item in path[1:]])
    if head == "dice":
        return _place(nxt, [str(item) for item in path[1:]])
    if head == "score" and len(path) == 2:
        return _write(nxt, str(path[1]))
    raise ValueError("Такого хода нет.")


def stored_path(path: list[str], after: dict[str, Any]) -> list[str]:
    if path and str(path[0]) == "roll":
        return ["dice", *[str(face) for face in after.get("dice") or []]]
    return [str(item) for item in path]


def label(before: dict[str, Any], after: dict[str, Any], path: list[str]) -> str:
    if not path:
        return ""
    head = str(path[0])
    if head == "dice":
        shown = " · ".join(str(item) for item in path[1:6])
        return f"Бросок {shown}" if shown else "Бросок"
    if head == "score" and len(path) == 2:
        seat = str(before.get("to_move") or "")
        category = str(path[1])
        value = int(((after.get("scores") or {}).get(seat) or {}).get(category) or 0)
        return f"{NAMES.get(category, category)}: {value}"
    return ""


def suggest(state: dict[str, Any], level: int = 3) -> list[str] | None:
    actions = legal(state)
    if not actions:
        return None
    rank = max(1, min(5, int(level)))
    dice = [int(item) for item in state.get("dice") or []]
    rolls = [item for item in actions if item["path"][0] == "roll"]
    if rolls and (not dice or _wants_another(state, dice, rank)):
        kept = [] if not dice else _kept(dice, rank)
        return ["roll", *[str(index) for index in kept]]
    scores = [item for item in actions if item["path"][0] == "score"]
    if not scores:
        return list(rolls[0]["path"])
    return _choose_score(state, scores, rank)


def leave(state: dict[str, Any], seat: str) -> dict[str, Any]:
    nxt = _copy(state)
    if nxt.get("result"):
        return nxt
    if seat not in _order(nxt):
        raise ValueError("За этим столом нет такого места.")
    others = [item for item in _order(nxt) if item != seat]
    nxt["phase"] = "done"
    nxt["reason"] = "left"
    nxt["result"] = f"{others[0]}_win" if len(others) == 1 else "draw"
    nxt["winners"] = others if len(others) == 1 else []
    nxt["line_text"] = "Вышел из-за стола."
    nxt["motion"] = None
    return nxt


def replay(initial: str, payloads: list[dict[str, Any]]) -> dict[str, Any]:
    state = loads(initial)
    for payload in payloads:
        if payload.get("leave"):
            state = leave(state, str(payload.get("seat") or state.get("to_move") or ""))
        else:
            raw = payload.get("path") or []
            state = apply(state, [str(item) for item in raw])
    return state


def chronicle(
    initial: str,
    payloads: list[dict[str, Any]],
    final: dict[str, Any] | None = None,
) -> dict[str, Any]:
    state = final if isinstance(final, dict) and final.get("kind") == "yahtzy" else replay(initial, payloads)
    result = str(state.get("result") or "")
    winner = result[:-4] if result.endswith("_win") else ""
    totals = {seat: _grand(state, seat) for seat in _order(state)}
    return {
        "done": bool(result),
        "winner": winner,
        "winners": [str(item) for item in state.get("winners") or ([winner] if winner else [])],
        "line": str(state.get("line_text") or ""),
        "reason": str(state.get("reason") or ""),
        "board": [],
        "pot": 0,
        "counts": totals,
        "last": {},
    }


def view(state: dict[str, Any], seat: str | None) -> dict[str, Any]:
    phase = str(state.get("phase") or "")
    actor = str(state.get("to_move") or "")
    yours = bool(seat) and seat == actor and phase == "play" and not state.get("result")
    dice = [int(item) for item in state.get("dice") or []]
    if phase == "waiting":
        message = "Ждём игроков."
    elif phase == "done":
        message = str(state.get("line_text") or "Партия окончена.")
    elif not dice:
        message = "Первый бросок из трёх."
    elif int(state.get("rolls_left") or 0) > 0:
        message = f"Кости {' · '.join(str(item) for item in dice)}. Можно перебросить или записать."
    else:
        message = f"Кости {' · '.join(str(item) for item in dice)}. Запишите в свободную клетку."
    actions = legal(state) if yours else []
    offers = []
    if yours and len(dice) == 5:
        joker = _joker(state, actor, dice)
        for item in actions:
            if item["path"][0] != "score":
                continue
            category = str(item["path"][1])
            offers.append(
                {
                    "category": category,
                    "points": _points(category, dice, joker=joker and category in LOWER),
                }
            )
    columns = []
    for key in _order(state):
        filled = _filled(state, key)
        upper = _upper_sum(filled)
        bonus = _upper_bonus(filled)
        chips = int((state.get("chips") or {}).get(key) or 0)
        lower = _lower_sum(filled)
        columns.append(
            {
                "key": key,
                "scores": {name: filled[name] for name in CATEGORIES if name in filled},
                "upper": upper,
                "bonus": bonus,
                "upper_total": upper + (bonus or 0),
                "lower": lower,
                "yahtzy_bonus": chips,
                "lower_total": lower + chips,
                "grand": upper + (bonus or 0) + lower + chips,
            }
        )
    picture = {
        "dice": dice,
        "rolls_left": int(state.get("rolls_left") or 0),
        "phase": phase,
        "actor": actor,
        "motion": state.get("motion") if isinstance(state.get("motion"), dict) else None,
        "columns": columns,
        "order": _order(state),
        "totals": {item["key"]: item["grand"] for item in columns},
        "choices": [item["category"] for item in offers],
        "offers": offers,
    }
    roster = [{"key": key, "count": len(_filled(state, key)), "folded": False} for key in _order(state)]
    return {
        "hand": [],
        "top": "",
        "color": None,
        "phase": phase,
        "roster": roster,
        "opponent_count": 0,
        "deck": int(state.get("rolls_left") or 0),
        "actions": actions,
        "message": message,
        "pot": 0,
        "shown": {},
        "board": [],
        "held": bool(dice),
        "yahtzy": picture,
    }


def _check_table(seats: list[str]) -> None:
    if len(seats) not in {2, 3, 4} or len(set(seats)) != len(seats):
        raise ValueError("В яцзы играют от двух до четырёх.")


def _shell(seats: list[str], phase: str) -> dict[str, Any]:
    return {
        "kind": "yahtzy",
        "variant": "classic",
        "phase": phase,
        "order": seats,
        "to_move": seats[0],
        "rolls_left": 3,
        "dice": [],
        "scores": {seat: {} for seat in seats},
        "chips": {seat: 0 for seat in seats},
        "motion": None,
        "result": None,
        "reason": None,
        "winners": [],
        "line_text": "",
    }


def _copy(state: dict[str, Any]) -> dict[str, Any]:
    return json.loads(dumps(state))


def _order(state: dict[str, Any]) -> list[str]:
    return [str(item) for item in state.get("order") or []]


def _filled(state: dict[str, Any], seat: str) -> dict[str, int]:
    raw = (state.get("scores") or {}).get(seat) or {}
    return {str(key): int(value) for key, value in raw.items()}


def _next(state: dict[str, Any], seat: str) -> str:
    order = _order(state)
    return order[(order.index(seat) + 1) % len(order)]


def _die() -> int:
    return secrets.randbelow(6) + 1


def _faces(values: list[str]) -> list[int]:
    if len(values) != 5:
        raise ValueError("На столе пять костей.")
    faces = []
    for item in values:
        try:
            face = int(item)
        except ValueError:
            raise ValueError("На кости нет такого числа.") from None
        if face not in range(1, 7):
            raise ValueError("На кости нет такого числа.")
        faces.append(face)
    return faces


def _keeps(raw: list[str], dice: list[int]) -> list[int]:
    kept: list[int] = []
    for item in raw:
        try:
            index = int(item)
        except ValueError:
            raise ValueError("Так кость отложить нельзя.") from None
        if index not in range(5) or index in kept:
            raise ValueError("Так кость отложить нельзя.")
        kept.append(index)
    if kept and len(dice) != 5:
        raise ValueError("Сначала бросьте все пять костей.")
    return kept


def _throw(state: dict[str, Any], raw: list[str]) -> dict[str, Any]:
    if int(state.get("rolls_left") or 0) <= 0:
        raise ValueError("Броски этого хода кончились.")
    dice = [int(item) for item in state.get("dice") or []]
    kept = _keeps(raw, dice)
    thrown = [_die() if index not in kept else dice[index] for index in range(5)]
    return _accept(state, thrown, kept)


def _place(state: dict[str, Any], raw: list[str]) -> dict[str, Any]:
    if int(state.get("rolls_left") or 0) <= 0:
        raise ValueError("Броски этого хода кончились.")
    return _accept(state, _faces(raw), [])


def _accept(state: dict[str, Any], thrown: list[int], kept: list[int]) -> dict[str, Any]:
    state["dice"] = thrown
    state["rolls_left"] = int(state["rolls_left"]) - 1
    state["motion"] = {"kind": "dice", "dice": thrown, "kept": kept}
    return state


def _write(state: dict[str, Any], category: str) -> dict[str, Any]:
    seat = str(state.get("to_move") or "")
    dice = [int(item) for item in state.get("dice") or []]
    if len(dice) != 5:
        raise ValueError("Сначала бросьте кости.")
    if category not in _score_choices(state, seat):
        raise ValueError("Эту клетку сейчас не записать.")
    joker = _joker(state, seat, dice)
    if joker and int((state.get("chips") or {}).get(seat) or 0) >= 0 and _box(state, seat, "yahtzy") == 50:
        state["chips"][seat] = int(state["chips"].get(seat) or 0) + 100
    state["scores"].setdefault(seat, {})[category] = _points(category, dice, joker=joker and category in LOWER)
    state["dice"] = []
    state["rolls_left"] = 3
    state["motion"] = None
    if all(len(_filled(state, key)) == len(CATEGORIES) for key in _order(state)):
        _finish(state)
    else:
        state["to_move"] = _next(state, seat)
    return state


def _box(state: dict[str, Any], seat: str, category: str) -> int | None:
    filled = _filled(state, seat)
    if category not in filled:
        return None
    return filled[category]


def _joker(state: dict[str, Any], seat: str, dice: list[int]) -> bool:
    return _five(dice) and _box(state, seat, "yahtzy") == 50


def _score_choices(state: dict[str, Any], seat: str) -> list[str]:
    filled = _filled(state, seat)
    open_boxes = [category for category in CATEGORIES if category not in filled]
    dice = [int(item) for item in state.get("dice") or []]
    if len(dice) != 5:
        return []
    if not _joker(state, seat, dice):
        return open_boxes
    upper = UPPER_OF[dice[0]]
    if upper not in filled:
        return [upper]
    lower = [category for category in LOWER if category not in filled]
    if lower:
        return lower
    return [category for category in UPPER if category not in filled]


def _points(category: str, dice: list[int], *, joker: bool) -> int:
    if joker and category in LOWER:
        if category == "house":
            return 25
        if category == "small":
            return 30
        if category == "large":
            return 40
        if category == "yahtzy":
            return 50
        return sum(dice)
    if category in FACES:
        face = FACES[category]
        return sum(item for item in dice if item == face)
    if category == "three":
        return sum(dice) if _kind(dice) >= 3 else 0
    if category == "four":
        return sum(dice) if _kind(dice) >= 4 else 0
    if category == "house":
        return 25 if _house(dice) else 0
    if category == "small":
        return 30 if _straight(dice) >= 4 else 0
    if category == "large":
        return 40 if _straight(dice) >= 5 else 0
    if category == "yahtzy":
        return 50 if _five(dice) else 0
    if category == "chance":
        return sum(dice)
    raise ValueError("Такой клетки на бланке нет.")


def _kind(dice: list[int]) -> int:
    return max(Counter(dice).values()) if dice else 0


def _five(dice: list[int]) -> bool:
    return len(dice) == 5 and len(set(dice)) == 1


def _house(dice: list[int]) -> bool:
    counts = sorted(Counter(dice).values())
    return counts == [2, 3]


def _straight(dice: list[int]) -> int:
    found = sorted(set(dice))
    best = run = 1
    for previous, current in zip(found, found[1:], strict=False):
        if current == previous + 1:
            run += 1
            best = max(best, run)
        else:
            run = 1
    return best


def _run_faces(dice: list[int]) -> set[int]:
    found = sorted(set(dice))
    if len(found) < 2:
        return set(found)
    best: list[int] = []
    current = [found[0]]
    for previous, face in zip(found, found[1:], strict=False):
        if face == previous + 1:
            current.append(face)
        else:
            if len(current) > len(best):
                best = current
            current = [face]
    if len(current) > len(best):
        best = current
    return set(best)


def _upper_sum(filled: dict[str, int]) -> int:
    return sum(int(filled.get(category) or 0) for category in UPPER if category in filled)


def _upper_bonus(filled: dict[str, int]) -> int | None:
    if _upper_sum(filled) >= 63:
        return 35
    if all(category in filled for category in UPPER):
        return 0
    return None


def _lower_sum(filled: dict[str, int]) -> int:
    return sum(int(filled.get(category) or 0) for category in LOWER if category in filled)


def _grand(state: dict[str, Any], seat: str) -> int:
    filled = _filled(state, seat)
    bonus = _upper_bonus(filled) or 0
    chips = int((state.get("chips") or {}).get(seat) or 0)
    return _upper_sum(filled) + bonus + _lower_sum(filled) + chips


def _finish(state: dict[str, Any]) -> None:
    totals = {seat: _grand(state, seat) for seat in _order(state)}
    best = max(totals.values())
    winners = [seat for seat, total in totals.items() if total == best]
    state["phase"] = "done"
    state["reason"] = "score"
    state["winners"] = winners
    if len(winners) == 1:
        state["result"] = f"{winners[0]}_win"
        state["line_text"] = f"Победа, {best} очков."
    else:
        state["result"] = "draw"
        state["line_text"] = f"Ничья, по {best} очков."


def _wants_another(state: dict[str, Any], dice: list[int], level: int) -> bool:
    if int(state.get("rolls_left") or 0) <= 0:
        return False
    if level <= 1:
        return secrets.randbelow(3) > 0
    if _five(dice) or _straight(dice) >= 5 or _house(dice):
        return False
    if _kind(dice) >= 4:
        return False
    if _straight(dice) >= 4 and level >= 4 and int(state["rolls_left"]) == 1:
        return False
    if _kind(dice) >= 3 and level < 5 and int(state["rolls_left"]) == 1:
        return False
    return True


def _kept(dice: list[int], level: int) -> list[int]:
    counts = Counter(dice)
    face, count = max(counts.items(), key=lambda item: (item[1], item[0]))
    if count >= 3 or (count >= 2 and level >= 2):
        return [index for index, value in enumerate(dice) if value == face]
    run = _run_faces(dice)
    if len(run) >= 4 or (len(run) >= 3 and level >= 3):
        return [index for index, value in enumerate(dice) if value in run]
    if level <= 1:
        return []
    highest = max(dice)
    return [dice.index(highest)]


def _choose_score(state: dict[str, Any], actions: list[dict[str, Any]], level: int) -> list[str]:
    seat = str(state.get("to_move") or "")
    dice = [int(item) for item in state.get("dice") or []]

    def worth(category: str) -> tuple[int, int]:
        points = _points(category, dice, joker=_joker(state, seat, dice) and category in LOWER)
        weight = SACRIFICE.index(category) if category in SACRIFICE else 0
        return points, -weight

    ranked = sorted(actions, key=lambda item: worth(str(item["path"][1])), reverse=True)
    best = ranked[0]
    category = str(best["path"][1])
    if _points(category, dice, joker=_joker(state, seat, dice) and category in LOWER) > 0:
        return [str(item) for item in best["path"]]
    order = list(SACRIFICE if level < 4 else SACRIFICE)
    open_boxes = {str(item["path"][1]) for item in actions}
    for name in order:
        if name in open_boxes:
            return ["score", name]
    return [str(item) for item in best["path"]]
