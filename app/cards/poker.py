"""Техасский холдем. Банк — игровые фишки, не деньги.

Белые — дилер и малый блайнд, чёрные — большой блайнд.
Новая раздача безлимитная: стек и любая ставка от минимума до ва-банка.
Раздача без стека доигрывается прежним лимитом.
Старые раздачи пятикарточного дро доигрываются прежними правилами.
"""

from __future__ import annotations

import json
import random
import secrets
from itertools import combinations
from typing import Any

RANKS = "23456789TJQKA"
SUITS = "CDHS"
SB = 5
BB = 10
ANTE = BB
STACK = 1000


def _big(state: dict[str, Any]) -> int:
    try:
        return max(1, int(state.get("bb") or BB))
    except (TypeError, ValueError):
        return BB


def _small(state: dict[str, Any]) -> int:
    try:
        return max(1, int(state.get("sb") or SB))
    except (TypeError, ValueError):
        return SB
MAX_BETS = 4
_STREET_CARDS = {"flop": 3, "turn": 1, "river": 1}
_NEXT = {"preflop": "flop", "flop": "turn", "turn": "river"}
_RANK_ONE = {
    14: "туз",
    13: "король",
    12: "дама",
    11: "валет",
    10: "десятка",
    9: "девятка",
    8: "восьмёрка",
    7: "семёрка",
    6: "шестёрка",
    5: "пятёрка",
    4: "четвёрка",
    3: "тройка",
    2: "двойка",
}
_RANK_MANY = {
    14: "тузов",
    13: "королей",
    12: "дам",
    11: "валетов",
    10: "десяток",
    9: "девяток",
    8: "восьмёрок",
    7: "семёрок",
    6: "шестёрок",
    5: "пятёрок",
    4: "четвёрок",
    3: "троек",
    2: "двоек",
}


def blind_for(seat: str, small: int | None = None, big: int | None = None) -> int:
    low = SB if small is None else small
    high = BB if big is None else big
    return low if seat == "white" else high


def _deck() -> list[str]:
    cards = [rank + suit for rank in RANKS for suit in SUITS]
    secrets.SystemRandom().shuffle(cards)
    return cards


def waiting() -> dict[str, Any]:
    return {
        "kind": "poker",
        "variant": "holdem",
        "phase": "waiting",
        "to_move": "white",
        "pot": 0,
        "board": [],
        "result": None,
        "reason": None,
    }


def _bankroll(
    committed: dict[str, int],
    buy_in: int = STACK,
    purses: dict[str, int] | None = None,
    big: int = BB,
) -> dict[str, Any]:
    posted = {str(seat): int(amount) for seat, amount in committed.items()}
    stacks: dict[str, int] = {}
    for seat, amount in posted.items():
        chosen = int(purses[seat]) if purses and seat in purses else int(buy_in)
        stacks[seat] = max(chosen, amount) - amount
    return {
        "stacks": stacks,
        "invested": dict(posted),
        "last_size": big,
    }


def spread_purses(seats: list[str], median: int, seed: int, big: int = BB) -> dict[str, int]:
    """Разные стеки компьютеров вокруг медианы, не одна и та же сумма."""
    center = max(big * 8, int(median))
    factors = (0.58, 0.7, 0.82, 0.94, 1.06, 1.18)
    order = list(factors)
    random.Random(seed).shuffle(order)
    purses: dict[str, int] = {}
    used: set[int] = set()
    for index, seat in enumerate(seats):
        raw = int(round(center * order[index % len(order)] / 10.0) * 10)
        raw = max(big * 8, raw)
        while raw in used:
            raw += 10
        used.add(raw)
        purses[str(seat)] = raw
    return purses


def cash_out(state: dict[str, Any]) -> dict[str, int] | None:
    stacks = state.get("stacks")
    if not isinstance(stacks, dict):
        return None
    payout = state.get("payout") if isinstance(state.get("payout"), dict) else {}
    seats = list(dict.fromkeys([*stacks, *payout]))
    return {str(seat): int(stacks.get(seat) or 0) + int(payout.get(seat) or 0) for seat in seats}


def deal(
    buy_in: int = STACK,
    purses: dict[str, int] | None = None,
    *,
    small: int = SB,
    big: int = BB,
) -> dict[str, Any]:
    deck = _deck()
    committed = {"white": small, "black": big}
    return {
        "kind": "poker",
        "variant": "holdem",
        "phase": "preflop",
        "hands": {"white": deck[:2], "black": deck[2:4]},
        "board": [],
        "deck": deck[4:],
        "pot": small + big,
        "to_move": "white",
        "button": "white",
        "committed": committed,
        "sb": small,
        "bb": big,
        "stake": big,
        "bets": 1,
        "acted": [],
        **_bankroll(committed, buy_in, purses, big),
        "result": None,
        "reason": None,
        "winner_hand": "",
        "named": {},
    }


def waiting_table(seat_keys: list[str]) -> dict[str, Any]:
    return {
        "kind": "poker",
        "variant": "holdem",
        "phase": "waiting",
        "order": list(seat_keys),
        "to_move": seat_keys[0],
        "pot": 0,
        "board": [],
        "result": None,
        "reason": None,
    }


