"""Дурак: подкидной и переводной, колода в 36 карт.

Подкидной: бьют карту, затем подкидывают достоинства, которые уже на столе.
Переводной: небитую карту одного достоинства можно перевести следующему,
если у него хватает карт. Козырь бьёт любую другую масть, старший козырь — младший.
Проигравший — тот, кто остался с картами, когда колода кончилась. Если карт не осталось ни у кого, ничья.
"""

from __future__ import annotations

import json
from typing import Any

from app.cards.deck import SUIT_NAME, label, pack, rank_value

RANKS = "6789TJQKA"
VARIANTS = {"podkidnoy": "Подкидной", "perevodnoy": "Переводной"}


def waiting(order: list[str] | None = None, variant: str = "podkidnoy") -> dict[str, Any]:
    seats = list(order or ["white", "black"])
    return {
        "kind": "durak",
        "variant": variant if variant in VARIANTS else "podkidnoy",
        "phase": "waiting",
        "to_move": seats[0],
        "order": seats,
        "hands": {},
        "deck": [],
        "trump": "",
        "trump_card": "",
        "table": [],
        "attacker": "",
        "defender": "",
        "out": [],
        "loser": "",
        "result": None,
        "reason": None,
        "line": "",
    }


def waiting_table(seat_keys: list[str], variant: str = "podkidnoy") -> dict[str, Any]:
    return waiting(seat_keys, variant)


def deal(order: list[str] | None = None, variant: str = "podkidnoy", purses: dict[str, int] | None = None) -> dict[str, Any]:
    del purses
    seats = list(order or ["white", "black"])
    if not 2 <= len(seats) <= 6:
        raise ValueError("В дурака играют от двух до шести.")
    kind = variant if variant in VARIANTS else "podkidnoy"
    deck = pack(RANKS)
    trump_card = deck[0]
    hands: dict[str, list[str]] = {seat: [] for seat in seats}
    for _ in range(6):
        for seat in seats:
            if not deck:
                break
            hands[seat].append(deck.pop())
    state: dict[str, Any] = {
        "kind": "durak",
        "variant": kind,
        "phase": "attack",
        "order": seats,
        "hands": hands,
        "deck": deck,
        "trump": trump_card[1],
        "trump_card": trump_card,
        "table": [],
        "out": [],
        "loser": "",
        "result": None,
        "reason": None,
        "line": "",
        "passed": [],
    }
    attacker = _first_attacker(state)
    state["attacker"] = attacker
    state["opener"] = attacker
    state["defender"] = _next_seat(state, attacker)
    state["to_move"] = attacker
    state["taking"] = False
    state["add_after_take"] = True
    return state


def deal_table(seat_keys: list[str], variant: str = "podkidnoy", purses: dict[str, int] | None = None) -> dict[str, Any]:
    return deal(seat_keys, variant, purses)


def dumps(state: dict[str, Any]) -> str:
    return json.dumps(state, ensure_ascii=False, separators=(",", ":"))


def loads(text: str) -> dict[str, Any]:
    state = json.loads(text)
    if not isinstance(state, dict) or state.get("kind") != "durak":
        raise ValueError("Это не стол дурака.")
    return state


def _rank(card: str) -> int:
    return rank_value(card, RANKS)


def _beats(card: str, other: str, trump: str) -> bool:
    if card[1] == other[1]:
        return _rank(card) > _rank(other)
    return card[1] == trump and other[1] != trump


def _next_seat(state: dict[str, Any], seat: str) -> str:
    order = list(state["order"])
    return order[(order.index(seat) + 1) % len(order)]


def _active(state: dict[str, Any]) -> list[str]:
    gone = set(state.get("out") or [])
    return [seat for seat in state["order"] if seat not in gone and state["hands"].get(seat)]


def _first_attacker(state: dict[str, Any]) -> str:
    trump = state["trump"]
    found: tuple[int, str] | None = None
    for seat in state["order"]:
        for card in state["hands"][seat]:
            if card[1] != trump:
                continue
            score = _rank(card)
            if found is None or score < found[0]:
                found = (score, seat)
    return found[1] if found else state["order"][0]


def _ranks_on_table(state: dict[str, Any]) -> set[str]:
    ranks: set[str] = set()
    for pair in state["table"]:
        ranks.add(pair["attack"][0])
        if pair.get("defense"):
            ranks.add(pair["defense"][0])
    return ranks


