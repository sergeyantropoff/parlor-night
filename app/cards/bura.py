"""Бура на двоих: 20 карт, три на руке, козырь снизу колоды."""

from __future__ import annotations

import json
from itertools import combinations
from typing import Any

from app.cards.deck import SUIT_NAME, label, pack

RANKS = "TJQKA"
BEATING = "JQKTA"
POINTS = {"A": 11, "T": 10, "K": 4, "Q": 3, "J": 2}
HAND = 3


def deal(
    order: list[str] | None = None,
    variant: str = "classic",
    purses: dict[str, int] | None = None,
) -> dict[str, Any]:
    del variant, purses
    seats = list(order or ["white", "black"])
    if len(seats) != 2:
        raise ValueError("В буру играют двое игроков.")
    deck = pack(RANKS)
    trump_card = deck[0]
    hands = {seat: [] for seat in seats}
    leader = seats[1]
    for _ in range(HAND):
        for seat in (leader, seats[0]):
            hands[seat].append(deck.pop())
    return _fresh(seats, hands, deck, trump_card, leader)


def deal_table(order: list[str], variant: str = "classic", purses: dict[str, int] | None = None) -> dict[str, Any]:
    return deal(order, variant, purses)


def waiting(order: list[str], variant: str = "classic") -> dict[str, Any]:
    seats = list(order)
    return {
        "kind": "bura",
        "phase": "waiting",
        "variant": variant,
        "order": seats,
        "hands": {seat: [] for seat in seats},
        "deck": [],
        "trump": "",
        "trump_card": "",
        "table": [],
        "tricks": {seat: [] for seat in seats},
        "scores": {seat: 0 for seat in seats},
        "to_move": seats[0] if seats else "white",
        "result": None,
        "reason": None,
        "line": "",
        "previous": {},
    }


def waiting_table(order: list[str], variant: str = "classic") -> dict[str, Any]:
    return waiting(order, variant)


def dumps(state: dict[str, Any]) -> str:
    return json.dumps(state, ensure_ascii=False, separators=(",", ":"))


def loads(text: str) -> dict[str, Any]:
    loaded = json.loads(text)
    if not isinstance(loaded, dict) or loaded.get("kind") != "bura":
        raise ValueError("Это не партия буры.")
    return loaded


def legal(state: dict[str, Any]) -> list[dict[str, Any]]:
    if state.get("result") or state.get("phase") not in {"lead", "answer"}:
        return []
    seat = str(state.get("to_move") or "")
    hand = list((state.get("hands") or {}).get(seat) or [])
    if state.get("phase") == "lead":
        return [_play(cards) for cards in _lead_groups(hand)]
    attack = [str(card) for card in state.get("table") or []]
    moves = [
        _play(list(cards))
        for size in (len(attack),)
        for cards in combinations(hand, size)
        if _covers(attack, list(cards), str(state.get("trump") or ""))
    ]
    moves.append({"path": ["act", "pass"], "notation": "Не бить", "promotion": None})
    return moves


def apply(state: dict[str, Any], path: list[str]) -> dict[str, Any]:
    if state.get("result"):
        raise ValueError("Партия уже окончена.")
    if state.get("phase") not in {"lead", "answer"}:
        raise ValueError("Сейчас ходить нельзя.")
    nxt = json.loads(dumps(state))
    seat = str(nxt["to_move"])
    other = _other(nxt, seat)
    if path and path[0] == "act" and path[1:] == ["pass"]:
        if nxt["phase"] != "answer":
            raise ValueError("Сейчас карты не бьют.")
        _take(nxt, other, list(nxt["table"]), [])
        _refill(nxt, other, seat)
        return nxt
    if not path or path[0] != "play" or len(path) < 2:
        raise ValueError("Такой ход не подходит.")
    cards = [str(card) for card in path[1:]]
    hand = list(nxt["hands"][seat])
    for card in cards:
        if card not in hand:
            raise ValueError("Этой карты нет на руке.")
        hand.remove(card)
    if nxt["phase"] == "lead":
        if len({card[1] for card in cards}) != 1:
            raise ValueError("Ходят картами одной масти.")
        nxt["hands"][seat] = hand
        nxt["table"] = cards
        nxt["phase"] = "answer"
        nxt["to_move"] = other
        if not nxt["hands"][other]:
            _take(nxt, seat, cards, [])
            _refill(nxt, seat, other)
        return nxt
    attack = [str(card) for card in nxt["table"]]
    if not _covers(attack, cards, str(nxt.get("trump") or "")):
        raise ValueError("Этими картами не побить.")
    nxt["hands"][seat] = hand
    _take(nxt, seat, attack, cards)
    _refill(nxt, seat, other)
    return nxt


