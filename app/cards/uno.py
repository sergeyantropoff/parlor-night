"""Короткое Уно на двоих: цвета, цифры, пропуск, прикуп двух и дикая карта."""

from __future__ import annotations

import hashlib
import json
import random
import secrets
from typing import Any

COLORS = "RYGB"
RANKS = "0123456789SD"


def _deck() -> list[str]:
    cards = [color + rank for color in COLORS for rank in RANKS]
    cards.extend(["W"] * 4)
    secrets.SystemRandom().shuffle(cards)
    return cards


def waiting() -> dict[str, Any]:
    return {"kind": "uno", "phase": "waiting", "to_move": "white", "result": None, "reason": None}


def waiting_table(seat_keys: list[str]) -> dict[str, Any]:
    return {
        "kind": "uno",
        "phase": "waiting",
        "order": list(seat_keys),
        "to_move": seat_keys[0],
        "result": None,
        "reason": None,
    }


def deal_table(seat_keys: list[str]) -> dict[str, Any]:
    if seat_keys == ["white", "black"]:
        return deal()
    deck = _deck()
    hands: dict[str, list[str]] = {}
    cursor = 0
    for key in seat_keys:
        hands[key] = deck[cursor : cursor + 7]
        cursor += 7
    rest = deck[cursor:]
    top = rest.pop()
    while top == "W" and rest:
        rest.insert(0, top)
        top = rest.pop()
    return {
        "kind": "uno",
        "phase": "play",
        "order": list(seat_keys),
        "direction": 1,
        "hands": hands,
        "deck": rest,
        "discard": [top],
        "color": top[0],
        "to_move": seat_keys[0],
        "result": None,
        "reason": None,
    }


def deal() -> dict[str, Any]:
    deck = _deck()
    white, black, rest = deck[:7], deck[7:14], deck[14:]
    top = rest.pop()
    while top == "W" and rest:
        rest.insert(0, top)
        top = rest.pop()
    return {
        "kind": "uno",
        "phase": "play",
        "hands": {"white": white, "black": black},
        "deck": rest,
        "discard": [top],
        "color": top[0],
        "to_move": "white",
        "result": None,
        "reason": None,
    }


def dumps(state: dict[str, Any]) -> str:
    return json.dumps(state, ensure_ascii=False, separators=(",", ":"))


def loads(text: str) -> dict[str, Any]:
    value = json.loads(text)
    if not isinstance(value, dict) or value.get("kind") != "uno":
        raise ValueError("Это не стол Уно.")
    return value


def _other(seat: str) -> str:
    return "black" if seat == "white" else "white"


def _order(state: dict[str, Any]) -> list[str]:
    order = state.get("order")
    if isinstance(order, list) and len(order) >= 2:
        return [str(item) for item in order]
    return ["white", "black"]


def _advance(state: dict[str, Any], seat: str, steps: int) -> str:
    order = _order(state)
    direction = -1 if int(state.get("direction") or 1) < 0 else 1
    index = order.index(seat) if seat in order else 0
    return order[(index + direction * steps) % len(order)]


def _roster(state: dict[str, Any]) -> list[dict[str, Any]]:
    if not state.get("order"):
        return []
    hands = state.get("hands") or {}
    waiting = state.get("phase") == "waiting"
    return [
        {"key": seat, "count": 0 if waiting else len(hands.get(seat, [])), "folded": False}
        for seat in _order(state)
    ]


def _is_wild(card: str) -> bool:
    return card == "W" or (len(card) >= 2 and card[0] == "W")


def _plain_wild(card: str) -> str:
    return "W" if _is_wild(card) else card


def _heal(state: dict[str, Any]) -> dict[str, Any]:
    """Дикая из сброса снова без цвета, а цвет стола — одна из четырёх букв."""
    nxt = json.loads(dumps(state))
    hands = nxt.get("hands") or {}
    for seat, cards in list(hands.items()):
        hands[seat] = [_plain_wild(str(card)) for card in cards]
    color = str(nxt.get("color") or "")
    if color not in COLORS:
        discard = list(nxt.get("discard") or [])
        top = str(discard[-1]) if discard else ""
        if len(top) >= 2 and top[0] == "W" and top[1] in COLORS:
            nxt["color"] = top[1]
        elif top[:1] in COLORS:
            nxt["color"] = top[0]
    return nxt


def _matches(card: str, top: str, color: str) -> bool:
    if _is_wild(card):
        return True
    return card[0] == color or (len(card) == 2 and len(top) >= 2 and card[1] == top[1] and card[0] in COLORS)