def _unbeaten(state: dict[str, Any]) -> list[dict[str, Any]]:
    return [pair for pair in state["table"] if not pair.get("defense")]


def _room(state: dict[str, Any]) -> bool:
    if len(state.get("table") or []) >= 6:
        return False
    if state.get("taking"):
        return bool(state.get("table"))
    defender = state.get("defender")
    if not defender:
        return False
    hand = len(state["hands"].get(defender, []))
    return len(_unbeaten(state)) < hand


def _throwers(state: dict[str, Any]) -> list[str]:
    defender = state["defender"]
    gone = set(state.get("out") or [])
    if state.get("taking") or state["variant"] != "perevodnoy":
        return [seat for seat in state["order"] if seat != defender and seat not in gone]
    attacker = state["attacker"]
    return [attacker] if attacker != defender else []


def legal(state: dict[str, Any]) -> list[dict[str, Any]]:
    if state.get("phase") not in {"attack", "defend", "throw"} or state.get("result"):
        return []
    seat = state["to_move"]
    hand = list(state["hands"].get(seat, []))
    phase = state["phase"]
    actions: list[dict[str, Any]] = []
    if phase == "attack":
        for card in dict.fromkeys(hand):
            actions.append({"path": ["play", card], "notation": f"Ход {label(card)}", "promotion": None})
        return actions
    if phase == "defend":
        target = _unbeaten(state)
        if target:
            attack = target[0]["attack"]
            for card in dict.fromkeys(hand):
                if _beats(card, attack, state["trump"]):
                    actions.append({"path": ["play", card], "notation": f"Бью {label(card)}", "promotion": None})
            if _can_transfer(state, seat):
                rank = attack[0]
                for card in dict.fromkeys(hand):
                    if card[0] == rank:
                        actions.append(
                            {"path": ["play", card], "notation": f"Перевод {label(card)}", "promotion": None}
                        )
        actions.append({"path": ["act", "take"], "notation": "Беру", "promotion": None})
        return actions
    ranks = _ranks_on_table(state)
    if _room(state):
        for card in dict.fromkeys(hand):
            if card[0] in ranks:
                actions.append({"path": ["play", card], "notation": f"Подкидываю {label(card)}", "promotion": None})
    done = "Хватит" if state.get("taking") else "Бито"
    actions.append({"path": ["act", "pass"], "notation": done, "promotion": None})
    return actions


def _can_transfer(state: dict[str, Any], seat: str) -> bool:
    if state["variant"] != "perevodnoy" or state["phase"] != "defend" or seat != state["defender"]:
        return False
    if any(pair.get("defense") for pair in state["table"]):
        return False
    ranks = {pair["attack"][0] for pair in state["table"]}
    if len(ranks) != 1 or not state["table"]:
        return False
    nxt = _next_seat(state, seat)
    if nxt in set(state.get("out") or []):
        return False
    need = len(state["table"]) + 1
    return len(state["hands"].get(nxt, [])) >= need


def apply(state: dict[str, Any], path: list[str]) -> dict[str, Any]:
    nxt = json.loads(dumps(state))
    allowed = [list(item["path"]) for item in legal(nxt)]
    if list(path) not in allowed:
        raise ValueError("Такой ход в дураке не принимается.")
    seat = nxt["to_move"]
    if path[0] == "act" and path[1] == "take":
        _take(nxt)
        return nxt
    if path[0] == "act" and path[1] == "pass":
        _pass(nxt)
        return nxt
    card = path[1]
    nxt["hands"][seat].remove(card)
    if nxt["phase"] == "attack":
        nxt["opener"] = nxt.get("opener") or seat
        nxt["table"] = [{"attack": card, "defense": ""}]
        nxt["phase"] = "defend"
        nxt["to_move"] = nxt["defender"]
        nxt["passed"] = []
        return nxt
    if nxt["phase"] == "throw":
        nxt["table"].append({"attack": card, "defense": ""})
        if nxt.get("taking"):
            _after_take_throw(nxt, seat)
            return nxt
        nxt["phase"] = "defend"
        nxt["to_move"] = nxt["defender"]
        nxt["passed"] = []
        return nxt
    if _can_transfer(nxt, seat) and card[0] == nxt["table"][0]["attack"][0] and not _beats(
        card, nxt["table"][0]["attack"], nxt["trump"]
    ):
        nxt["table"].append({"attack": card, "defense": ""})
        nxt["attacker"] = nxt["defender"]
        nxt["defender"] = _next_seat(nxt, seat)
        nxt["to_move"] = nxt["defender"]
        nxt["phase"] = "defend"
        return nxt
    target = _unbeaten(nxt)[0]
    target["defense"] = card
    if _unbeaten(nxt):
        nxt["to_move"] = nxt["defender"]
        return nxt
    if _room(nxt) and _someone_can_throw(nxt):
        nxt["phase"] = "throw"
        nxt["passed"] = []
        nxt["to_move"] = _first_thrower(nxt)
        return nxt
    _bito(nxt)
    return nxt