def deal_table(
    seat_keys: list[str],
    buy_in: int = STACK,
    purses: dict[str, int] | None = None,
    busted: list[str] | None = None,
    *,
    small: int = SB,
    big: int = BB,
) -> dict[str, Any]:
    if seat_keys == ["white", "black"]:
        dealt = deal(buy_in, purses, small=small, big=big)
        if busted:
            dealt["busted"] = [str(item) for item in busted]
        return dealt
    deck = _deck()
    hands = {seat: deck[index * 2 : index * 2 + 2] for index, seat in enumerate(seat_keys)}
    rest = deck[len(seat_keys) * 2 :]
    button = seat_keys[0]
    if len(seat_keys) == 2:
        low_seat, high_seat, first = seat_keys[0], seat_keys[1], seat_keys[0]
    else:
        low_seat, high_seat = seat_keys[1], seat_keys[2]
        first = seat_keys[3 % len(seat_keys)]
    committed = dict.fromkeys(seat_keys, 0)
    committed[low_seat] = small
    committed[high_seat] = big
    return {
        "kind": "poker",
        "variant": "holdem",
        "phase": "preflop",
        "order": list(seat_keys),
        "hands": hands,
        "board": [],
        "deck": rest,
        "pot": small + big,
        "to_move": first,
        "button": button,
        "committed": committed,
        "sb": small,
        "bb": big,
        "stake": big,
        "bets": 1,
        "acted": [],
        "folded": [],
        **_bankroll(committed, buy_in, purses, big),
        "busted": [str(item) for item in busted or []],
        "result": None,
        "reason": None,
        "winner_hand": "",
        "named": {},
    }


def dumps(state: dict[str, Any]) -> str:
    return json.dumps(state, ensure_ascii=False, separators=(",", ":"))


def matches(state: dict[str, Any], stored: str) -> bool:
    if dumps(state) == stored:
        return True
    try:
        other = loads(stored)
    except ValueError:
        return False
    left = json.loads(dumps(state))
    right = json.loads(dumps(other))
    for item in (left, right):
        folded = item.get("folded")
        if isinstance(folded, list):
            item["folded"] = sorted(str(name) for name in folded)
    return left == right


def loads(text: str) -> dict[str, Any]:
    value = json.loads(text)
    if not isinstance(value, dict) or value.get("kind") != "poker":
        raise ValueError("Это не стол покера.")
    return value


def _value(card: str) -> int:
    return RANKS.index(card[0]) + 2


def rank_hand(cards: list[str]) -> tuple[int, ...]:
    values = sorted((_value(card) for card in cards), reverse=True)
    flush = len({card[1] for card in cards}) == 1
    unique = sorted(set(values), reverse=True)
    straight = False
    high = unique[0] if unique else 0
    if len(unique) == 5 and unique[0] - unique[4] == 4:
        straight = True
    if unique == [14, 5, 4, 3, 2]:
        straight = True
        high = 5
    counts = sorted(((values.count(value), value) for value in unique), reverse=True)
    if straight and flush:
        return (8, high)
    if counts and counts[0][0] == 4:
        return (7, counts[0][1], counts[1][1])
    if len(counts) > 1 and counts[0][0] == 3 and counts[1][0] == 2:
        return (6, counts[0][1], counts[1][1])
    if flush:
        return (5, *values)
    if straight:
        return (4, high)
    if counts and counts[0][0] == 3:
        kickers = [value for value in values if value != counts[0][1]]
        return (3, counts[0][1], *kickers)
    if len(counts) > 1 and counts[0][0] == 2 and counts[1][0] == 2:
        pairs = sorted((counts[0][1], counts[1][1]), reverse=True)
        return (2, pairs[0], pairs[1], counts[2][1])
    if counts and counts[0][0] == 2:
        kickers = [value for value in values if value != counts[0][1]]
        return (1, counts[0][1], *kickers)
    return (0, *values)


def best_hand(cards: list[str]) -> tuple[tuple[int, ...], list[str]]:
    found: tuple[int, ...] | None = None
    chosen: list[str] = []
    for group in combinations(cards, 5):
        rank = rank_hand(list(group))
        if found is None or rank > found:
            found = rank
            chosen = list(group)
    return found or (0,), chosen


def hand_name(cards: list[str]) -> str:
    if len(cards) < 5:
        return ""
    rank, _chosen = best_hand(cards)
    return _describe(rank)


def _many(value: int) -> str:
    return _RANK_MANY.get(value, str(value))


def _one(value: int) -> str:
    return _RANK_ONE.get(value, str(value))


def _describe(rank: tuple[int, ...]) -> str:
    kind = rank[0] if rank else 0
    if kind == 8 and len(rank) > 1 and rank[1] == 14:
        return "Роял-флеш"
    if kind == 8:
        return f"Стрит-флеш до {_one(rank[1])}"
    if kind == 7:
        return f"Каре {_many(rank[1])}"
    if kind == 6:
        return f"Фулл-хаус, {_many(rank[1])} и {_many(rank[2])}"
    if kind == 5:
        return f"Флеш, старшая карта {_one(rank[1])}"
    if kind == 4:
        return f"Стрит до {_one(rank[1])}"
    if kind == 3:
        return f"Сет {_many(rank[1])}"
    if kind == 2:
        return f"Две пары, {_many(rank[1])} и {_many(rank[2])}"
    if kind == 1:
        return f"Пара {_many(rank[1])}"
    return f"Старшая карта {_one(rank[1])}" if len(rank) > 1 else "Старшая карта"