def _draw_from(state: dict[str, Any], count: int) -> list[str]:
    drawn: list[str] = []
    for _ in range(count):
        if not state["deck"]:
            keep = state["discard"][-1]
            pile = [_plain_wild(str(card)) for card in state["discard"][:-1]]
            seed = hashlib.sha256(" ".join(pile).encode()).digest()
            random.Random(seed).shuffle(pile)
            state["deck"] = pile
            state["discard"] = [keep]
        if not state["deck"]:
            break
        drawn.append(state["deck"].pop())
    return drawn


def legal(state: dict[str, Any]) -> list[dict[str, Any]]:
    state = _heal(state)
    if state.get("phase") != "play":
        return []
    seat = state["to_move"]
    top = state["discard"][-1]
    actions = []
    seen: set[tuple[str, ...]] = set()
    for card in state["hands"][seat]:
        if not _matches(card, top, state["color"]):
            continue
        if _is_wild(card):
            for color, title in (("R", "красную"), ("Y", "жёлтую"), ("G", "зелёную"), ("B", "синюю")):
                path = ("play", "W", color)
                if path in seen:
                    continue
                seen.add(path)
                actions.append({"path": ["play", "W", color], "notation": f"Дикая, {title}", "promotion": None})
        else:
            path = ("play", card)
            if path in seen:
                continue
            seen.add(path)
            actions.append({"path": ["play", card], "notation": f"Ход {card}", "promotion": None})
    actions.append({"path": ["draw", "1"], "notation": "Взять карту", "promotion": None})
    hand = state["hands"][seat]
    if len(hand) == 2 and state.get("uno_called") != seat:
        actions.append({"path": ["uno"], "notation": "УНО", "promotion": None})
    if len(hand) == 2:
        plays = [item for item in actions if item["path"][0] == "play"]
        actions.extend(
            {"path": [*item["path"], "uno"], "notation": item["notation"], "promotion": None}
            for item in plays
        )
    if _can_catch(state, str(seat)):
        actions.append({"path": ["catch"], "notation": "УНО", "promotion": None})
    return actions


def catch_target(state: dict[str, Any]) -> str:
    """Кого ловят на Уно: уже ушёл в одну карту или ходит, держа две и не сказав сам."""
    state = _heal(state)
    if state.get("phase") != "play":
        return ""
    exposed = str(state.get("exposed") or "")
    if exposed and exposed in _order(state):
        return exposed
    seat = str(state.get("to_move") or "")
    hand = list((state.get("hands") or {}).get(seat) or [])
    if len(hand) == 2 and state.get("uno_called") != seat:
        return seat
    return ""


def _can_catch(state: dict[str, Any], seat: str | None) -> bool:
    if not seat or seat not in _order(state):
        return False
    target = catch_target(state)
    return bool(target) and target != str(seat)


def _drop_window(state: dict[str, Any], seat: str) -> None:
    if state.get("exposed"):
        state["exposed"] = ""
    called = str(state.get("called_out") or "")
    if called and called != seat:
        state["called_out"] = ""


def _apply_catch(state: dict[str, Any], catcher: str) -> dict[str, Any]:
    nxt = json.loads(dumps(_heal(state)))
    target = catch_target(nxt)
    if not target or (catcher and catcher == target):
        raise ValueError("Сейчас Уно сказать не на кого.")
    if str(nxt.get("exposed") or "") == target:
        nxt["hands"][target].extend(_draw_from(nxt, 2))
        _remember(nxt, target, "miss")
        said = {str(item) for item in nxt.get("said") or []}
        said.discard(target)
        _keep_said(nxt, said)
        nxt["exposed"] = ""
        nxt["called_out"] = ""
        nxt["uno_called"] = None
        return nxt
    if str(nxt.get("called_out") or "") == target:
        raise ValueError("Уно уже сказано.")
    nxt["called_out"] = target
    return nxt


def _view_actions(state: dict[str, Any], seat: str | None) -> list[dict[str, Any]]:
    actions = legal(state) if seat and state.get("to_move") == seat else []
    if seat and state.get("to_move") != seat and _can_catch(state, seat):
        actions.append({"path": ["catch"], "notation": "УНО", "promotion": None})
    return actions


def _pile(state: dict[str, Any]) -> list[dict[str, Any]]:
    discard = [str(card) for card in (state.get("discard") or [])]
    tail = discard[-10:]
    start = len(discard) - len(tail)
    return [{"card": card, "n": start + index} for index, card in enumerate(tail)]