def suggest(state: dict[str, Any], level: int) -> list[str]:
    actions = legal(state)
    if not actions:
        return []
    if state.get("phase") == "lead":
        singles = [item for item in actions if len(item["path"]) == 2]
        pool = singles or actions

        def lead_cost(item: dict[str, Any]) -> tuple[int, int]:
            card = str(item["path"][1])
            trump_cost = 0 if card[1] != state.get("trump") else 100
            return (trump_cost, _rank(card))

        return list(min(pool, key=lead_cost)["path"])
    beats = [item for item in actions if item["path"][0] == "play"]
    passed = next(item for item in actions if item["path"][1:] == ["pass"])
    if not beats:
        return list(passed["path"])
    trump = str(state.get("trump") or "")
    attack = [str(card) for card in state.get("table") or []]

    def beat_cost(item: dict[str, Any]) -> tuple[int, int]:
        cards = [str(card) for card in item["path"][1:]]
        spent = sum(1 for card in cards if card[1] == trump and card[1] not in {one[1] for one in attack})
        return (spent, sum(_rank(card) for card in cards))

    chosen = min(beats, key=beat_cost)
    if level <= 1 and beat_cost(chosen)[0] and _points(attack) < 11:
        return list(passed["path"])
    return list(chosen["path"])


def leave(state: dict[str, Any], seat: str) -> dict[str, Any]:
    nxt = json.loads(dumps(state))
    if nxt.get("result"):
        return nxt
    others = [item for item in nxt["order"] if item != seat]
    nxt["phase"] = "done"
    nxt["hands"][seat] = []
    nxt["reason"] = "left"
    nxt["result"] = f"{others[0]}_win" if others else "draw"
    nxt["line"] = "Вышел из-за стола."
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


def chronicle(initial: str, payloads: list[dict[str, Any]], final: dict[str, Any] | None = None) -> dict[str, Any]:
    state = final if isinstance(final, dict) else replay(initial, payloads)
    result = str(state.get("result") or "")
    winner = result[:-4] if result.endswith("_win") else ""
    scores = state.get("scores") if isinstance(state.get("scores"), dict) else {}
    return {
        "done": bool(result),
        "winner": winner,
        "loser": "",
        "line": str(state.get("line") or ""),
        "reason": str(state.get("reason") or ""),
        "board": [],
        "pot": 0,
        "counts": {str(key): int(value) for key, value in scores.items()},
        "hands": state.get("hands") if result else {},
        "notes": [],
    }


def view(state: dict[str, Any], seat: str | None) -> dict[str, Any]:
    you = seat if seat in (state.get("hands") or {}) else str(state.get("to_move") or "white")
    hand = _sorted(list((state.get("hands") or {}).get(you) or []), str(state.get("trump") or ""))
    trump = str(state.get("trump") or "")
    deck = list(state.get("deck") or [])
    phase = str(state.get("phase") or "")
    actions = legal(state) if phase in {"lead", "answer"} and not state.get("result") else []
    if state.get("result"):
        message = str(state.get("line") or "Партия окончена.")
    elif phase == "answer":
        if any(item["path"][0] == "play" for item in actions):
            message = "Нажмите карты, которыми бьёте, или «Не бить»."
        else:
            message = "Этими картами побить нельзя. Нажмите «Не бить»."
    elif phase == "waiting":
        message = "Ждём второго игрока."
    else:
        message = "Нажмите карты одной масти — они лягут на стол."
    if trump and not state.get("result"):
        message = f"Козырь — {SUIT_NAME.get(trump, trump)}. {message}"
    other = _other(state, you) if you in (state.get("order") or []) else ""
    return {
        "hand": hand,
        "pairs": [{"attack": str(card), "defense": ""} for card in state.get("table") or []],
        "trump": trump,
        "trump_card": str(deck[0]) if deck else "",
        "deck": len(deck),
        "phase": phase,
        "roster": [
            {"key": key, "count": len((state.get("hands") or {}).get(key) or []), "folded": False}
            for key in state.get("order") or []
        ],
        "message": message,
        "actions": actions,
        "previous": state.get("previous") if isinstance(state.get("previous"), dict) else {},
        "scores": {str(key): int(value) for key, value in (state.get("scores") or {}).items()},
        "opponent_count": len((state.get("hands") or {}).get(other) or []),
        "pot": 0,
    }