def _other(seat: str) -> str:
    return "black" if seat == "white" else "white"


def _seats(state: dict[str, Any]) -> list[str]:
    order = state.get("order")
    if isinstance(order, list) and len(order) >= 2:
        return [str(item) for item in order]
    return ["white", "black"]


def _folded(state: dict[str, Any]) -> set[str]:
    return {str(item) for item in state.get("folded") or []}


def _note_fold(state: dict[str, Any], seat: str) -> None:
    folded = [str(item) for item in state.get("folded") or []]
    if seat not in folded:
        folded.append(seat)
    state["folded"] = folded


def _live(state: dict[str, Any]) -> list[str]:
    folded = _folded(state)
    return [seat for seat in _seats(state) if seat not in folded]


def _after(state: dict[str, Any], seat: str) -> str:
    order = _seats(state)
    live = set(_live(state))
    if seat not in order or not live:
        return next(iter(live), seat)
    start = order.index(seat)
    for step in range(1, len(order) + 1):
        candidate = order[(start + step) % len(order)]
        if candidate in live:
            return candidate
    return seat


def _title(seat: str) -> str:
    if seat == "white":
        return "Белые"
    if seat == "black":
        return "Чёрные"
    if seat.startswith("p") and seat[1:].isdigit():
        return f"Место {int(seat[1:]) + 1}"
    return seat


def _numbers(value: object) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    return {str(key): int(amount) for key, amount in value.items()}


def _roster(state: dict[str, Any]) -> list[dict[str, Any]]:
    if not state.get("order"):
        return []
    folded = _folded(state)
    hands = state.get("hands") or {}
    waiting = state.get("phase") == "waiting"
    return [
        {"key": seat, "count": 0 if waiting else len(hands.get(seat, [])), "folded": seat in folded}
        for seat in _seats(state)
    ]


def _money(state: dict[str, Any]) -> bool:
    return isinstance(state.get("stacks"), dict)


def _all_in(state: dict[str, Any], seat: str) -> bool:
    stacks = state.get("stacks")
    if not isinstance(stacks, dict) or seat not in stacks:
        return False
    return int(stacks[seat]) <= 0


def _next_actor(state: dict[str, Any], seat: str) -> str:
    order = _seats(state)
    live = set(_live(state))
    if seat not in order or not live:
        return next(iter(live), seat)
    start = order.index(seat)
    for step in range(1, len(order) + 1):
        candidate = order[(start + step) % len(order)]
        if candidate in live and not _all_in(state, candidate):
            return candidate
    return _after(state, seat)


def _closed(state: dict[str, Any]) -> bool:
    live = _live(state)
    acted = {str(item) for item in state.get("acted") or []}
    if not live:
        return False
    pending = [seat for seat in live if not _all_in(state, seat)]
    if not pending:
        return True
    if not set(pending).issubset(acted):
        return False
    stake = int(state.get("stake") or 0)
    return all(int(state["committed"][seat]) == stake or _all_in(state, seat) for seat in live)


def _legacy(state: dict[str, Any]) -> bool:
    if state.get("variant") == "holdem":
        return False
    return state.get("phase") in {"bet1", "draw", "bet2"} or "drawn" in state


def _pay_layers(state: dict[str, Any], contestants: list[str]) -> dict[str, int] | None:
    invested = state.get("invested")
    if not isinstance(invested, dict):
        return None
    folded = _folded(state)
    levels = sorted({int(amount) for amount in invested.values()})
    payout = dict.fromkeys(_seats(state), 0)
    previous = 0
    for level in levels:
        if level <= previous:
            continue
        contributors = [seat for seat, amount in invested.items() if int(amount) >= level]
        layer = (level - previous) * len(contributors)
        eligible = [seat for seat in contestants if seat in contributors and seat not in folded]
        if not eligible:
            if contributors:
                payout[contributors[-1]] += layer
        else:
            share, extra = divmod(layer, len(eligible))
            for index, seat in enumerate(eligible):
                payout[seat] += share + (extra if index == 0 else 0)
        previous = level
    return payout


def _finish(
    state: dict[str, Any],
    winner: str | None,
    reason: str,
    tied: list[str] | None = None,
) -> None:
    state["phase"] = "done"
    state["result"] = None if winner is None else f"{winner}_win"
    state["reason"] = reason
    group = list(tied) if tied else ([winner] if winner else _live(state))
    layered = _pay_layers(state, group)
    seats = _seats(state)
    if layered is not None:
        if set(seats) == {"white", "black"} and winner:
            other = _other(winner)
            state["payout"] = {winner: layered.get(winner, 0), other: layered.get(other, 0)}
        else:
            state["payout"] = {seat: layered.get(seat, 0) for seat in seats}
        return
    pot = int(state["pot"])
    if winner is None:
        share, extra = divmod(pot, len(seats))
        state["payout"] = {seat: share + (extra if index == 0 else 0) for index, seat in enumerate(seats)}
    elif set(seats) == {"white", "black"}:
        state["payout"] = {winner: pot, _other(winner): 0}
    else:
        state["payout"] = {seat: pot if seat == winner else 0 for seat in seats}


