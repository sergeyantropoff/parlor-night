"""Преферанс на троих. Банк — игровые фишки, не деньги.

Колода в 32 карты, по десять на руки и две в прикуп.
Торг идёт от шести в пиках до десяти без козыря. Мизер дороже семёрки без козыря и дешевле восьмёрки.
Распасы — если все пасуют. Кто взял игру, забирает прикуп, может повысить заказ и сбрасывает две карты.
Соперники вистуют или пасуют.

Партия идёт, пока у каждого в пуле не наберётся выбранное число очков. Обычная пуля — 12.
Шестёрка стоит 2, дальше каждая ступень добавляет 2, мизер стоит 10. Лишние взятки дописывают в пулю.
Сверх выбранного числа очки уходят в висты на обоих соперников. Невзятая игра пишется в гору.
Цена очка выбирается до первой сдачи. На стол садится стек в 100 таких очков:
при цене 1 это 100 фишек, при цене 10 — 1000. Со счёта списывается только стек.
Если фишек меньше, партия не начинается. Остановка возвращает стек.
Стеки лежат на столе и не двигаются, пока пуля открыта.
В конце расписка переводит разницу итогов в фишки, но не больше стека. Счёт в минус не уходит.
"""

from __future__ import annotations

import json
import math
import random
import secrets
from typing import Any

from app.cards.deck import SUITS, label, rank_value

RANKS = "789TJQKA"
SUIT_ORDER = ("S", "C", "D", "H", "NT")
SUIT_TITLE = {"S": "пики", "C": "трефы", "D": "бубны", "H": "черви", "NT": "без козыря"}
POOLS = (6, 10, 12, 16, 20)
STAKES = (1, 2, 5, 10)
STACK_POINTS = 100
STACK = STACK_POINTS * 10
ANTE = 10


def waiting(order: list[str] | None = None, variant: str = "classic") -> dict[str, Any]:
    seats = list(order or ["p0", "p1", "p2"])
    state = _shell(seats, "waiting")
    pool = _pool_of(variant)
    state["pool"] = pool
    state["variant"] = f"pool-{pool}"
    state["stake"] = 1
    return state


def waiting_table(seat_keys: list[str], variant: str = "classic") -> dict[str, Any]:
    return waiting(seat_keys, variant)


def deal(
    order: list[str] | None = None,
    variant: str = "classic",
    purses: dict[str, int] | None = None,
) -> dict[str, Any]:
    seats = list(order or ["p0", "p1", "p2"])
    if len(seats) != 3:
        raise ValueError("В преферансе трое игроков.")
    pool = _pool_of(variant)
    state = _shell(seats, "bid")
    state["pool"] = pool
    state["variant"] = f"pool-{pool}"
    state["stake"] = 1
    state["stacks"] = _stacks(seats, purses)
    state["seed"] = secrets.randbits(31)
    state["deals"] = 1
    state["opener"] = 0
    _lay_deal(state)
    state["committed"] = {seat: 0 for seat in seats}
    state["to_move"] = seats[0]
    return state


def deal_table(
    seat_keys: list[str],
    variant: str = "classic",
    purses: dict[str, int] | None = None,
) -> dict[str, Any]:
    return deal(seat_keys, variant, purses)


def _shell(seats: list[str], phase: str) -> dict[str, Any]:
    return {
        "kind": "preferans",
        "variant": "classic",
        "phase": phase,
        "to_move": seats[0],
        "order": seats,
        "hands": {seat: [] for seat in seats},
        "talon": [],
        "bidding": {seat: "open" for seat in seats},
        "contract": None,
        "declarer": "",
        "whist": {},
        "trump": "",
        "trick": [],
        "trick_seats": [],
        "last_trick": [],
        "last_trick_seats": [],
        "last_trick_winner": "",
        "last_write": {},
        "tricks": {seat: 0 for seat in seats},
        "lead": "",
        "committed": {seat: 0 for seat in seats},
        "stacks": {},
        "stake": 0,
        "chips": {},
        "owed": {},
        "unpaid": {},
        "payout": {},
        "result": None,
        "reason": None,
        "line": "",
        "played": [],
        "pool": 12,
        "seed": 1,
        "deals": 0,
        "opener": 0,
        "bullet": {seat: 0 for seat in seats},
        "mountain": {seat: 0 for seat in seats},
        "whists": {seat: {other: 0 for other in seats if other != seat} for seat in seats},
        "sheet": None,
    }


def stake_of(value: object) -> int:
    try:
        stake = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 1
    return stake if stake in STAKES else 1


def stack_for(value: object) -> int:
    return stake_of(value) * STACK_POINTS


def _stacks(seats: list[str], purses: dict[str, int] | None) -> dict[str, int]:
    given: dict[str, int] = {}
    for key, value in (purses or {}).items():
        try:
            given[str(key)] = max(0, int(value))
        except (TypeError, ValueError):
            continue
    return {seat: given[seat] if seat in given else STACK for seat in seats}