def _remember(state: dict[str, Any], seat: str, action: str) -> None:
    acts = dict(state.get("acts") or {})
    acts[seat] = action
    state["acts"] = acts


def _keep_said(state: dict[str, Any], said: set[str]) -> None:
    state["said"] = [item for item in _order(state) if item in said and len(state["hands"].get(item, [])) == 1]


def apply(state: dict[str, Any], path: list[str]) -> dict[str, Any]:
    path = list(path)
    if path and path[0] == "play" and len(path) >= 2 and path[1] != "W" and _is_wild(path[1]):
        named = path[1][1] if len(path[1]) > 1 and path[1][1] in COLORS else "R"
        path = ["play", "W", named, *path[2:]]
    healed = _heal(state)
    if path and path[0] == "catch":
        catcher = str(path[1]) if len(path) > 1 else ""
        return _apply_catch(healed, catcher)
    allowed = {tuple(item["path"]) for item in legal(healed)}
    if tuple(path) not in allowed:
        raise ValueError("Такой ход в Уно не принимается.")
    nxt = json.loads(dumps(healed))
    seat = nxt["to_move"]
    said = {str(item) for item in nxt.get("said") or []}
    calling = path[0] == "play" and path[-1] == "uno"
    if calling:
        path = path[:-1]
        nxt["uno_called"] = seat
        if str(nxt.get("called_out") or "") == seat:
            nxt["called_out"] = ""
    if path[0] == "uno":
        nxt["uno_called"] = seat
        if str(nxt.get("called_out") or "") == seat:
            nxt["called_out"] = ""
        _remember(nxt, seat, "uno")
        return nxt
    if path[0] == "draw":
        _drop_window(nxt, seat)
        nxt["called_out"] = ""
        nxt["hands"][seat].extend(_draw_from(nxt, 1))
        nxt["uno_called"] = None
        said.discard(seat)
        _remember(nxt, seat, "draw")
        _keep_said(nxt, said)
        nxt["to_move"] = _advance(nxt, seat, 1)
        return nxt
    _drop_window(nxt, seat)
    card = path[1]
    hand = list(nxt["hands"][seat])
    token = "W" if card == "W" else card
    hand.remove(token)
    nxt["hands"][seat] = hand
    if card == "W":
        color = path[2]
        nxt["discard"].append("W" + color)
        nxt["color"] = color
        nxt["to_move"] = _advance(nxt, seat, 1)
        _remember(nxt, seat, "wild")
    else:
        nxt["discard"].append(card)
        nxt["color"] = card[0]
        symbol = card[1]
        skipped = _advance(nxt, seat, 1)
        if symbol == "D":
            nxt["hands"][skipped].extend(_draw_from(nxt, 2))
            said.discard(skipped)
        nxt["to_move"] = _advance(nxt, seat, 2 if symbol in {"S", "V", "D"} else 1)
        _remember(nxt, seat, "skip" if symbol == "S" else "draw2" if symbol == "D" else "play")
    if not nxt["hands"][seat]:
        said.discard(seat)
        nxt["exposed"] = ""
        nxt["called_out"] = ""
        nxt["phase"] = "done"
        nxt["result"] = f"{seat}_win"
        nxt["reason"] = "empty_hand"
    elif len(nxt["hands"][seat]) == 1 and nxt.get("uno_called") == seat:
        said.add(seat)
        nxt["called_out"] = ""
    elif len(nxt["hands"][seat]) == 1 and str(nxt.get("called_out") or "") == seat:
        said.discard(seat)
        nxt["hands"][seat].extend(_draw_from(nxt, 2))
        _remember(nxt, seat, "miss")
        nxt["called_out"] = ""
        nxt["exposed"] = ""
    elif len(nxt["hands"][seat]) == 1:
        said.discard(seat)
        nxt["exposed"] = seat
        nxt["called_out"] = ""
    else:
        said.discard(seat)
        if str(nxt.get("called_out") or "") == seat:
            nxt["called_out"] = ""
    nxt["uno_called"] = None
    _keep_said(nxt, said)
    return nxt