def _showdown(state: dict[str, Any]) -> None:
    board = list(state.get("board") or [])
    ranks: dict[str, tuple[int, ...]] = {}
    names: dict[str, str] = {}
    for seat in _live(state):
        rank, _cards = best_hand(list(state["hands"][seat]) + board)
        ranks[seat] = rank
        names[seat] = _describe(rank)
    state["named"] = names
    best = max(ranks.values())
    winners = [seat for seat, rank in ranks.items() if rank == best]
    if len(winners) == 1:
        winner = winners[0]
        _finish(state, winner, "showdown")
        state["winner_hand"] = f"{_title(winner)} выиграли: {names[winner]}."
        return
    _finish(state, None, "split", tied=winners)
    state["result"] = "draw"
    state["winner_hand"] = f"Ничья: {names[winners[0]]}."


def _bet_size(state: dict[str, Any]) -> int:
    big = _big(state)
    phase = str(state.get("phase") or "")
    return big if phase in {"preflop", "flop"} else big * 2


def _open_street(state: dict[str, Any]) -> None:
    phase = str(state["phase"])
    coming = _NEXT[phase]
    count = _STREET_CARDS[coming]
    state["board"] = list(state.get("board") or []) + list(state["deck"][:count])
    state["deck"] = state["deck"][count:]
    state["phase"] = coming
    state["committed"] = dict.fromkeys(_seats(state), 0)
    state["stake"] = 0
    state["bets"] = 0
    state["acted"] = []
    state["last_size"] = _big(state)
    button = str(state.get("button") or _seats(state)[0])
    state["to_move"] = _next_actor(state, button)


def _runout(state: dict[str, Any]) -> bool:
    if not _money(state):
        return False
    rich = [seat for seat in _live(state) if int(state["stacks"].get(seat) or 0) > 0]
    return len(_live(state)) >= 2 and len(rich) <= 1


def _next_street(state: dict[str, Any]) -> None:
    if str(state["phase"]) == "river":
        _showdown(state)
        return
    if _runout(state):
        while str(state["phase"]) in _NEXT:
            _open_street(state)
        _showdown(state)
        return
    _open_street(state)


def _bounds(state: dict[str, Any], seat: str) -> tuple[str, int, int, int] | None:
    stake = int(state["stake"])
    put = int(state["committed"][seat])
    high = put + int(state["stacks"][seat])
    if high <= 0:
        return None
    if stake <= 0:
        floor = _big(state)
        low = floor if high >= floor else high
        return ("bet", low, high, put)
    step = max(_big(state), int(state.get("last_size") or _big(state)))
    low = stake + step
    if high < low:
        return None
    return ("raise", low, high, put)


def _chosen_total(state: dict[str, Any], seat: str, path: list[str], kind: str) -> int:
    bounds = _bounds(state, seat)
    if bounds is None or bounds[0] != kind:
        raise ValueError("Такое действие за покерным столом не принимается.")
    if len(path) < 3:
        return bounds[1]
    try:
        amount = int(path[2])
    except (TypeError, ValueError) as exc:
        raise ValueError("Такое действие за покерным столом не принимается.") from exc
    if amount < bounds[1] or amount > bounds[2]:
        raise ValueError("Такое действие за покерным столом не принимается.")
    return amount


def _sized_ok(state: dict[str, Any], path: list[str]) -> bool:
    try:
        _chosen_total(state, str(state["to_move"]), path, path[1])
    except (ValueError, KeyError, IndexError):
        return False
    return True


def _money_legal(state: dict[str, Any]) -> list[dict[str, Any]]:
    seat = str(state["to_move"])
    if _all_in(state, seat):
        return []
    owed = int(state["stake"]) - int(state["committed"][seat])
    room = int(state["stacks"][seat])
    actions: list[dict[str, Any]] = []
    bounds = _bounds(state, seat)
    if owed <= 0:
        actions.append({"path": ["act", "check"], "notation": "Чек", "promotion": None})
        if bounds and bounds[0] == "bet":
            actions.append(
                {
                    "path": ["act", "bet"],
                    "notation": "Ставка",
                    "promotion": None,
                    "min": bounds[1],
                    "max": bounds[2],
                    "put": bounds[3],
                }
            )
        return actions
    pay = min(owed, room)
    actions.append(
        {
            "path": ["act", "call"],
            "notation": "Ва-банк" if room <= owed else f"Уравнять: {pay}",
            "promotion": None,
        }
    )
    if bounds and bounds[0] == "raise":
        actions.append(
            {
                "path": ["act", "raise"],
                "notation": "Повысить",
                "promotion": None,
                "min": bounds[1],
                "max": bounds[2],
                "put": bounds[3],
            }
        )
    actions.append({"path": ["act", "fold"], "notation": "Пас", "promotion": None})
    return actions


def legal(state: dict[str, Any]) -> list[dict[str, Any]]:
    if _legacy(state):
        return _draw_legal(state)
    if state.get("phase") in {None, "waiting", "done"}:
        return []
    if _money(state):
        return _money_legal(state)
    seat = str(state["to_move"])
    owed = int(state["stake"]) - int(state["committed"][seat])
    actions: list[dict[str, Any]] = []
    size = _bet_size(state)
    can_raise = int(state.get("bets") or 0) < MAX_BETS
    if owed <= 0:
        actions.append({"path": ["act", "check"], "notation": "Чек", "promotion": None})
        # A bet opens a street. Once chips are already in, another «Ставка» of the
        # same size used to add money without raising, and two computers did it forever.
        if can_raise and int(state.get("stake") or 0) == 0:
            actions.append({"path": ["act", "bet"], "notation": f"Ставка {size}", "promotion": None})
    else:
        actions.append({"path": ["act", "call"], "notation": f"Уравнять {owed}", "promotion": None})
        if can_raise:
            target = int(state["stake"]) + size
            actions.append({"path": ["act", "raise"], "notation": f"Повысить до {target}", "promotion": None})
        actions.append({"path": ["act", "fold"], "notation": "Сбросить", "promotion": None})
    return actions