def _chip_word(count: int) -> str:
    number = abs(int(count))
    if number % 10 == 1 and number % 100 != 11:
        return "фишка"
    if number % 10 in {2, 3, 4} and number % 100 not in {12, 13, 14}:
        return "фишки"
    return "фишек"


def _staked(state: dict[str, Any]) -> bool:
    stacks = state.get("stacks")
    return int(state.get("stake") or 0) in STAKES and isinstance(stacks, dict) and bool(stacks)


def _pool_of(variant: str) -> int:
    text = str(variant or "")
    if text.startswith("pool-"):
        try:
            size = int(text.split("-", 1)[1])
        except ValueError:
            size = 12
        if size in POOLS:
            return size
    return 12


def _shuffled(seed: int) -> list[str]:
    cards = [rank + suit for rank in RANKS for suit in SUITS]
    random.Random(seed).shuffle(cards)
    return cards


def _lay_deal(state: dict[str, Any]) -> None:
    deck = _shuffled(int(state["seed"]) + int(state["deals"]))
    seats = list(state["order"])
    state["hands"] = {seat: [deck.pop() for _ in range(10)] for seat in seats}
    state["talon"] = [deck.pop(), deck.pop()]


def _ensure(state: dict[str, Any]) -> None:
    seats = list(state.get("order") or [])
    state["pool"] = int(state.get("pool") or _pool_of(str(state.get("variant") or "")))
    state.setdefault("seed", 1)
    state.setdefault("deals", 1)
    state.setdefault("opener", 0)
    bullet = state.setdefault("bullet", {})
    mountain = state.setdefault("mountain", {})
    whists = state.setdefault("whists", {})
    for seat in seats:
        bullet.setdefault(seat, 0)
        mountain.setdefault(seat, 0)
        row = whists.setdefault(seat, {})
        for other in seats:
            if other != seat:
                row.setdefault(other, 0)


def dumps(state: dict[str, Any]) -> str:
    return json.dumps(state, ensure_ascii=False, separators=(",", ":"))


def loads(text: str) -> dict[str, Any]:
    state = json.loads(text)
    if not isinstance(state, dict) or state.get("kind") != "preferans":
        raise ValueError("Это не стол преферанса.")
    return state


def _value(card: str) -> int:
    return rank_value(card, RANKS)


def _contract_rank(contract: dict[str, Any] | None) -> float:
    if not contract:
        return -1
    if contract.get("miser"):
        return 7 * 5 + 4 + 0.5
    return int(contract["level"]) * 5 + SUIT_ORDER.index(str(contract["suit"]))


def _contract_need(contract: dict[str, Any] | None) -> int | None:
    if not isinstance(contract, dict) or contract.get("raspasy"):
        return None
    if contract.get("miser"):
        return 0
    if contract.get("level") is None:
        return None
    return int(contract["level"])


def _contract_title(contract: dict[str, Any] | None) -> str:
    if not contract:
        return "Распасы"
    if contract.get("miser"):
        return "Мизер"
    if contract.get("raspasy"):
        return "Распасы"
    return f"{contract['level']} {SUIT_TITLE[str(contract['suit'])]}"


def _next(state: dict[str, Any], seat: str) -> str:
    order = list(state["order"])
    return order[(order.index(seat) + 1) % len(order)]


def _raise_bids(state: dict[str, Any], *, allow_pass: bool, allow_miser: bool) -> list[dict[str, Any]]:
    current = _contract_rank(state.get("contract"))
    actions: list[dict[str, Any]] = []
    if allow_pass:
        actions.append({"path": ["bid", "pass"], "notation": "Пас", "promotion": None})
    if allow_miser and current < 7 * 5 + 4 + 0.5:
        actions.append({"path": ["bid", "miser"], "notation": "Мизер", "promotion": None})
    for level in range(6, 11):
        for suit in SUIT_ORDER:
            rank = level * 5 + SUIT_ORDER.index(suit)
            if rank > current:
                actions.append(
                    {
                        "path": ["bid", str(level), suit],
                        "notation": f"{level} {SUIT_TITLE[suit]}",
                        "promotion": None,
                    }
                )
    return actions


