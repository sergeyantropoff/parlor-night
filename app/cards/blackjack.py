"""Блэкджек против дилера. Банк — игровые фишки, не деньги.

Игроки ставят по очереди, затем берут карты или останавливаются.
Туз — 1 или 11. Дилер открывает вторую карту. С опытного уровня берёт до 17,
новичок останавливается на 15, любитель на 16, сильный и мастер берут мягкие 17.
Блэкджек из двух карт платит 3 к 2. Обычная победа платит 1 к 1. Ничья возвращает ставку.
"""

from __future__ import annotations

import json
from typing import Any

from app.cards.deck import label, pack

RANKS = "23456789TJQKA"
STACK = 200
BETS = (10, 25, 50, 100)


def _menu(state: dict[str, Any]) -> tuple[int, ...]:
    raw = state.get("bet_menu")
    if isinstance(raw, list) and raw:
        values: list[int] = []
        for item in raw:
            try:
                values.append(int(item))
            except (TypeError, ValueError):
                continue
        if values:
            return tuple(values)
    return BETS


def waiting(order: list[str] | None = None, variant: str = "classic") -> dict[str, Any]:
    del variant
    seats = list(order or ["white"])
    return _shell(seats, "waiting")


def waiting_table(seat_keys: list[str], variant: str = "classic") -> dict[str, Any]:
    return waiting(seat_keys, variant)


def deal(
    order: list[str] | None = None,
    variant: str = "classic",
    purses: dict[str, int] | None = None,
    *,
    stack: int = STACK,
    bets: tuple[int, ...] | list[int] | None = None,
) -> dict[str, Any]:
    del variant
    seats = list(order or ["white"])
    if not 1 <= len(seats) <= 6:
        raise ValueError("За блэкджеком от одного до шести игроков.")
    stacks = {}
    for seat in seats:
        chosen = int(purses[seat]) if purses and seat in purses else stack
        stacks[seat] = max(0, chosen)
    state = _shell(seats, "bet")
    state["stacks"] = stacks
    state["bet_menu"] = list(bets or BETS)
    state["deck"] = pack(RANKS) + pack(RANKS)
    state["to_move"] = _next_bettor(state, "")
    if state["to_move"] is None:
        state["phase"] = "done"
        state["result"] = "draw"
        state["reason"] = "no_chips"
        state["line"] = "Ставить нечем."
    return state


def deal_table(
    seat_keys: list[str],
    variant: str = "classic",
    purses: dict[str, int] | None = None,
    *,
    stack: int = STACK,
    bets: tuple[int, ...] | list[int] | None = None,
) -> dict[str, Any]:
    return deal(seat_keys, variant, purses, stack=stack, bets=bets)


def _shell(seats: list[str], phase: str) -> dict[str, Any]:
    return {
        "kind": "blackjack",
        "variant": "classic",
        "phase": phase,
        "to_move": seats[0],
        "order": seats,
        "hands": {seat: [] for seat in seats},
        "status": {seat: "open" for seat in seats},
        "acts": {},
        "dealer": [],
        "deck": [],
        "stacks": {seat: 0 for seat in seats},
        "committed": {seat: 0 for seat in seats},
        "payout": {},
        "result": None,
        "reason": None,
        "line": "",
        "hole": True,
    }


def dumps(state: dict[str, Any]) -> str:
    return json.dumps(state, ensure_ascii=False, separators=(",", ":"))


def loads(text: str) -> dict[str, Any]:
    state = json.loads(text)
    if not isinstance(state, dict) or state.get("kind") != "blackjack":
        raise ValueError("Это не стол блэкджека.")
    return state


def _total(cards: list[str]) -> int:
    total = 0
    aces = 0
    for card in cards:
        rank = card[0]
        if rank == "A":
            aces += 1
            total += 11
        elif rank in "TJQK":
            total += 10
        else:
            total += int(rank)
    while total > 21 and aces:
        total -= 10
        aces -= 1
    return total


def _blackjack(cards: list[str]) -> bool:
    return len(cards) == 2 and _total(cards) == 21


def _draw(state: dict[str, Any], count: int = 1) -> list[str]:
    drawn = []
    for _ in range(count):
        if not state["deck"]:
            state["deck"] = pack(RANKS)
        drawn.append(state["deck"].pop())
    return drawn


def _next_bettor(state: dict[str, Any], after: str) -> str | None:
    order = list(state["order"])
    start = order.index(after) + 1 if after in order else 0
    for step in range(len(order)):
        seat = order[(start + step) % len(order)]
        if after and seat == after:
            continue
        floor = _menu(state)[0]
        if int(state["stacks"].get(seat, 0)) >= floor and int(state["committed"].get(seat, 0)) == 0:
            return seat
        if after == "" and seat == order[-1] and int(state["stacks"].get(seat, 0)) < floor:
            continue
    if after == "":
        floor = _menu(state)[0]
        for seat in order:
            if int(state["stacks"].get(seat, 0)) >= floor:
                return seat
    return None