def _stake_money(
    nxt: dict[str, Any],
    seat: str,
    path: list[str],
    *,
    opening: bool,
) -> tuple[dict[str, Any], list[tuple[str, int]]]:
    kind = "bet" if opening else "raise"
    total = _chosen_total(nxt, seat, path, kind)
    pay = total - int(nxt["committed"][seat])
    previous = int(nxt["stake"])
    nxt["committed"][seat] = total
    nxt["stacks"][seat] = int(nxt["stacks"][seat]) - pay
    nxt["invested"][seat] = int(nxt["invested"][seat]) + pay
    nxt["pot"] = int(nxt["pot"]) + pay
    nxt["stake"] = total
    if opening:
        nxt["bets"] = 1
        nxt["last_size"] = total
    else:
        nxt["bets"] = int(nxt.get("bets") or 0) + 1
        nxt["last_size"] = max(_big(nxt), total - previous)
    nxt["acted"] = [seat]
    if _closed(nxt):
        _next_street(nxt)
    else:
        nxt["to_move"] = _next_actor(nxt, seat)
    return nxt, [(seat, pay)]


def _call_money(nxt: dict[str, Any], seat: str) -> tuple[dict[str, Any], list[tuple[str, int]]]:
    owed = int(nxt["stake"]) - int(nxt["committed"][seat])
    room = int(nxt["stacks"][seat])
    pay = min(owed, room)
    nxt["committed"][seat] = int(nxt["committed"][seat]) + pay
    nxt["stacks"][seat] = room - pay
    nxt["invested"][seat] = int(nxt["invested"][seat]) + pay
    nxt["pot"] = int(nxt["pot"]) + pay
    nxt["acted"] = list(dict.fromkeys([*nxt["acted"], seat]))
    if _closed(nxt):
        _next_street(nxt)
    else:
        nxt["to_move"] = _next_actor(nxt, seat)
    return nxt, [(seat, pay)] if pay else []


def _recorded_flat_bet(state: dict[str, Any], path: list[str]) -> bool:
    if _money(state) or path != ["act", "bet"]:
        return False
    seat = str(state.get("to_move") or "")
    stake = int(state.get("stake") or 0)
    committed = state.get("committed") if isinstance(state.get("committed"), dict) else {}
    return stake > 0 and int(committed.get(seat) or 0) >= stake


def apply(state: dict[str, Any], path: list[str]) -> tuple[dict[str, Any], list[tuple[str, int]]]:
    if _legacy(state):
        return _draw_apply(state, path)
    money = _money(state)
    sized = money and len(path) >= 3 and path[1] in {"bet", "raise"}
    if sized:
        if not _sized_ok(state, path):
            raise ValueError("Такое действие за покерным столом не принимается.")
    else:
        allowed = {tuple(item["path"]) for item in legal(state)}
        if tuple(path) not in allowed and not _recorded_flat_bet(state, path):
            raise ValueError("Такое действие за покерным столом не принимается.")
    nxt = json.loads(dumps(state))
    seat = str(nxt["to_move"])
    action = path[1]
    if action == "fold":
        remaining = [item for item in _live(nxt) if item != seat]
        if len(remaining) == 1 and not _folded(nxt):
            won = remaining[0]
            _finish(nxt, won, "fold")
            pair = {seat, won}
            if pair == {"white", "black"} and won == "white":
                nxt["winner_hand"] = "Чёрные сбросили карты. Банк у белых."
            elif pair == {"white", "black"}:
                nxt["winner_hand"] = "Белые сбросили карты. Банк у чёрных."
            else:
                nxt["winner_hand"] = f"{_title(seat)} сбросили карты. Банк у {_title(won)}."
            return nxt, []
        _note_fold(nxt, seat)
        if len(remaining) == 1:
            won = remaining[0]
            _finish(nxt, won, "fold")
            nxt["winner_hand"] = f"{_title(seat)} сбросили карты. Банк у {_title(won)}."
        else:
            nxt["to_move"] = _next_actor(nxt, seat)
        return nxt, []
    if action == "check":
        nxt["acted"] = list(dict.fromkeys([*nxt["acted"], seat]))
        if _closed(nxt):
            _next_street(nxt)
        else:
            nxt["to_move"] = _next_actor(nxt, seat)
        return nxt, []
    if action == "bet":
        if money:
            return _stake_money(nxt, seat, path, opening=True)
        size = _bet_size(nxt)
        nxt["stake"] = size
        nxt["bets"] = 1
        nxt["committed"][seat] = size
        nxt["pot"] = int(nxt["pot"]) + size
        nxt["acted"] = [seat]
        nxt["to_move"] = _after(nxt, seat)
        return nxt, [(seat, size)]
    if action == "raise":
        if money:
            return _stake_money(nxt, seat, path, opening=False)
        size = _bet_size(nxt)
        pay = int(nxt["stake"]) + size - int(nxt["committed"][seat])
        nxt["stake"] = int(nxt["stake"]) + size
        nxt["bets"] = int(nxt.get("bets") or 0) + 1
        nxt["committed"][seat] = nxt["stake"]
        nxt["pot"] = int(nxt["pot"]) + pay
        nxt["acted"] = [seat]
        nxt["to_move"] = _after(nxt, seat)
        return nxt, [(seat, pay)]
    if money:
        return _call_money(nxt, seat)
    pay = int(nxt["stake"]) - int(nxt["committed"][seat])
    nxt["committed"][seat] = nxt["stake"]
    nxt["pot"] = int(nxt["pot"]) + pay
    nxt["acted"] = list(dict.fromkeys([*nxt["acted"], seat]))
    if _closed(nxt):
        _next_street(nxt)
    else:
        nxt["to_move"] = _after(nxt, seat)
    return nxt, [(seat, pay)] if pay else []