def legal(state: dict[str, Any]) -> list[dict[str, Any]]:
    if state.get("result"):
        return []
    phase = state.get("phase")
    seat = state.get("to_move")
    actions: list[dict[str, Any]] = []
    if phase == "bid":
        return _raise_bids(state, allow_pass=True, allow_miser=True)
    if phase == "discard":
        actions.extend(_raise_bids(state, allow_pass=False, allow_miser=False))
        hand = list(state["hands"][seat])
        seen: set[tuple[str, str]] = set()
        for left in range(len(hand)):
            for right in range(left + 1, len(hand)):
                pair = tuple(sorted((hand[left], hand[right])))
                if pair in seen:
                    continue
                seen.add(pair)
                actions.append(
                    {
                        "path": ["discard", pair[0], pair[1]],
                        "notation": f"Сброс {label(pair[0])} и {label(pair[1])}",
                        "promotion": None,
                    }
                )
        return actions
    if phase == "whist":
        actions.append({"path": ["whist", "yes"], "notation": "Вист", "promotion": None})
        actions.append({"path": ["whist", "half"], "notation": "Полвиста", "promotion": None})
        actions.append({"path": ["whist", "no"], "notation": "Пас на вист", "promotion": None})
        return actions
    if phase == "play":
        hand = list(state["hands"][seat])
        for card in _playable(state, seat):
            actions.append({"path": ["play", card], "notation": label(card), "promotion": None})
        del hand
        return actions
    return []


def _playable(state: dict[str, Any], seat: str) -> list[str]:
    hand = list(state["hands"][seat])
    trick = list(state.get("trick") or [])
    if not trick:
        return list(dict.fromkeys(hand))
    led = trick[0][1]
    same = [card for card in hand if card[1] == led]
    return list(dict.fromkeys(same or hand))


def apply(state: dict[str, Any], path: list[str]) -> tuple[dict[str, Any], list[tuple[str, int]]]:
    nxt = json.loads(dumps(state))
    _ensure(nxt)
    allowed = [list(item["path"]) for item in legal(nxt)]
    if list(path) not in allowed:
        raise ValueError("Такой ход в преферансе не принимается.")
    seat = nxt["to_move"]
    if path[0] == "bid":
        revising = nxt["phase"] == "discard"
        if not revising:
            nxt["last_trick"] = []
            nxt["last_trick_seats"] = []
            nxt["last_trick_winner"] = ""
            nxt["last_write"] = {}
        if path[1] == "pass":
            nxt["bidding"][seat] = "passed"
        elif path[1] == "miser":
            nxt["contract"] = {"miser": True}
            nxt["bidding"][seat] = "bid"
        else:
            nxt["contract"] = {"level": int(path[1]), "suit": path[2]}
            nxt["bidding"][seat] = "bid"
        if revising:
            suit = str(nxt["contract"].get("suit") or "")
            nxt["trump"] = "" if suit in {"", "NT"} else suit
            return nxt, []
        _after_bid(nxt)
        return nxt, []
    if path[0] == "discard":
        for card in path[1:]:
            nxt["hands"][seat].remove(card)
        nxt["talon"] = []
        _after_discard(nxt)
        return nxt, []
    if path[0] == "whist":
        nxt["whist"][seat] = path[1] if path[1] in {"yes", "half", "no"} else "no"
        _after_whist(nxt)
        return nxt, []
    card = path[1]
    nxt["hands"][seat].remove(card)
    nxt["trick"].append(card)
    nxt["trick_seats"].append(seat)
    nxt["played"].append(card)
    if len(nxt["trick"]) < 3:
        nxt["to_move"] = _next(nxt, seat)
        return nxt, []
    winner = _trick_winner(nxt)
    nxt["tricks"][winner] = int(nxt["tricks"].get(winner, 0)) + 1
    nxt["last_trick"] = list(nxt["trick"])
    nxt["last_trick_seats"] = list(nxt["trick_seats"])
    nxt["last_trick_winner"] = winner
    nxt["trick"] = []
    nxt["trick_seats"] = []
    if any(nxt["hands"].values()):
        nxt["to_move"] = winner
        nxt["lead"] = winner
        return nxt, []
    _score(nxt)
    return nxt, []


def _after_bid(state: dict[str, Any]) -> None:
    order = list(state["order"])
    if state.get("contract") is None:
        if all(state["bidding"][seat] == "passed" for seat in order):
            state["contract"] = {"raspasy": True}
            state["declarer"] = ""
            state["trump"] = ""
            state["phase"] = "play"
            state["to_move"] = order[0]
            state["lead"] = order[0]
        else:
            state["to_move"] = _next_open_bidder(state, state["to_move"])
        return
    still = [seat for seat in order if state["bidding"][seat] != "passed"]
    if len(still) == 1:
        _start_declarer(state, still[0])
        return
    state["to_move"] = _next_open_bidder(state, state["to_move"])


def _next_open_bidder(state: dict[str, Any], seat: str) -> str:
    nxt = seat
    for _ in state["order"]:
        nxt = _next(state, nxt)
        if state["bidding"][nxt] != "passed":
            return nxt
    return seat


def _start_declarer(state: dict[str, Any], seat: str) -> None:
    state["declarer"] = seat
    contract = state["contract"]
    if contract.get("miser"):
        state["trump"] = ""
        state["phase"] = "whist"
        state["to_move"] = _next(state, seat)
        return
    state["trump"] = "" if contract["suit"] == "NT" else contract["suit"]
    state["hands"][seat].extend(state["talon"])
    state["phase"] = "discard"
    state["to_move"] = seat