def _someone_can_throw(state: dict[str, Any]) -> bool:
    ranks = _ranks_on_table(state)
    for seat in _throwers(state):
        if any(card[0] in ranks for card in state["hands"].get(seat, [])):
            return True
    return False


def _throw_ring(state: dict[str, Any]) -> list[str]:
    order = _throwers(state)
    start = (state.get("opener") or state.get("attacker")) if state.get("taking") else state.get("attacker")
    if start in order:
        index = order.index(start)
        return order[index:] + order[:index]
    return order


def _seat_can_throw(state: dict[str, Any], seat: str) -> bool:
    if seat not in _throwers(state) or not _room(state):
        return False
    ranks = _ranks_on_table(state)
    return any(card[0] in ranks for card in state["hands"].get(seat, []))


def _first_thrower(state: dict[str, Any]) -> str:
    ordered = _throw_ring(state)
    for seat in ordered:
        if _seat_can_throw(state, seat):
            return seat
    return ordered[0] if ordered else str(state.get("attacker") or state["order"][0])


def _finish_throw(state: dict[str, Any]) -> None:
    if state.get("taking"):
        _collect_take(state)
        return
    _bito(state)


def _offer_next_throw(state: dict[str, Any], after: str) -> None:
    ring = _throw_ring(state)
    if after in ring:
        start = ring.index(after)
        ring = ring[start + 1 :] + ring[:start]
    passed = list(state.get("passed") or [])
    for seat in ring:
        if seat in passed:
            continue
        if _seat_can_throw(state, seat):
            state["passed"] = passed
            state["to_move"] = seat
            state["phase"] = "throw"
            return
        passed.append(seat)
    state["passed"] = passed
    _finish_throw(state)


def _after_take_throw(state: dict[str, Any], seat: str) -> None:
    state["phase"] = "throw"
    state["taking"] = True
    if len(state["table"]) >= 6 or not _someone_can_throw(state):
        _collect_take(state)
        return
    if _seat_can_throw(state, seat):
        state["to_move"] = seat
        return
    _offer_next_throw(state, seat)


def _pass(state: dict[str, Any]) -> None:
    passed = list(state.get("passed") or [])
    seat = state["to_move"]
    if seat not in passed:
        passed.append(seat)
    state["passed"] = passed
    if state.get("taking"):
        _offer_next_throw(state, seat)
        return
    ranks = _ranks_on_table(state)
    for nxt in _throwers(state):
        if nxt in passed:
            continue
        if any(card[0] in ranks for card in state["hands"].get(nxt, [])):
            state["to_move"] = nxt
            return
        passed.append(nxt)
        state["passed"] = passed
    _bito(state)


def _keep_table(state: dict[str, Any]) -> None:
    table = state.get("table") or []
    if table:
        state["last_table"] = [dict(pair) for pair in table]


def _take(state: dict[str, Any]) -> None:
    state["passed"] = []
    if state.get("add_after_take") and len(state["table"]) < 6:
        state["taking"] = True
        if _someone_can_throw(state):
            state["phase"] = "throw"
            state["to_move"] = _first_thrower(state)
            return
    _collect_take(state)


def _collect_take(state: dict[str, Any]) -> None:
    defender = state["defender"]
    taken: list[str] = []
    _keep_table(state)
    for pair in state["table"]:
        taken.append(pair["attack"])
        if pair.get("defense"):
            taken.append(pair["defense"])
    state["hands"][defender].extend(taken)
    state["last_bout"] = {"kind": "take", "seat": str(defender)}
    state["table"] = []
    state["taking"] = False
    state["passed"] = []
    _refill(state, defender_last=True)
    if state.get("result"):
        return
    nxt = _next_playing(state, defender)
    if nxt is None:
        _finish(state)
        return
    _open_attack(state, nxt)