def legal(state: dict[str, Any]) -> list[dict[str, Any]]:
    if state.get("result") or state.get("phase") not in {"bet", "play"}:
        return []
    seat = state["to_move"]
    phase = state["phase"]
    actions: list[dict[str, Any]] = []
    if phase == "bet":
        stack = int(state["stacks"].get(seat, 0))
        for amount in _menu(state):
            if amount <= stack:
                actions.append({"path": ["bet", str(amount)], "notation": f"Ставка {amount}", "promotion": None})
        return actions
    actions.append({"path": ["act", "hit"], "notation": "Ещё", "promotion": None})
    actions.append({"path": ["act", "stand"], "notation": "Хватит", "promotion": None})
    bet = int(state["committed"].get(seat, 0))
    if len(state["hands"].get(seat, [])) == 2 and int(state["stacks"].get(seat, 0)) >= bet:
        actions.append({"path": ["act", "double"], "notation": "Удвоить", "promotion": None})
    return actions


def apply(state: dict[str, Any], path: list[str]) -> tuple[dict[str, Any], list[tuple[str, int]]]:
    nxt = json.loads(dumps(state))
    allowed = [list(item["path"]) for item in legal(nxt)]
    if list(path) not in allowed:
        raise ValueError("Такой ход в блэкджеке не принимается.")
    seat = nxt["to_move"]
    charges: list[tuple[str, int]] = []
    if path[0] == "bet":
        amount = int(path[1])
        nxt["stacks"][seat] = int(nxt["stacks"][seat]) - amount
        nxt["committed"][seat] = amount
        charges.append((seat, amount))
        nxt_seat = _next_bettor(nxt, seat)
        if nxt_seat is None:
            _open_cards(nxt)
        else:
            nxt["to_move"] = nxt_seat
        return nxt, charges
    nxt.setdefault("acts", {})
    nxt["acts"][seat] = path[1]
    if path[1] == "double":
        extra = int(nxt["committed"][seat])
        nxt["stacks"][seat] = int(nxt["stacks"][seat]) - extra
        nxt["committed"][seat] = extra * 2
        charges.append((seat, extra))
        nxt["hands"][seat].extend(_draw(nxt))
        nxt["status"][seat] = "bust" if _total(nxt["hands"][seat]) > 21 else "stand"
    elif path[1] == "hit":
        nxt["hands"][seat].extend(_draw(nxt))
        if _total(nxt["hands"][seat]) > 21:
            nxt["status"][seat] = "bust"
        elif _total(nxt["hands"][seat]) == 21:
            nxt["status"][seat] = "stand"
    else:
        nxt["status"][seat] = "stand"
    _advance_player(nxt)
    return nxt, charges


def _open_cards(state: dict[str, Any]) -> None:
    for seat in state["order"]:
        if int(state["committed"].get(seat, 0)) <= 0:
            state["status"][seat] = "out"
            continue
        state["hands"][seat] = _draw(state, 2)
        state["status"][seat] = "blackjack" if _blackjack(state["hands"][seat]) else "open"
    state["dealer"] = _draw(state, 2)
    if _blackjack(state["dealer"]) or all(state["status"][seat] != "open" for seat in state["order"]):
        _settle(state)
        return
    state["phase"] = "play"
    state["hole"] = True
    state["to_move"] = _next_open(state, "")


def _next_open(state: dict[str, Any], after: str) -> str | None:
    order = list(state["order"])
    start = order.index(after) + 1 if after in order else 0
    for step in range(len(order)):
        seat = order[(start + step) % len(order)]
        if state["status"].get(seat) == "open":
            return seat
    return None


def _advance_player(state: dict[str, Any]) -> None:
    nxt = _next_open(state, state["to_move"])
    if nxt is None:
        _settle(state)
        return
    state["to_move"] = nxt


def _soft(cards: list[str]) -> bool:
    total = 0
    aces = 0
    for card in cards:
        rank = card[0]
        if rank == "A":
            aces += 1
            total += 11
        elif rank in "TJQK":
            total += 10
        else:
            total += int(rank)
    while total > 21 and aces:
        total -= 10
        aces -= 1
    return aces > 0 and total <= 21


def _dealer_stands(cards: list[str], level: int) -> bool:
    total = _total(cards)
    if total > 21:
        return True
    if level >= 4 and total == 17 and _soft(cards):
        return False
    floor = 17 if level >= 3 else 16 if level == 2 else 15
    return total >= floor