def _after_discard(state: dict[str, Any]) -> None:
    state["phase"] = "whist"
    state["to_move"] = _next(state, state["declarer"])


def _after_whist(state: dict[str, Any]) -> None:
    defenders = [seat for seat in state["order"] if seat != state["declarer"]]
    pending = [seat for seat in defenders if seat not in state["whist"]]
    if pending:
        state["to_move"] = pending[0]
        return
    if any(_whist_mode(value) in {"yes", "half"} for value in state["whist"].values()):
        state["phase"] = "play"
        state["to_move"] = state["declarer"] or state["order"][0]
        state["lead"] = state["to_move"]
        return
    _score(state, blind=True)


def _trick_winner(state: dict[str, Any]) -> str:
    cards = list(state["trick"])
    seats = list(state["trick_seats"])
    trump = str(state.get("trump") or "")
    led = cards[0][1]
    best = 0
    for index, card in enumerate(cards):
        if _outranks(card, cards[best], led, trump):
            best = index
    return seats[best]


def _outranks(card: str, other: str, led: str, trump: str) -> bool:
    if trump:
        if card[1] == trump and other[1] != trump:
            return True
        if card[1] != trump and other[1] == trump:
            return False
        if card[1] == trump and other[1] == trump:
            return _value(card) > _value(other)
    if card[1] == led and other[1] != led:
        return True
    if card[1] != led and other[1] == led:
        return False
    if card[1] == other[1]:
        return _value(card) > _value(other)
    return False


def _cost(contract: dict[str, Any]) -> int:
    if contract.get("miser"):
        return 10
    if contract.get("raspasy"):
        return 0
    return max(0, (int(contract["level"]) - 5) * 2)


def _write_bullet(state: dict[str, Any], seat: str, points: int) -> None:
    if points <= 0:
        return
    pool = int(state["pool"])
    room = max(0, pool - int(state["bullet"].get(seat, 0)))
    into = min(points, room)
    state["bullet"][seat] = int(state["bullet"].get(seat, 0)) + into
    spill = points - into
    if spill <= 0:
        return
    for other in state["order"]:
        if other != seat:
            _write_whist(state, seat, str(other), spill)


def _write_mountain(state: dict[str, Any], seat: str, points: int) -> None:
    if points > 0:
        state["mountain"][seat] = int(state["mountain"].get(seat, 0)) + points


def _write_whist(state: dict[str, Any], owner: str, target: str, points: int) -> None:
    if points <= 0 or owner == target:
        return
    row = state["whists"].setdefault(owner, {})
    row[target] = int(row.get(target, 0)) + points


def _previous_trick(state: dict[str, Any]) -> dict[str, Any]:
    cards = [str(card) for card in (state.get("last_trick") or [])]
    winner = str(state.get("last_trick_winner") or "")
    if len(cards) < 3 or not winner:
        return {}
    return {
        "cards": cards,
        "seats": [str(item) for item in (state.get("last_trick_seats") or [])],
        "winner": winner,
    }


def _remember_deal(state: dict[str, Any], before_bullet: dict[str, int], before_mountain: dict[str, int]) -> None:
    wrote: dict[str, str] = {}
    for seat in state["order"]:
        key = str(seat)
        bullet = int(state["bullet"].get(key, 0)) > int(before_bullet.get(key, 0))
        mountain = int(state["mountain"].get(key, 0)) > int(before_mountain.get(key, 0))
        if bullet and mountain:
            wrote[key] = "both"
        elif bullet:
            wrote[key] = "bullet"
        elif mountain:
            wrote[key] = "mountain"
    state["last_write"] = wrote


def _score(state: dict[str, Any], *, blind: bool = False) -> None:
    _ensure(state)
    seats = list(state["order"])
    before_bullet = {str(seat): int(state["bullet"].get(seat, 0)) for seat in seats}
    before_mountain = {str(seat): int(state["mountain"].get(seat, 0)) for seat in seats}
    contract = state.get("contract") or {"raspasy": True}
    declarer = str(state.get("declarer") or "")
    tricks = {seat: int(state["tricks"].get(seat, 0)) for seat in seats}
    title = _contract_title(contract)
    if contract.get("raspasy") or not declarer:
        for seat, count in tricks.items():
            _write_mountain(state, seat, count)
        fewest = min(tricks.values()) if tricks else 0
        winners = [seat for seat, count in tricks.items() if count == fewest]
        if len(winners) == 1:
            _write_bullet(state, winners[0], 2)
        state["line"] = "Распасы записаны в гору."
    elif contract.get("miser"):
        made = blind or tricks.get(declarer, 0) == 0
        if made:
            _write_bullet(state, declarer, 10)
            state["line"] = "Оба спасовали. Мизер записан без розыгрыша." if blind else "Мизер взят: 10 в пулю."
        else:
            _write_mountain(state, declarer, 10)
            for seat in seats:
                if seat == declarer:
                    continue
                points = max(2, 2 * tricks.get(declarer, 0))
                if _whist_mode((state.get("whist") or {}).get(seat)) == "half":
                    points = _whist_points("half", points)
                _write_whist(state, seat, declarer, points)
            state["line"] = "Мизер не взят: 10 в гору."
    else:
        need = int(contract["level"])
        taken = need if blind else tricks.get(declarer, 0)
        price = _cost(contract)
        if taken >= need:
            _write_bullet(state, declarer, price + (taken - need))
            _award_whists(state, declarer)
            if blind:
                state["line"] = f"Оба спасовали на вист. {title} записана без розыгрыша."
            else:
                state["line"] = f"{title} взята: {taken} из {need}."
        else:
            _write_mountain(state, declarer, price)
            _award_whists(state, declarer)
            state["line"] = f"{title} не взята: {taken} из {need}."
    _remember_deal(state, before_bullet, before_mountain)
    if _closed(state):
        _finish(state)
        return
    _redeal(state)