def _bito(state: dict[str, Any]) -> None:
    _keep_table(state)
    state["last_bout"] = {"kind": "bito", "seat": str(state.get("defender") or "")}
    state["table"] = []
    defender = state["defender"]
    _refill(state, defender_last=True)
    if state.get("result"):
        return
    nxt = defender if defender not in set(state.get("out") or []) and state["hands"].get(defender) else _next_playing(state, defender)
    if nxt is None:
        _finish(state)
        return
    _open_attack(state, nxt)


def _open_attack(state: dict[str, Any], attacker: str) -> None:
    defender = _next_playing(state, attacker)
    if defender is None or defender == attacker:
        _finish(state)
        return
    state["attacker"] = attacker
    state["opener"] = attacker
    state["defender"] = defender
    state["to_move"] = attacker
    state["phase"] = "attack"
    state["passed"] = []
    state["table"] = []
    state["taking"] = False


def _refill(state: dict[str, Any], *, defender_last: bool) -> None:
    defender = state.get("defender")
    order = [seat for seat in state["order"] if seat != defender]
    start = state.get("attacker")
    if start in order:
        order = order[order.index(start) :] + order[: order.index(start)]
    if defender_last and defender in state["order"]:
        order.append(defender)
    for seat in order:
        while len(state["hands"][seat]) < 6 and state["deck"]:
            state["hands"][seat].append(state["deck"].pop())
    if not state["deck"]:
        state["out"] = [seat for seat in state["order"] if not state["hands"][seat]]
    _finish(state)


def _next_playing(state: dict[str, Any], seat: str) -> str | None:
    order = list(state["order"])
    if seat not in order:
        return None
    gone = set(state.get("out") or [])
    for step in range(1, len(order) + 1):
        cand = order[(order.index(seat) + step) % len(order)]
        if cand in gone:
            continue
        if state["hands"].get(cand) or state["deck"]:
            return cand
    return None


def _finish(state: dict[str, Any]) -> None:
    if state.get("result"):
        return
    if state["deck"]:
        return
    alive = [seat for seat in state["order"] if state["hands"].get(seat)]
    if len(alive) > 1:
        return
    state["phase"] = "done"
    state["table"] = []
    if len(alive) == 1:
        loser = alive[0]
        state["loser"] = loser
        others = [seat for seat in state["order"] if seat != loser]
        state["reason"] = "durak"
        state["result"] = f"{others[0]}_win" if len(others) == 1 else "draw"
        state["line"] = "Остался с картами и проиграл."
        return
    state["loser"] = ""
    state["reason"] = "clear"
    state["result"] = "draw"
    state["line"] = "Карты кончились у всех. Ничья."


def suggest(state: dict[str, Any], level: int = 3) -> list[str] | None:
    actions = legal(state)
    if not actions:
        return None
    seat = state["to_move"]
    trump = state["trump"]
    phase = state["phase"]
    if phase == "attack":
        plain = [item for item in actions if item["path"][1][1] != trump]
        pool = plain or actions
        pool.sort(key=lambda item: _rank(item["path"][1]))
        return list(pool[0]["path"])
    if phase == "defend":
        beats = [item for item in actions if item["path"][0] == "play" and _beats(item["path"][1], _unbeaten(state)[0]["attack"], trump)]
        transfers = [
            item
            for item in actions
            if item["path"][0] == "play" and item not in beats
        ]
        if transfers and level <= 2:
            return list(transfers[0]["path"])
        if beats:
            beats.sort(key=lambda item: (_rank(item["path"][1]) + (20 if item["path"][1][1] == trump else 0)))
            if level >= 4 or beats[0]["path"][1][1] != trump or not any(card[1] != trump for card in state["hands"][seat]):
                return list(beats[0]["path"])
        if transfers:
            return list(transfers[0]["path"])
        return ["act", "take"]
    adds = [item for item in actions if item["path"][0] == "play"]
    if state.get("taking"):
        plain = [item for item in adds if item["path"][1][1] != trump]
        pool = plain or (adds if level >= 4 else [])
        if pool:
            pool.sort(key=lambda item: _rank(item["path"][1]))
            return list(pool[0]["path"])
        return ["act", "pass"]
    if adds and (level >= 3 or len(state["table"]) < 3):
        adds.sort(key=lambda item: _rank(item["path"][1]) + (20 if item["path"][1][1] == trump else 0))
        if adds[0]["path"][1][1] != trump or level >= 5:
            return list(adds[0]["path"])
    return ["act", "pass"]