def _settle(state: dict[str, Any]) -> None:
    level = max(1, min(5, int(state.get("level") or 3)))
    while state["dealer"] and not _dealer_stands(state["dealer"], level):
        state["dealer"].extend(_draw(state))
    dealer_total = _total(state["dealer"])
    dealer_bust = dealer_total > 21
    dealer_bj = _blackjack(state["dealer"])
    payout: dict[str, int] = {}
    notes: list[str] = []
    profits: dict[str, int] = {}
    for seat in state["order"]:
        bet = int(state["committed"].get(seat, 0))
        cards = list(state["hands"].get(seat, []))
        if bet <= 0 or not cards:
            payout[seat] = 0
            profits[seat] = 0
            continue
        player_bj = _blackjack(cards)
        total = _total(cards)
        if total > 21:
            back = 0
            notes.append("перебор")
        elif player_bj and dealer_bj:
            back = bet
        elif player_bj:
            back = bet + (bet * 3) // 2
        elif dealer_bj or (not dealer_bust and dealer_total > total):
            back = 0
        elif dealer_bust or total > dealer_total:
            back = bet * 2
        else:
            back = bet
        payout[seat] = back
        profits[seat] = back - bet
    state["payout"] = payout
    state["hole"] = False
    state["phase"] = "done"
    state["reason"] = "showdown"
    winners = [seat for seat, profit in profits.items() if profit > 0]
    if len(state["order"]) == 1:
        profit = profits.get(state["order"][0], 0)
        if profit > 0:
            state["result"] = f"{state['order'][0]}_win"
            state["line"] = "Выигрыш у дилера."
        elif profit < 0:
            state["result"] = "black_win" if state["order"][0] == "white" else "draw"
            state["line"] = "Дилер забирает ставку."
            if state["order"][0] != "white":
                state["result"] = "draw"
        else:
            state["result"] = "draw"
            state["line"] = "Ничья с дилером. Ставка возвращена."
        return
    if len(winners) == 1:
        state["result"] = f"{winners[0]}_win"
        state["line"] = "Один игрок остался в плюсе."
    else:
        state["result"] = "draw"
        state["line"] = "Раздача закрыта." if not notes else "Раздача закрыта."


def suggest(state: dict[str, Any], level: int = 3) -> list[str] | None:
    actions = legal(state)
    if not actions:
        return None
    if state["phase"] == "bet":
        wanted = {1: 10, 2: 10, 3: 25, 4: 50, 5: 50}[max(1, min(5, level))]
        affordable = [item for item in actions if int(item["path"][1]) <= wanted]
        return list((affordable or actions)[-1]["path"])
    seat = state["to_move"]
    total = _total(state["hands"][seat])
    up = state["dealer"][0] if state["dealer"] else "7S"
    up_value = _total([up])
    stand = ["act", "stand"]
    hit = ["act", "hit"]
    if any(item["path"] == ["act", "double"] for item in actions) and 9 <= total <= 11 and level >= 3:
        return ["act", "double"]
    limit = 17 if level >= 4 else 16 if level >= 2 else 15
    if total >= limit:
        return stand
    if total >= 12 and up_value <= 6 and level >= 3:
        return stand
    return hit


def leave(state: dict[str, Any], seat: str) -> dict[str, Any]:
    nxt = json.loads(dumps(state))
    if nxt.get("result"):
        return nxt
    nxt["status"][seat] = "bust"
    nxt["phase"] = "done"
    nxt["result"] = "draw"
    nxt["reason"] = "left"
    nxt["line"] = "Игрок вышел из-за стола."
    nxt["payout"] = {key: 0 for key in nxt["order"]}
    return nxt


def cash_out(state: dict[str, Any]) -> dict[str, int] | None:
    stacks = state.get("stacks")
    if not isinstance(stacks, dict) or state.get("kind") != "blackjack":
        return None
    payout = state.get("payout") if isinstance(state.get("payout"), dict) else {}
    return {str(seat): int(stacks.get(seat, 0)) + int(payout.get(seat, 0)) for seat in stacks}


def replay(initial: str, payloads: list[dict[str, Any]]) -> dict[str, Any]:
    state = loads(initial)
    for payload in payloads:
        if payload.get("leave"):
            state = leave(state, str(payload.get("seat") or state.get("to_move") or "white"))
            continue
        path = payload.get("path") or []
        state, _charges = apply(state, [str(item) for item in path])
    return state