def _closed(state: dict[str, Any]) -> bool:
    pool = int(state["pool"])
    return all(int(state["bullet"].get(seat, 0)) >= pool for seat in state["order"])


def _balance(state: dict[str, Any], seat: str) -> int:
    own = sum(int(points) for points in (state["whists"].get(seat) or {}).values())
    against = sum(int((state["whists"].get(other) or {}).get(seat, 0)) for other in state["order"] if other != seat)
    return int(state["bullet"].get(seat, 0)) - int(state["mountain"].get(seat, 0)) + own - against


def _chip_deltas(scores: dict[str, int], stake: int) -> dict[str, int]:
    seats = list(scores)
    if not seats:
        return {}
    mean = sum(scores.values()) / len(seats)
    raw = [(scores[seat] - mean) * stake for seat in seats]
    base = [math.floor(value) for value in raw]
    leftover = int(round(sum(raw) - sum(base)))
    if leftover > 0:
        order = sorted(range(len(seats)), key=lambda index: (raw[index] - base[index], -index), reverse=True)
        for index in order[:leftover]:
            base[index] += 1
    elif leftover < 0:
        order = sorted(range(len(seats)), key=lambda index: (base[index] - raw[index], index), reverse=True)
        for index in order[: -leftover]:
            base[index] -= 1
    return {seat: base[index] for index, seat in enumerate(seats)}