_BLUFF = {1: 0.0, 2: 0.05, 3: 0.16, 4: 0.30, 5: 0.48}


def _roll(state: dict[str, Any], level: int, salt: str) -> float:
    seat = str(state.get("to_move") or "")
    hole = ",".join(state.get("hands", {}).get(seat, []))
    board = ",".join(state.get("board") or [])
    return random.Random(f"{level}|{salt}|{hole}|{board}|{state.get('phase')}").random()


def _outs(hole: list[str], board: list[str]) -> str:
    if len(board) < 3:
        return ""
    cards = [*hole, *board]
    suits: dict[str, int] = {}
    for card in cards:
        suits[card[1]] = suits.get(card[1], 0) + 1
    flush = any(count == 4 for count in suits.values())
    values = {_value(card) for card in cards}
    if 14 in values:
        values.add(1)
    straight = False
    for start in sorted(values):
        window = {start, start + 1, start + 2, start + 3, start + 4}
        hit = len(window & values)
        if hit == 4:
            straight = True
            break
    if flush and straight:
        return "both"
    if flush:
        return "flush"
    if straight:
        return "straight"
    return ""


def _pressure(state: dict[str, Any], seat: str) -> tuple[int, int, int]:
    stacks = state.get("stacks") if isinstance(state.get("stacks"), dict) else {}
    invested = state.get("invested") if isinstance(state.get("invested"), dict) else {}
    behind = int(stacks.get(seat) or 0)
    brought = behind + int(invested.get(seat) or 0)
    stake = int(state.get("stake") or 0)
    put = int((state.get("committed") or {}).get(seat) or 0)
    owed = max(0, stake - put)
    step = max(_big(state), int(state.get("last_size") or _big(state)))
    return behind, brought, owed if owed else step


def _should_stop(state: dict[str, Any], seat: str, monster: bool) -> bool:
    if not _money(state):
        return False
    behind, brought, price = _pressure(state, seat)
    if brought <= 0:
        return True
    spent = 1 - (behind / brought)
    bets = int(state.get("bets") or 0)
    if monster:
        floor = _big(state)
        return spent >= 0.34 or price >= max(floor, int(behind * 0.45)) or bets >= 3
    floor = _big(state)
    return spent >= 0.22 or price >= max(floor, int(behind * 0.28)) or bets >= 2


def suggest(state: dict[str, Any], level: int = 5) -> list[str] | None:
    if _legacy(state):
        return _draw_suggest(state, level)
    actions = legal(state)
    if not actions:
        return None
    strength = max(1, min(5, int(level)))
    paths = [list(item["path"]) for item in actions]
    seat = str(state["to_move"])
    hole = list(state.get("hands", {}).get(seat, []))
    board = list(state.get("board") or [])
    category = _score(state, seat)[0]
    facing = any(path[1] in {"call", "raise", "fold"} for path in paths)
    draw = _outs(hole, board)
    bluff = _roll(state, strength, "bluff") < _BLUFF[strength]
    monster = category >= 4 or (category >= 3 and strength >= 3)

    def take(name: str) -> list[str]:
        for path in paths:
            if path[1] == name:
                return path
        return paths[0]

    if _should_stop(state, seat, monster):
        if not facing:
            return take("check")
        if category == 0 and not draw:
            return take("fold")
        behind, _spent, price = _pressure(state, seat)
        if monster or (category >= 2 and price <= max(_big(state), int(behind * 0.35))):
            return take("call")
        return take("fold")
    if strength == 1:
        return random.choice(paths)

    made = category >= 2 or (category >= 1 and strength >= 4)
    if facing:
        if category == 0 and not draw:
            return take("fold")
        if monster and strength >= 4:
            return take("raise")
        if category >= 2 and strength >= 5:
            return take("raise")
        if draw and category < 2 and strength >= 4 and bluff:
            return take("raise")
        if made or category >= 1 or (draw and strength >= 3):
            return take("call")
        if bluff and strength >= 5:
            return take("raise")
        return take("fold")
    if monster or made or (category >= 1 and strength >= 3):
        return take("bet")
    if draw and strength >= 3:
        return take("bet")
    if bluff:
        return take("bet")
    return take("check")