def suggest(state: dict[str, Any], level: int = 5) -> list[str] | None:
    state = _heal(state)
    exposed = str(state.get("exposed") or "")
    if exposed and exposed != str(state.get("to_move") or ""):
        return ["catch"]
    actions = legal(state)
    if not actions:
        return None
    called = next((item for item in actions if item["path"] == ["uno"]), None)
    if called:
        return ["uno"]
    plays = [item for item in actions if item["path"][0] == "play"]
    if not plays:
        return list(actions[0]["path"])
    strength = max(1, min(5, level))
    if strength == 1:
        return list(random.choice(plays)["path"])
    seat = str(state["to_move"])
    hand = list(state.get("hands", {}).get(seat, []))
    color = str(state.get("color") or "")
    if strength == 2:
        plain = [item for item in plays if item["path"][1] != "W"]
        return list(random.choice(plain or plays)["path"])
    matching = [item for item in plays if item["path"][1] != "W" and item["path"][1][0] == color]
    if strength >= 4 and matching:
        numbers = [item for item in matching if item["path"][1][1] in "0123456789"]
        pool = numbers or matching
        return list(pool[-1]["path"])
    if matching:
        return list(matching[0]["path"])
    plain = [item for item in plays if item["path"][1] != "W"]
    if plain:
        return list(plain[0]["path"])
    wilds = [item for item in plays if item["path"][1] == "W"]
    if not wilds:
        return list(plays[0]["path"])
    counts: dict[str, int] = {}
    for card in hand:
        if card != "W" and card[0] in COLORS:
            counts[card[0]] = counts.get(card[0], 0) + 1
    best_color = max(COLORS, key=lambda item: counts.get(item, 0))
    chosen = next(item for item in wilds if item["path"][2] == best_color)
    return list(chosen["path"])


def leave(state: dict[str, Any], seat: str) -> dict[str, Any]:
    nxt = json.loads(dumps(state))
    if nxt.get("phase") == "done":
        return nxt
    if nxt.get("phase") == "waiting":
        nxt["phase"] = "done"
        nxt["reason"] = "left"
        return nxt
    nxt["phase"] = "done"
    nxt["result"] = f"{_advance(nxt, seat, 1)}_win"
    nxt["reason"] = "left"
    return nxt


def aligned(initial: str, payloads: list[dict[str, Any]], recorded: str) -> dict[str, Any]:
    """Повтор ходов, а если колода когда-то собралась заново случайно — сохранённая позиция."""
    state: dict[str, Any] | None
    try:
        state = replay(initial, payloads)
    except (TypeError, ValueError, KeyError):
        state = None
    if state is not None and dumps(state) == recorded:
        return state
    try:
        stored = loads(recorded)
    except (TypeError, ValueError, json.JSONDecodeError):
        stored = None
    if isinstance(stored, dict) and stored.get("kind") == "uno":
        return stored
    if state is not None:
        return state
    raise ValueError("запись карточной партии не сходится")


def chronicle(
    initial: str,
    payloads: list[dict[str, Any]],
    final: dict[str, Any] | None = None,
) -> dict[str, Any]:
    try:
        counts, last, played = _replay_counts(initial, payloads)
    except (TypeError, ValueError, KeyError):
        counts, last = _tally(loads(initial), payloads)
        played = None
    state = final if final is not None else played
    if state is None:
        state = loads(initial)
    result = str(state.get("result") or "")
    winner = result[:-4] if result.endswith("_win") else ""
    discard = list(state.get("discard") or [])
    reason = str(state.get("reason") or "")
    lines = {"empty_hand": "Карты закончились.", "left": "Игрок вышел из-за стола."}
    return {
        "done": state.get("phase") == "done",
        "winner": winner,
        "reason": reason,
        "line": lines.get(reason, "Партия окончена."),
        "pot": len(state.get("deck") or []),
        "board": [discard[-1]] if discard else [],
        "counts": counts,
        "hands": {str(key): list(value) for key, value in (state.get("hands") or {}).items()},
        "said": [str(item) for item in state.get("said") or []],
        "last": last,
    }


def _replay_counts(
    initial: str,
    payloads: list[dict[str, Any]],
) -> tuple[dict[str, int], dict[str, str], dict[str, Any]]:
    state = loads(initial)
    counts = {"play": 0, "draw": 0, "uno": 0, "wild": 0, "skip": 0, "draw2": 0, "miss": 0}
    last: dict[str, str] = {}
    for payload in payloads:
        if payload.get("leave"):
            seat = str(payload.get("seat") or state.get("to_move") or "white")
            state = leave(state, seat)
            last[seat] = "left"
            continue
        path = [str(item) for item in (payload.get("path") or [])]
        before = str(state.get("to_move") or "")
        if path and path[0] == "catch":
            target = str(state.get("exposed") or "")
            state = apply(state, path)
            if target and str((state.get("acts") or {}).get(target) or "") == "miss":
                counts["miss"] += 1
                last[target] = "miss"
            continue
        if path and path[0] == "play" and path[-1] == "uno":
            counts["uno"] += 1
        kind = _chronicle_kind(path)
        state = apply(state, path)
        if str((state.get("acts") or {}).get(before) or "") == "miss":
            kind = "miss"
        if kind:
            counts[kind] += 1
            last[before] = kind
    return counts, last, state