def _fresh(
    seats: list[str],
    hands: dict[str, list[str]],
    deck: list[str],
    trump_card: str,
    leader: str,
) -> dict[str, Any]:
    return {
        "kind": "bura",
        "phase": "lead",
        "variant": "classic",
        "order": seats,
        "hands": hands,
        "deck": deck,
        "trump": trump_card[1],
        "trump_card": trump_card,
        "table": [],
        "tricks": {seat: [] for seat in seats},
        "scores": {seat: 0 for seat in seats},
        "to_move": leader,
        "result": None,
        "reason": None,
        "line": "",
        "previous": {},
    }


def _other(state: dict[str, Any], seat: str) -> str:
    order = [str(item) for item in state.get("order") or []]
    rest = [item for item in order if item != seat]
    return rest[0] if rest else seat


def _rank(card: str) -> int:
    return BEATING.index(card[0])


def _points(cards: list[str]) -> int:
    return sum(POINTS.get(card[0], 0) for card in cards)


def _sorted(cards: list[str], trump: str) -> list[str]:
    return sorted(cards, key=lambda card: (card[1] != trump, card[1], -_rank(card)))


def _lead_groups(hand: list[str]) -> list[list[str]]:
    by_suit: dict[str, list[str]] = {}
    for card in hand:
        by_suit.setdefault(card[1], []).append(card)
    groups: list[list[str]] = []
    for cards in by_suit.values():
        for size in range(1, len(cards) + 1):
            groups.extend(list(combo) for combo in combinations(cards, size))
    return groups


def _beats(card: str, other: str, trump: str) -> bool:
    if card[1] == other[1]:
        return _rank(card) > _rank(other)
    return card[1] == trump and other[1] != trump


def _covers(attack: list[str], defense: list[str], trump: str) -> bool:
    if len(attack) != len(defense) or not attack:
        return False
    used = [False] * len(defense)

    def walk(index: int) -> bool:
        if index == len(attack):
            return True
        for place, card in enumerate(defense):
            if used[place] or not _beats(card, attack[index], trump):
                continue
            used[place] = True
            if walk(index + 1):
                return True
            used[place] = False
        return False

    return walk(0)


def _play(cards: list[str]) -> dict[str, Any]:
    return {
        "path": ["play", *cards],
        "notation": ", ".join(label(card) for card in cards),
        "promotion": None,
    }


def _take(state: dict[str, Any], seat: str, attack: list[str], defense: list[str]) -> None:
    pile = [*attack, *defense]
    state["tricks"][seat].extend(pile)
    state["scores"][seat] = _points(state["tricks"][seat])
    state["previous"] = {
        "kind": "take",
        "seat": seat,
        "pairs": [
            {"attack": attack[index], "defense": defense[index] if index < len(defense) else ""}
            for index in range(len(attack))
        ],
    }
    state["table"] = []


def _refill(state: dict[str, Any], first: str, second: str) -> None:
    for seat in (first, second):
        while len(state["hands"][seat]) < HAND and state["deck"]:
            state["hands"][seat].append(state["deck"].pop())
    state["table"] = []
    state["phase"] = "lead"
    if state["hands"][first]:
        state["to_move"] = first
        return
    if state["hands"][second]:
        state["to_move"] = second
        return
    _finish(state)


def _finish(state: dict[str, Any]) -> None:
    order = [str(seat) for seat in state["order"]]
    scores = {seat: _points(state["tricks"][seat]) for seat in order}
    state["scores"] = scores
    state["phase"] = "done"
    state["table"] = []
    state["reason"] = "points"
    shown = " — ".join(str(scores[seat]) for seat in order)
    best = max(scores.values()) if scores else 0
    winners = [seat for seat in order if scores[seat] == best]
    if len(winners) != 1:
        state["result"] = "draw"
        state["line"] = f"{shown}. Ничья."
        return
    state["result"] = f"{winners[0]}_win"
    state["line"] = f"{shown}."