def _showdown(state: dict[str, Any]) -> tuple[dict[str, str], dict[str, str], list[str], str]:
    committed = state.get("committed") or {}
    payout = state.get("payout") or {}
    hands = state.get("hands") or {}
    notes: dict[str, str] = {}
    outcomes: dict[str, str] = {}
    winners: list[str] = []
    for seat in state.get("order") or []:
        bet = int(committed.get(seat, 0) or 0)
        cards = list(hands.get(seat) or [])
        back = int(payout.get(seat, 0) or 0)
        if bet <= 0 or not cards:
            outcomes[seat] = "out"
            notes[seat] = "без ставки"
            continue
        profit = back - bet
        if _total(cards) > 21:
            outcomes[seat] = "bust"
            word = "перебор"
        elif profit > 0 and _blackjack(cards):
            outcomes[seat] = "blackjack"
            word = "блэкджек"
            winners.append(seat)
        elif profit > 0:
            outcomes[seat] = "win"
            word = "выиграл"
            winners.append(seat)
        elif profit < 0:
            outcomes[seat] = "loss"
            word = "проиграл"
        else:
            outcomes[seat] = "push"
            word = "ничья"
        notes[seat] = f"{word} · ставка {bet}"
    dealer = list(state.get("dealer") or [])
    if not dealer:
        detail = ""
    else:
        total = _total(dealer)
        detail = "Дилер: перебор." if total > 21 else f"Дилер: {total}."
    return notes, outcomes, winners, detail


def chronicle(initial: str, payloads: list[dict[str, Any]], final: dict[str, Any] | None = None) -> dict[str, Any]:
    state = final if isinstance(final, dict) else replay(initial, payloads)
    result = str(state.get("result") or "")
    reason = str(state.get("reason") or "")
    winner = result[:-4] if result.endswith("_win") and result != "black_win" else ""
    hands = {}
    if result:
        hands = {seat: list(cards) for seat, cards in state.get("hands", {}).items()}
        hands["dealer"] = list(state.get("dealer") or [])
    if reason == "showdown":
        notes, outcomes, winners, detail = _showdown(state)
    else:
        notes = {
            seat: f"ставка {int((state.get('committed') or {}).get(seat, 0))}"
            for seat in state.get("order") or []
        }
        outcomes = {}
        winners = [winner] if winner else []
        detail = ""
    return {
        "done": bool(result),
        "winner": winner,
        "winners": winners,
        "loser": "",
        "line": str(state.get("line") or ""),
        "reason": reason,
        "board": list(state.get("dealer") or []),
        "pot": sum(int(amount) for amount in (state.get("committed") or {}).values()),
        "counts": {"play": len(payloads)},
        "hands": hands,
        "notes": notes,
        "outcomes": outcomes,
        "detail": detail,
        "payout": state.get("payout") or {},
        "last": {},
    }


def view(state: dict[str, Any], seat: str | None) -> dict[str, Any]:
    phase = state.get("phase")
    done = phase == "done"
    hand = list(state.get("hands", {}).get(seat, [])) if seat and phase not in {"waiting", "bet"} else []
    dealer = list(state.get("dealer") or [])
    visible = dealer if done or not state.get("hole", True) else dealer[:1]
    hole = bool(dealer) and not done and bool(state.get("hole", True))
    if phase == "waiting":
        message = "Ждём игроков за стол."
    elif phase == "bet":
        message = "Сделайте ставку фишками."
    elif phase == "play":
        message = f"У вас {_total(hand)}. Дилер показывает {label(visible[0]) if visible else 'карту'}."
    else:
        message = str(state.get("line") or "Раздача закрыта.")
    roster = [
        {
            "key": key,
            "count": len(state.get("hands", {}).get(key, [])),
            "folded": state.get("status", {}).get(key) in {"bust", "out"},
        }
        for key in state.get("order") or []
    ]
    shown = {}
    if done:
        shown = {key: list(cards) for key, cards in state.get("hands", {}).items()}
        shown["dealer"] = dealer
    return {
        "hand": hand,
        "top": "",
        "color": None,
        "phase": phase,
        "roster": roster,
        "opponent_count": len(dealer),
        "deck": len(state.get("deck") or []),
        "actions": legal(state) if seat and state.get("to_move") == seat and not state.get("result") else [],
        "message": message,
        "pot": sum(int(amount) for amount in (state.get("committed") or {}).values()),
        "board": dealer,
        "pairs": [],
        "trump": "",
        "trump_card": "",
        "hole": hole,
        "talon": [],
        "contract": "Блэкджек",
        "shown": shown,
        "status": {str(key): str(value) for key, value in (state.get("status") or {}).items()},
        "acts": {str(key): str(value) for key, value in (state.get("acts") or {}).items()},
        "outcomes": _showdown(state)[1] if done else {},
        "stacks": state.get("stacks") or {},
        "committed": state.get("committed") or {},
    }