def _score(state: dict[str, Any], seat: str) -> tuple[int, ...]:
    hole = list(state.get("hands", {}).get(seat, []))
    board = list(state.get("board") or [])
    if len(board) >= 3 and len(hole) == 2:
        return best_hand(hole + board)[0]
    if len(hole) < 2:
        return (0, 0)
    high, low = sorted((_value(card) for card in hole), reverse=True)
    suited = hole[0][1] == hole[1][1]
    if high == low:
        return (3, high)
    if high >= 12 and low >= 10:
        return (2 if suited else 1, high)
    if high >= 14 or (suited and high - low <= 2 and high >= 8):
        return (1, high)
    return (0, high)


def leave(state: dict[str, Any], seat: str) -> dict[str, Any]:
    nxt = json.loads(dumps(state))
    if nxt.get("phase") == "done":
        return nxt
    if nxt.get("phase") == "waiting":
        nxt["phase"] = "done"
        nxt["reason"] = "left"
        return nxt
    others = [item for item in _live(nxt) if item != seat]
    if not _folded(nxt):
        _finish(nxt, others[0] if others else _after(state, seat), "left")
        return nxt
    _note_fold(nxt, seat)
    _finish(nxt, others[0] if others else _after(nxt, seat), "left")
    return nxt


def chronicle(initial: str, payloads: list[dict[str, Any]]) -> dict[str, Any]:
    state = loads(initial)
    last: dict[str, str] = {}
    counts = {"fold": 0, "call": 0, "raise": 0, "bet": 0, "check": 0}
    folded_by = ""
    for payload in payloads:
        if payload.get("leave"):
            seat = str(payload.get("seat") or "")
            last[seat] = "fold"
            counts["fold"] += 1
            state = leave(state, seat)
            continue
        path = [str(item) for item in payload.get("path") or []]
        action = path[1] if len(path) > 1 and path[0] == "act" else ""
        actor = str(state.get("to_move") or "")
        state, _charges = apply(state, path)
        if action in counts:
            last[actor] = action
            counts[action] += 1
            if action == "fold":
                folded_by = actor
    result = state.get("result")
    winner = result[: -len("_win")] if isinstance(result, str) and result.endswith("_win") else None
    named = state.get("named") if isinstance(state.get("named"), dict) else {}
    combination = str(named.get(winner) or "") if winner else ""
    return {
        "last": last,
        "counts": counts,
        "winner": winner,
        "winner_label": _title(winner) if winner else "",
        "combination": combination,
        "pot": int(state.get("pot") or 0),
        "payout": state.get("payout") if isinstance(state.get("payout"), dict) else {},
        "line": str(state.get("winner_hand") or ""),
        "folded_by": folded_by,
        "done": state.get("phase") == "done",
        "board": list(state.get("board") or []),
        "reason": str(state.get("reason") or ""),
        "named": named,
        "hands": state.get("hands") if state.get("reason") in {"showdown", "split"} else {},
        "remaining": cash_out(state) or {},
        "invested": state.get("invested") if isinstance(state.get("invested"), dict) else {},
    }


def replay(initial: str, payloads: list[dict[str, Any]]) -> dict[str, Any]:
    state = loads(initial)
    for payload in payloads:
        if payload.get("leave"):
            state = leave(state, str(payload.get("seat") or "white"))
            continue
        path = payload.get("path") or []
        state, _charges = apply(state, [str(item) for item in path])
    return state


def view(state: dict[str, Any], seat: str | None) -> dict[str, Any]:
    if _legacy(state):
        seen = _draw_view(state, seat)
        seen["board"] = []
        seen["winner_hand"] = ""
        return seen
    phase = state.get("phase")
    mine = list(state.get("hands", {}).get(seat, [])) if seat and phase != "waiting" else []
    show = phase == "done" and state.get("reason") in {"showdown", "split"}
    others = [item for item in _seats(state) if item != seat]
    waiting = (
        "Ждём игроков за свободные места."
        if state.get("order")
        else "Ждём второго игрока. Блайнды ещё не поставлены."
    )
    titles = {
        "waiting": waiting,
        "preflop": "Две закрытые карты. Можно уравнять, повысить или сбросить.",
        "flop": "На столе три общие карты.",
        "turn": "На столе четыре общие карты.",
        "river": "На столе пять общих карт. Последняя торговля.",
        "done": state.get("winner_hand") or "Раздача окончена. Банк — игровые фишки.",
    }
    return {
        "hand": mine,
        "shown": state.get("hands", {}) if show else {},
        "board": list(state.get("board") or []),
        "winner_hand": state.get("winner_hand") or "",
        "pot": state.get("pot", 0),
        "phase": phase,
        "stacks": _numbers(state.get("stacks")),
        "committed": _numbers(state.get("committed")),
        "button": str(state.get("button") or ""),
        "busted": [str(item) for item in state.get("busted") or []],
        "roster": _roster(state),
        "opponent_count": 0
        if not seat or phase == "waiting"
        else sum(len(state.get("hands", {}).get(item, [])) for item in others),
        "deck": len(state.get("deck") or []),
        "actions": legal(state) if seat and state.get("to_move") == seat else [],
        "message": titles.get(str(phase), "Стол открыт."),
    }