def leave(state: dict[str, Any], seat: str) -> dict[str, Any]:
    nxt = json.loads(dumps(state))
    if nxt.get("result"):
        return nxt
    others = [item for item in nxt["order"] if item != seat]
    nxt["phase"] = "done"
    nxt["hands"][seat] = []
    nxt["loser"] = seat
    nxt["reason"] = "left"
    nxt["result"] = f"{others[0]}_win" if len(others) == 1 else "draw"
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
    return {
        "done": bool(result),
        "winner": winner,
        "loser": str(state.get("loser") or ""),
        "line": str(state.get("line") or ""),
        "reason": str(state.get("reason") or ""),
        "board": [pair["attack"] for pair in state.get("table") or []],
        "pot": 0,
        "counts": {"play": len(payloads)},
        "hands": {seat: list(cards) for seat, cards in (state.get("hands") or {}).items()} if result else {},
        "notes": _notes(state),
        "last": {},
    }


def _notes(state: dict[str, Any]) -> dict[str, str]:
    loser = str(state.get("loser") or "")
    notes = {}
    for seat in state.get("order") or []:
        if seat == loser:
            notes[seat] = "дурак"
        elif seat in set(state.get("out") or []):
            notes[seat] = "вышел"
        else:
            notes[seat] = f"{len(state.get('hands', {}).get(seat, []))} карт"
    return notes


def view(state: dict[str, Any], seat: str | None) -> dict[str, Any]:
    phase = state.get("phase")
    hand = list(state.get("hands", {}).get(seat, [])) if seat and phase != "waiting" else []
    trump_card = str(state.get("trump_card") or "")
    shown = trump_card if trump_card and trump_card in (state.get("deck") or []) else ""
    title = VARIANTS.get(str(state.get("variant")), "Дурак")
    if phase == "waiting":
        message = "Ждём игроков. Вид игры уже выбран."
    elif phase == "done":
        message = str(state.get("line") or "Партия окончена.")
    elif phase == "attack":
        message = f"{title}. Козырь — {SUIT_NAME.get(state.get('trump', ''), '')}. Ходите картой."
    elif phase == "defend":
        message = f"{title}. Побейте карту, переведите или заберите."
    elif state.get("taking"):
        message = f"{title}. Карты берут. Подкиньте достоинство со стола или скажите «хватит»."
    else:
        message = f"{title}. Подкиньте достоинство со стола или скажите «бито»."
    roster = []
    for key in state.get("order") or []:
        roster.append(
            {
                "key": key,
                "count": len(state.get("hands", {}).get(key, [])),
                "folded": key in set(state.get("out") or []),
            }
        )
    live = [
        {"attack": pair["attack"], "defense": pair.get("defense") or ""}
        for pair in state.get("table") or []
    ]
    held = False
    if not live and phase in {"attack", "throw", "defend"}:
        live = [
            {"attack": pair["attack"], "defense": pair.get("defense") or ""}
            for pair in state.get("last_table") or []
            if isinstance(pair, dict) and pair.get("attack")
        ]
        held = bool(live)
    bout = state.get("last_bout") if held and isinstance(state.get("last_bout"), dict) else {}
    remembered = state.get("last_bout") if isinstance(state.get("last_bout"), dict) else {}
    previous = remembered if str(remembered.get("kind") or "") in {"bito", "take"} else {}
    pairs = live
    return {
        "hand": hand,
        "top": pairs[-1]["attack"] if pairs else "",
        "color": state.get("trump"),
        "phase": phase,
        "roster": roster,
        "opponent_count": sum(item["count"] for item in roster if item["key"] != seat),
        "deck": len(state.get("deck") or []),
        "actions": legal(state) if seat and state.get("to_move") == seat and not state.get("result") else [],
        "message": message,
        "pot": 0,
        "board": [pair["attack"] for pair in pairs],
        "pairs": pairs,
        "held": held,
        "bout": bout,
        "previous": {
            "kind": str(previous.get("kind") or ""),
            "seat": str(previous.get("seat") or ""),
            "pairs": [
                {"attack": str(pair.get("attack") or ""), "defense": str(pair.get("defense") or "")}
                for pair in (state.get("last_table") or [])
                if isinstance(pair, dict) and pair.get("attack")
            ],
        }
        if previous
        else {},
        "trump": state.get("trump") or "",
        "trump_card": shown,
        "hole": False,
        "talon": [],
        "contract": title,
        "shown": {},
    }