def _move_stacks(state: dict[str, Any], owed: dict[str, int]) -> None:
    seats = [str(seat) for seat in state["order"]]
    stacks = {seat: max(0, int((state.get("stacks") or {}).get(seat, 0))) for seat in seats}
    moved = {seat: 0 for seat in seats}
    unpaid = {seat: 0 for seat in seats}
    pot = 0
    for seat in seats:
        amount = int(owed.get(seat, 0))
        if amount >= 0:
            continue
        can = min(-amount, stacks[seat])
        stacks[seat] -= can
        moved[seat] = -can
        unpaid[seat] = -amount - can
        pot += can
    winners = [seat for seat in seats if int(owed.get(seat, 0)) > 0]
    due = sum(int(owed[seat]) for seat in winners)
    if winners and due and pot:
        shares = {seat: pot * int(owed[seat]) // due for seat in winners}
        left = pot - sum(shares.values())
        for seat in sorted(winners, key=lambda item: int(owed[item]), reverse=True):
            if left <= 0:
                break
            shares[seat] += 1
            left -= 1
        for seat in winners:
            stacks[seat] += shares[seat]
            moved[seat] = shares[seat]
            unpaid[seat] = int(owed[seat]) - shares[seat]
    elif winners and due:
        for seat in winners:
            unpaid[seat] = int(owed[seat])
    state["stacks"] = stacks
    state["chips"] = moved
    state["owed"] = {seat: int(owed.get(seat, 0)) for seat in seats}
    state["unpaid"] = unpaid
    state["payout"] = {seat: stacks[seat] for seat in seats}


def _finish(state: dict[str, Any], *, reason: str = "score", line: str = "") -> None:
    seats = list(state["order"])
    scores = {seat: _balance(state, seat) for seat in seats}
    best = max(scores.values()) if scores else 0
    leaders = [seat for seat, score in scores.items() if score == best]
    if _staked(state):
        _move_stacks(state, _chip_deltas(scores, int(state["stake"])))
    else:
        mean = sum(scores.values()) / len(scores) if scores else 0
        payout = {seat: max(0, int(round((scores[seat] - mean) * 5))) for seat in seats}
        if sum(payout.values()) == 0:
            payout = {seat: ANTE for seat in seats}
        state["payout"] = payout
    state["phase"] = "done"
    state["reason"] = reason
    state["result"] = f"{leaders[0]}_win" if len(leaders) == 1 else "draw"
    pool = int(state["pool"])
    note = line or f"Пуля до {pool} закрыта. Расписка готова."
    if _staked(state) and any(int(value) > 0 for value in (state.get("unpaid") or {}).values()):
        note = f"{note} На стеке не хватило части фишек."
    state["line"] = note
    state["sheet"] = _public_sheet(state, closed=True)
    state["pot"] = sum(int(amount) for amount in (state.get("stacks") or state.get("committed") or {}).values())


def _redeal(state: dict[str, Any]) -> None:
    seats = list(state["order"])
    note = str(state.get("line") or "")
    state["deals"] = int(state.get("deals") or 1) + 1
    state["opener"] = (int(state.get("opener") or 0) + 1) % len(seats)
    state["bidding"] = {seat: "open" for seat in seats}
    state["contract"] = None
    state["declarer"] = ""
    state["whist"] = {}
    state["trump"] = ""
    state["trick"] = []
    state["trick_seats"] = []
    state["tricks"] = {seat: 0 for seat in seats}
    state["played"] = []
    state["lead"] = ""
    state["committed"] = {seat: 0 for seat in seats}
    state["payout"] = {}
    state["result"] = None
    state["reason"] = None
    state["phase"] = "bid"
    state["to_move"] = seats[int(state["opener"])]
    state["line"] = note
    _lay_deal(state)


def _public_sheet(state: dict[str, Any], *, closed: bool) -> dict[str, Any]:
    seats = list(state["order"])
    return {
        "pool": int(state["pool"]),
        "closed": closed,
        "seats": seats,
        "bullet": {seat: int(state["bullet"].get(seat, 0)) for seat in seats},
        "mountain": {seat: int(state["mountain"].get(seat, 0)) for seat in seats},
        "whists": {
            seat: {other: int((state["whists"].get(seat) or {}).get(other, 0)) for other in seats if other != seat}
            for seat in seats
        },
        "total": {seat: _balance(state, seat) for seat in seats},
        "stake": int(state["stake"]) if int(state.get("stake") or 0) in STAKES else 0,
        "stacks": _named_bag(state.get("stacks"), seats) if state.get("stacks") else {},
        "chips": _named_bag(state.get("chips"), seats) if state.get("chips") else {},
        "unpaid": _named_bag(state.get("unpaid"), seats) if state.get("unpaid") else {},
    }


def _named_bag(bag: object, seats: list[str]) -> dict[str, int]:
    source = bag if isinstance(bag, dict) else {}
    return {seat: int(source.get(seat, 0) or 0) for seat in seats}


def _note_tone(line: str) -> str:
    text = line.casefold()
    if "не взят" in text:
        return "miss"
    if "взят" in text or "без розыгрыша" in text:
        return "made"
    return "draw"


def _progress(state: dict[str, Any]) -> str:
    pool = int(state.get("pool") or 12)
    parts = [f"{int((state.get('bullet') or {}).get(seat, 0))}/{pool}" for seat in state.get("order") or []]
    return f"Пуля {' · '.join(parts)}."


def _whist_mode(value: object) -> str:
    if value is True or value == "yes":
        return "yes"
    if value == "half":
        return "half"
    return "no"


def _whist_points(mode: str, taken: int) -> int:
    if mode == "half":
        return (int(taken) + 1) // 2
    return int(taken)


def _award_whists(state: dict[str, Any], declarer: str) -> None:
    for seat, raw in (state.get("whist") or {}).items():
        mode = _whist_mode(raw)
        if str(seat) == declarer or mode == "no":
            continue
        _write_whist(state, str(seat), declarer, _whist_points(mode, int(state["tricks"].get(seat, 0))))


def _whist_tricks(hand: list[str], trump: str) -> int:
    suits: dict[str, list[int]] = {}
    for card in hand:
        suits.setdefault(card[1], []).append(_value(card))
    tricks = 0
    for suit, ranks in suits.items():
        ranks.sort(reverse=True)
        if trump and suit == trump:
            honors = sum(1 for rank in ranks if rank >= 5)
            tricks += honors + max(0, len(ranks) - 2)
            continue
        if ranks[0] == 7:
            tricks += 1
        if 6 in ranks and len(ranks) >= 2:
            tricks += 1
    return tricks


def _suggest_whist(state: dict[str, Any], seat: str, level: int) -> list[str]:
    contract = state.get("contract") or {}
    hand = list(state["hands"].get(seat) or [])
    if contract.get("miser"):
        highs = sum(1 for card in hand if _value(card) >= 5)
        if highs >= 2 or level >= 3:
            return ["whist", "yes"]
        return ["whist", "half"] if highs == 1 else ["whist", "no"]
    trump = str(state.get("trump") or "")
    tricks = _whist_tricks(hand, trump)
    if tricks >= 2:
        return ["whist", "yes"]
    if tricks == 1:
        return ["whist", "half"]
    return ["whist", "no"]


def suggest(state: dict[str, Any], level: int = 3) -> list[str] | None:
    actions = legal(state)
    if not actions:
        return None
    phase = state["phase"]
    seat = state["to_move"]
    if phase == "bid":
        return _suggest_bid(state, seat, actions, level)
    if phase == "discard":
        return _suggest_discard(state, seat, actions)
    if phase == "whist":
        return _suggest_whist(state, str(seat), level)
    playable = _playable(state, seat)
    trump = str(state.get("trump") or "")
    if not state.get("trick"):
        plain = [card for card in playable if card[1] != trump]
        pool = plain or playable
        pool.sort(key=_value)
        return ["play", pool[0]]
    led = state["trick"][0][1]
    winning = [card for card in playable if _outranks(card, state["trick"][-1], led, trump)]
    pool = winning or playable
    pool.sort(key=_value)
    return ["play", pool[0 if not winning else -1]]


def _suggest_bid(state: dict[str, Any], seat: str, actions: list[dict[str, Any]], level: int) -> list[str]:
    hand = state["hands"][seat]
    best_suit = max(SUIT_ORDER[:-1], key=lambda suit: sum(1 for card in hand if card[1] == suit))
    length = sum(1 for card in hand if card[1] == best_suit)
    highs = sum(1 for card in hand if card[1] == best_suit and _value(card) >= 8)
    target = 0
    if length >= 5 or (length >= 4 and highs >= 2):
        target = min(8, 5 + length // 2 + (1 if level >= 4 else 0))
    elif length >= 4 and level >= 2:
        target = 6
    if target < 6:
        if level >= 5 and sum(1 for card in hand if _value(card) >= 9) >= 4:
            return ["bid", "miser"]
        return ["bid", "pass"]
    wanted = ["bid", str(target), best_suit]
    if list(wanted) in [list(item["path"]) for item in actions]:
        return wanted
    higher = [item for item in actions if item["path"][0] == "bid" and item["path"][1] not in {"pass", "miser"}]
    if not higher:
        return ["bid", "pass"]
    higher.sort(key=lambda item: _contract_rank({"level": int(item["path"][1]), "suit": item["path"][2]}))
    return list(higher[0]["path"])


def _suggest_discard(state: dict[str, Any], seat: str, actions: list[dict[str, Any]]) -> list[str]:
    trump = str(state.get("trump") or "")
    hand = list(state["hands"][seat])
    ranked = sorted(hand, key=lambda card: (_value(card) + (30 if card[1] == trump else 0)))
    drop = tuple(sorted(ranked[:2]))
    drops = [item for item in actions if item["path"][0] == "discard"]
    for item in drops:
        if tuple(sorted(item["path"][1:])) == drop:
            return list(item["path"])
    return list(drops[0]["path"])


def leave(state: dict[str, Any], seat: str) -> dict[str, Any]:
    nxt = json.loads(dumps(state))
    _ensure(nxt)
    if nxt.get("result"):
        return nxt
    _write_mountain(nxt, seat, int(nxt["pool"]))
    _finish(nxt, reason="left", line="Вышел из-за стола. Пуля расписана.")
    return nxt


def replay(initial: str, payloads: list[dict[str, Any]]) -> dict[str, Any]:
    state = loads(initial)
    for payload in payloads:
        if payload.get("leave"):
            state = leave(state, str(payload.get("seat") or state.get("to_move") or "p0"))
            continue
        path = payload.get("path") or []
        state, _charges = apply(state, [str(item) for item in path])
    return state


def _seat_note(state: dict[str, Any], seat: str) -> str:
    order = [str(item) for item in state.get("order") or []]
    scores = {item: _balance(state, item) for item in order}
    best = max(scores.values()) if scores else 0
    leaders = [item for item, score in scores.items() if score == best]
    bullet = int((state.get("bullet") or {}).get(seat, 0))
    mountain = int((state.get("mountain") or {}).get(seat, 0))
    total = scores.get(seat, 0)
    line = f"пуля {bullet} · гора {mountain} · итог {total}"
    if state.get("result") and isinstance(state.get("chips"), dict) and seat in state["chips"]:
        moved = int(state["chips"].get(seat, 0) or 0)
        short = int((state.get("unpaid") or {}).get(seat, 0) or 0)
        if moved or short:
            sign = f"+{moved}" if moved > 0 else str(moved)
            line = f"{line} · {sign} {_chip_word(moved)}"
            if short:
                line = f"{line}, не хватило {short}"
    if not state.get("result"):
        return line
    if len(leaders) == 1 and seat == leaders[0]:
        word = "выиграл"
    elif seat in leaders:
        word = "ничья"
    else:
        word = "проиграл"
    return f"{word} · {line}"


def chronicle(initial: str, payloads: list[dict[str, Any]], final: dict[str, Any] | None = None) -> dict[str, Any]:
    state = final if isinstance(final, dict) else replay(initial, payloads)
    _ensure(state)
    result = str(state.get("result") or "")
    winner = result[:-4] if result.endswith("_win") else ""
    return {
        "done": bool(result),
        "winner": winner,
        "loser": "",
        "line": str(state.get("line") or ""),
        "reason": str(state.get("reason") or ""),
        "board": list(state.get("talon") or []),
        "pot": sum(int(amount) for amount in (state.get("committed") or {}).values()),
        "counts": {"play": len(payloads), "tricks": sum(int(item) for item in (state.get("tricks") or {}).values())},
        "hands": {seat: list(cards) for seat, cards in (state.get("hands") or {}).items()} if result else {},
        "notes": {seat: _seat_note(state, str(seat)) for seat in state.get("order") or []},
        "payout": state.get("payout") or {},
        "sheet": state.get("sheet") or _public_sheet(state, closed=bool(result)),
        "last": {},
    }


def _by_suit(cards: list[str]) -> list[str]:
    order = {suit: index for index, suit in enumerate(("S", "C", "D", "H"))}
    return sorted(cards, key=lambda card: (order.get(card[1], 9), -_value(card)))


def view(state: dict[str, Any], seat: str | None) -> dict[str, Any]:
    _ensure(state)
    phase = state.get("phase")
    raw = list(state.get("hands", {}).get(seat, [])) if seat and phase not in {"waiting", "done"} else []
    hand = _by_suit(raw)
    title = _contract_title(state.get("contract"))
    progress = _progress(state)
    price = ""
    if int(state.get("stake") or 0) in STAKES:
        stake = int(state["stake"])
        price = f"Очко стоит {stake} {_chip_word(stake)}. "
    if phase == "waiting":
        message = f"{progress} {price}Ждём третьего игрока."
    elif phase == "bid":
        trade = f"Сейчас на столе: {title}." if state.get("contract") else "Можно заказать игру или спасовать."
        message = f"{progress} Торг. {trade}"
    elif phase == "discard":
        message = f"{progress} {title}. Можно повысить заказ или сбросить две карты."
    elif phase == "whist":
        message = f"{progress} {title}. Вист, полвиста или пас."
    elif phase == "play":
        message = f"{progress} {title}. Ход во взятку."
    else:
        message = str(state.get("line") or "Пуля закрыта.")
    roster = [
        {"key": key, "count": len(state.get("hands", {}).get(key, [])), "folded": False}
        for key in state.get("order") or []
    ]
    shown = {}
    if phase == "done":
        shown = {key: list(cards) for key, cards in state.get("hands", {}).items()}
    scored = int(state.get("deals") or 1) > 1 or phase == "done"
    live = list(state.get("trick") or [])
    held = False
    board = live
    order = [str(item) for item in state.get("order") or []]
    bidding = state.get("bidding") or {}
    fresh = phase == "bid" and not state.get("contract") and all(
        str(bidding.get(seat) or "open") == "open" for seat in order
    )
    if not live and (phase in {"play", "done"} or fresh):
        board = [str(card) for card in (state.get("last_trick") or [])]
        held = bool(board)
    writes = state.get("last_write") if fresh or phase == "done" else {}
    return {
        "hand": hand,
        "top": state["trick"][-1] if state.get("trick") else "",
        "color": state.get("trump") or None,
        "phase": phase,
        "roster": roster,
        "opponent_count": sum(item["count"] for item in roster if item["key"] != seat),
        "deck": 0,
        "actions": legal(state) if seat and state.get("to_move") == seat and not state.get("result") else [],
        "message": message,
        "pot": sum(int(amount) for amount in (state.get("committed") or {}).values()),
        "board": board,
        "held": held,
        "trick_seats": [str(item) for item in (state.get("last_trick_seats") or [])] if held else [],
        "trick_winner": str(state.get("last_trick_winner") or "") if held else "",
        "previous": _previous_trick(state),
        "writes": writes if isinstance(writes, dict) else {},
        "pairs": [],
        "trump": state.get("trump") or "",
        "trump_card": "",
        "hole": False,
        "talon": [],
        "contract": title if phase != "done" else f"Пуля до {int(state['pool'])}",
        "contract_need": _contract_need(state.get("contract")),
        "declarer": str(state.get("declarer") or ""),
        "tricks": {
            str(seat): int((state.get("tricks") or {}).get(seat, 0))
            for seat in order
        },
        "sheet": state.get("sheet") or _public_sheet(state, closed=phase == "done"),
        "scored": scored,
        "note": str(state.get("line") or "") if scored else "",
        "note_tone": _note_tone(str(state.get("line") or "")) if scored and state.get("line") else "",
        "shown": shown,
        "stacks": _named_bag(state.get("stacks"), [str(item) for item in state.get("order") or []])
        if state.get("stacks")
        else {},
        "committed": state.get("committed") or {},
        "bidding": {
            str(seat): str((state.get("bidding") or {}).get(seat) or "open")
            for seat in state.get("order") or []
        },
        "whist": {
            str(seat): _whist_mode(value)
            for seat, value in (state.get("whist") or {}).items()
        },
    }