def _draw_legal(state: dict[str, Any]) -> list[dict[str, Any]]:
    if state.get("phase") in {None, "waiting", "done"}:
        return []
    phase = state["phase"]
    if phase == "draw":
        hand = list(state["hands"][state["to_move"]])
        actions = [{"path": ["draw", "-"], "notation": "Без обмена", "promotion": None}]
        for size in (1, 2, 3):
            for group in combinations(hand, size):
                actions.append({"path": ["draw", ",".join(group)], "notation": f"Обмен {size}", "promotion": None})
        return actions
    actions = []
    if state["street_bet"] is None:
        actions.append({"path": ["act", "check"], "notation": "Чек", "promotion": None})
        actions.append({"path": ["act", "bet"], "notation": "Ставка 10", "promotion": None})
    elif state["street_bet"] != state["to_move"]:
        actions.append({"path": ["act", "call"], "notation": "Уравнять", "promotion": None})
    actions.append({"path": ["act", "fold"], "notation": "Сбросить", "promotion": None})
    return actions


def _draw_normalize(state: dict[str, Any], path: list[str]) -> list[str]:
    if not path or path[0] != "draw" or len(path) < 2 or path[1] == "-":
        return path
    requested = path[1].split(",")
    hand = list(state["hands"][state["to_move"]])
    if len(requested) != len(set(requested)) or any(card not in hand for card in requested):
        return path
    ordered = [card for card in hand if card in requested]
    return ["draw", ",".join(ordered)]


def _draw_open(state: dict[str, Any], phase: str) -> None:
    state["phase"] = phase
    state["to_move"] = "white"
    state["street_bet"] = None
    state["acted"] = []


def _draw_showdown(state: dict[str, Any]) -> None:
    white = rank_hand(state["hands"]["white"])
    black = rank_hand(state["hands"]["black"])
    white_name = _describe(white)
    black_name = _describe(black)
    state["named"] = {"white": white_name, "black": black_name}
    if white > black:
        _finish(state, "white", "showdown")
        state["winner_hand"] = f"Белые выиграли: {white_name}."
    elif black > white:
        _finish(state, "black", "showdown")
        state["winner_hand"] = f"Чёрные выиграли: {black_name}."
    else:
        _finish(state, None, "split")
        state["result"] = "draw"
        state["winner_hand"] = f"Ничья: {white_name}."


def _draw_apply(state: dict[str, Any], path: list[str]) -> tuple[dict[str, Any], list[tuple[str, int]]]:
    path = _draw_normalize(state, path)
    allowed = {tuple(item["path"]) for item in _draw_legal(state)}
    if tuple(path) not in allowed:
        raise ValueError("Такое действие за покерным столом не принимается.")
    nxt = json.loads(dumps(state))
    seat = nxt["to_move"]
    charges: list[tuple[str, int]] = []
    if path[0] == "draw":
        discards = [] if path[1] == "-" else path[1].split(",")
        hand = [card for card in nxt["hands"][seat] if card not in discards]
        drawn = nxt["deck"][: len(discards)]
        nxt["deck"] = nxt["deck"][len(discards) :]
        nxt["hands"][seat] = hand + drawn
        nxt["drawn"][seat] = True
        nxt["to_move"] = _other(seat)
        if all(nxt["drawn"].values()):
            _draw_open(nxt, "bet2")
        return nxt, charges
    action = path[1]
    if action == "fold":
        _finish(nxt, _other(seat), "fold")
        return nxt, charges
    if action == "bet":
        nxt["pot"] += 10
        nxt["street_bet"] = seat
        nxt["acted"] = [seat]
        nxt["to_move"] = _other(seat)
        return nxt, [(seat, 10)]
    if action == "call":
        nxt["pot"] += 10
        charges.append((seat, 10))
        if nxt["phase"] == "bet1":
            _draw_open(nxt, "draw")
        else:
            _draw_showdown(nxt)
        return nxt, charges
    nxt["acted"] = list(dict.fromkeys([*nxt["acted"], seat]))
    if nxt["street_bet"] is None and len(nxt["acted"]) == 2:
        if nxt["phase"] == "bet1":
            _draw_open(nxt, "draw")
        else:
            _draw_showdown(nxt)
    else:
        nxt["to_move"] = _other(seat)
    return nxt, charges


def _draw_suggest(state: dict[str, Any], level: int) -> list[str] | None:
    actions = _draw_legal(state)
    if not actions:
        return None
    if level <= 1 or random.random() < 0.15:
        return list(random.choice(actions)["path"])
    if state.get("phase") == "draw":
        return ["draw", "-"]
    facing = state.get("street_bet") not in {None, state.get("to_move")}
    wanted = "call" if facing else "check"
    for item in actions:
        if item["path"][1] == wanted:
            return list(item["path"])
    return list(actions[0]["path"])


def _draw_view(state: dict[str, Any], seat: str | None) -> dict[str, Any]:
    phase = state.get("phase")
    mine = list(state.get("hands", {}).get(seat, [])) if seat and phase != "waiting" else []
    show = phase == "done"
    titles = {
        "waiting": "Ждём второго игрока. Фишки ещё не поставлены.",
        "bet1": "Торговля перед обменом.",
        "draw": "Можно обменять до трёх карт.",
        "bet2": "Последняя торговля.",
        "done": state.get("winner_hand") or "Раздача окончена. Банк — игровые фишки.",
    }
    return {
        "hand": mine,
        "shown": state.get("hands", {}) if show else {},
        "pot": state.get("pot", 0),
        "phase": phase,
        "opponent_count": 0 if not seat else len(state.get("hands", {}).get(_other(seat), [])),
        "deck": len(state.get("deck") or []),
        "actions": _draw_legal(state) if seat and state.get("to_move") == seat else [],
        "message": titles.get(str(phase), "Стол открыт."),
    }