def _tally(start: dict[str, Any], payloads: list[dict[str, Any]]) -> tuple[dict[str, int], dict[str, str]]:
    counts = {"play": 0, "draw": 0, "uno": 0, "wild": 0, "skip": 0, "draw2": 0, "miss": 0}
    last: dict[str, str] = {}
    cursor = {
        "order": _order(start),
        "direction": start.get("direction") or 1,
        "to_move": str(start.get("to_move") or _order(start)[0]),
    }
    for payload in payloads:
        if payload.get("leave"):
            last[str(payload.get("seat") or cursor["to_move"])] = "left"
            continue
        path = [str(item) for item in (payload.get("path") or [])]
        seat = str(cursor["to_move"])
        if path and path[0] == "catch":
            continue
        if path and path[0] == "play" and path[-1] == "uno":
            counts["uno"] += 1
            path = path[:-1]
        kind = _chronicle_kind(path)
        if kind:
            counts[kind] += 1
            last[seat] = kind
        if not path or path[0] == "uno":
            continue
        steps = 1
        card = path[1] if path[0] == "play" and len(path) > 1 else ""
        if card not in {"", "W"} and len(card) > 1 and card[1] in {"S", "V", "D"}:
            steps = 2
        cursor["to_move"] = _advance(cursor, seat, steps)
    return counts, last


def _chronicle_kind(path: list[str]) -> str:
    if not path:
        return ""
    if path[0] in {"uno", "draw"}:
        return path[0]
    if path[0] != "play" or len(path) < 2:
        return ""
    card = path[1]
    if card == "W":
        return "wild"
    if len(card) > 1 and card[1] == "S":
        return "skip"
    if len(card) > 1 and card[1] == "D":
        return "draw2"
    return "play"


def replay(initial: str, payloads: list[dict[str, Any]]) -> dict[str, Any]:
    state = loads(initial)
    for payload in payloads:
        if payload.get("leave"):
            state = leave(state, str(payload.get("seat") or "white"))
            continue
        path = payload.get("path") or []
        state = apply(state, [str(item) for item in path])
    return state


def _by_color(cards: list[str]) -> list[str]:
    colors = {color: index for index, color in enumerate(COLORS)}
    ranks = {rank: index for index, rank in enumerate(RANKS)}

    def key(card: str) -> tuple[int, int, str]:
        if len(card) >= 2 and card[0] in colors:
            return (colors[card[0]], ranks.get(card[1], 99), card)
        return (len(COLORS), 0, card)

    return sorted(cards, key=key)


def view(state: dict[str, Any], seat: str | None) -> dict[str, Any]:
    state = _heal(state)
    phase = state.get("phase")
    raw = list(state.get("hands", {}).get(seat, [])) if seat and phase != "waiting" else []
    hand = _by_color(raw)
    discard = state.get("discard") or []
    names = {"R": "красный", "Y": "жёлтый", "G": "зелёный", "B": "синий", "W": "дикий"}
    color = names.get(str(state.get("color")), "")
    if phase == "waiting":
        message = "Ждём игроков за свободные места." if state.get("order") else "Ждём второго игрока."
    elif phase == "done":
        message = "Колода разыграна."
    else:
        message = f"Цвет стола: {color}."
    if seat and _can_catch(state, seat):
        message = f"{message} Можно сказать Уно."
    others = [item for item in _order(state) if item != seat]
    return {
        "hand": hand,
        "top": discard[-1] if discard else "",
        "pile": _pile(state),
        "color": state.get("color"),
        "phase": phase,
        "roster": _roster(state),
        "opponent_count": 0 if not seat else sum(len(state.get("hands", {}).get(item, [])) for item in others),
        "deck": len(state.get("deck") or []),
        "actions": _view_actions(state, seat),
        "message": message,
        "pot": 0,
        "shown": {},
        "acts": {str(key): str(value) for key, value in (state.get("acts") or {}).items()},
        "said": [str(item) for item in state.get("said") or []],
    }
