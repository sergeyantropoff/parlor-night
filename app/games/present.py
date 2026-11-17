"""Представление партии для страницы и JSON API."""

from __future__ import annotations

import hashlib
import random
import uuid

import chess
from app.cards import poker, uno
from app.cards.registry import CARD_GAMES, card_module
from app.checkers.model import (
    BLACK_KING,
    BLACK_MAN,
    FILES,
    SQUARE_OF,
    WHITE_KING,
    WHITE_MAN,
    algebraic,
)
from app.checkers.rules import legal_moves
from app.checkers.serialization import parse_rcp
from app.chess.rules import cells as chess_cells
from app.chess.rules import check_square, legal_records
from app.db.repositories.users import User
from app.games.access import (
    black_at_bottom,
    can_hint,
    other_side,
    seat_of,
    undo_count,
    user_may_move,
    user_may_request_engine,
)
from app.games.messages import result_badge, result_message, result_tone, stopped_badge
from app.games.replay import replay_checkers, replay_chess
from app.go.engine import computer_pending
from app.go.match import load_state, points_for, same_bones, score_view
from app.go.match import replay as replay_go
from app.go.rules import KOMI_HALF, format_half


def _player_seat(
    game: dict[str, object],
    user_id: str,
    creator_id: str,
    opponent_id: str | None,
    creator_side: str,
) -> str | None:
    for item in game.get("table_seats") or []:
        if isinstance(item, dict) and item.get("user_id") and str(item["user_id"]) == user_id:
            return str(item["seat_key"])
    return seat_of(user_id, creator_id, opponent_id, creator_side)


def _sid(value: object) -> str:
    if isinstance(value, uuid.UUID):
        return str(value)
    return str(value)


def _call_roster(game: dict[str, object]) -> list[dict[str, str]]:
    roster: list[dict[str, str]] = []
    seen: set[str] = set()

    def add(uid: object, name: object, login: object = "", avatar: object = "") -> None:
        if not uid or not name:
            return
        key = _sid(uid)
        if key in seen:
            return
        seen.add(key)
        roster.append(
            {
                "id": key,
                "name": str(name),
                "login": str(login or ""),
                "avatar": str(avatar or ""),
            }
        )

    for item in game.get("table_seats") or []:
        if isinstance(item, dict) and item.get("kind") != "computer":
            add(item.get("user_id"), item.get("username"), item.get("login"), item.get("avatar"))
    add(game.get("user_id"), game.get("creator_name"), game.get("creator_login"), game.get("creator_avatar"))
    add(game.get("opponent_id"), game.get("opponent_name"), game.get("opponent_login"), game.get("opponent_avatar"))
    return roster


def _faces(game: dict[str, object], mode: str, creator_side: str) -> dict[str, str]:
    other = other_side(creator_side)
    creator_login = str(game.get("creator_login") or "")
    creator_avatar = str(game.get("creator_avatar") or "")
    if mode == "online":
        other_login = str(game.get("opponent_login") or "")
        other_avatar = str(game.get("opponent_avatar") or "")
    else:
        other_login = ""
        other_avatar = ""
    if mode not in {"online", "vs_computer"}:
        creator_login = creator_avatar = other_login = other_avatar = ""
    logins = {creator_side: creator_login, other: other_login}
    avatars = {creator_side: creator_avatar, other: other_avatar}
    return {
        "white_login": logins.get("white", ""),
        "black_login": logins.get("black", ""),
        "white_avatar": avatars.get("white", ""),
        "black_avatar": avatars.get("black", ""),
    }


def _viewer_face(game: dict[str, object], user: User, mode: str) -> dict[str, str]:
    creator = str(user.id) == _sid(game["user_id"])
    if mode == "online" and creator:
        login, avatar = game.get("opponent_login"), game.get("opponent_avatar")
    elif mode == "online":
        login, avatar = game.get("creator_login"), game.get("creator_avatar")
    else:
        login, avatar = "", ""
    return {
        "login": user.username,
        "avatar": user.avatar,
        "opponent_login": str(login or ""),
        "opponent_avatar": str(avatar or ""),
    }


def _face_of(item: dict[str, object], names: dict[str, str], key: str) -> dict[str, str]:
    return {
        "login": str(item.get("login") or names.get(f"{key}_login") or ""),
        "avatar": str(item.get("avatar") or names.get(f"{key}_avatar") or ""),
    }


_LEVELS = {1: "Новичок", 2: "Любитель", 3: "Опытный", 4: "Сильный", 5: "Мастер"}
_CPU_NAMES = (
    "Алексей",
    "Елена",
    "Дмитрий",
    "Анна",
    "Михаил",
    "Ольга",
    "Игорь",
    "Марина",
    "Павел",
    "София",
    "Никита",
    "Дарья",
    "Сергей",
    "Ксения",
    "Андрей",
    "Виктория",
)


def _blocked_names(reserved: object) -> set[str]:
    blocked: set[str] = set()
    for item in reserved if isinstance(reserved, (list, tuple, set)) else ():
        for part in str(item or "").replace("\x1f", " ").split():
            if part in _CPU_NAMES:
                blocked.add(part)
    return blocked


def _cpu_aliases(game_id: object, keys: list[str], reserved: object = ()) -> dict[str, str]:
    ordered = sorted({str(key) for key in keys if str(key)})
    seed = int(hashlib.sha256(str(game_id).encode()).hexdigest()[:8], 16)
    rng = random.Random(seed)
    pool = [name for name in _CPU_NAMES if name not in _blocked_names(reserved)]
    if len(pool) < len(ordered):
        pool = list(_CPU_NAMES)
    rng.shuffle(pool)
    return {key: pool[index] for index, key in enumerate(ordered)}


def cpu_name(game_id: object, key: str, reserved: object = ()) -> str:
    return _cpu_aliases(game_id, [key], reserved)[key]


def _table_reserved(game: dict[str, object]) -> list[str]:
    names = [str(game.get("creator_name") or ""), str(game.get("opponent_name") or "")]
    for item in game.get("table_seats") or []:
        if isinstance(item, dict) and item.get("kind") != "computer":
            names.append(str(item.get("username") or ""))
    return names


def computer_names(
    game_id: object,
    player_side: object,
    seat_keys: object,
    reserved: object = (),
) -> list[str]:
    keys = [item for item in str(seat_keys or "").split(",") if item]
    if not keys:
        side = str(player_side or "")
        keys = [other_side(side)] if side in {"white", "black"} else ["black"]
    aliases = _cpu_aliases(game_id, keys, reserved)
    return [aliases[key] for key in sorted(aliases)]


def _salon_faces(
    card: dict[str, object],
    *,
    mode: str,
    seat: str | None,
    side: str,
    status: str,
    user: object,
    named: dict[str, str],
    game_id: object,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    you_key = str(seat or "")
    for item in card.get("roster") or []:
        if not isinstance(item, dict) or not item.get("key"):
            continue
        key = str(item["key"])
        you = bool(you_key) and key == you_key
        if you:
            name, kind = str(getattr(user, "display_name", "") or "Вы"), "you"
            login, avatar = str(getattr(user, "username", "") or ""), str(getattr(user, "avatar", "") or "")
        elif mode == "vs_computer":
            name, kind, login, avatar = str(named.get(f"{key}_name") or cpu_name(game_id, key)), "computer", "", ""
        else:
            name, kind, login, avatar = str(named.get(f"{key}_name") or "Соперник"), "human", "", ""
        rows.append(
            {
                "key": key,
                "name": name,
                "login": login,
                "avatar": avatar,
                "kind": kind,
                "count": int(item.get("count") or 0),
                "folded": bool(item.get("folded")),
                "you": you,
                "turn": key == side and status == "active",
                "cpu": kind == "computer",
                "stack": _chip(card.get("stacks"), key),
                "busted": False,
                "bet": _chip(card.get("committed"), key) or 0,
                "dealer": False,
            }
        )
    return rows


def _chip(mapping: object, key: str) -> int | None:
    if not isinstance(mapping, dict) or key not in mapping:
        return None
    return int(mapping[key])


def _side_names(
    mode: str,
    creator_side: str,
    creator_name: str,
    opponent_name: str | None,
    engine_level: object,
    game_id: object,
) -> dict[str, str]:
    other = other_side(creator_side)
    if mode == "vs_computer":
        seated = {creator_side: creator_name, other: cpu_name(game_id, other, [creator_name])}
    elif mode == "online":
        seated = {creator_side: creator_name, other: opponent_name or ""}
    else:
        seated = {}
    try:
        level = int(engine_level)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        level = 0
    return {
        "white_name": seated.get("white") or "",
        "black_name": seated.get("black") or "",
        "engine_title": _LEVELS.get(level, ""),
    }


def _payloads(moves: list[dict[str, object]]) -> list[dict[str, object]]:
    payloads: list[dict[str, object]] = []
    for move in moves:
        payload = move["move_payload"]
        if isinstance(payload, dict):
            payloads.append(payload)
    return payloads


def _checkers_cells(position_board: tuple[int, ...]) -> list[dict[str, object]]:
    cells: list[dict[str, object]] = []
    for rank in range(8):
        for file in range(8):
            number = SQUARE_OF.get((rank, file))
            square = algebraic(number) if number else f"{FILES[file]}{rank + 1}"
            piece = None
            color = None
            if number:
                code = position_board[number]
                if code in (WHITE_MAN, WHITE_KING):
                    color = "white"
                    piece = "K" if code == WHITE_KING else "M"
                elif code in (BLACK_MAN, BLACK_KING):
                    color = "black"
                    piece = "K" if code == BLACK_KING else "M"
            if number is None:
                aria = f"светлое поле {square}, в русских шашках не используется"
                key = square
            elif piece is None:
                aria = f"поле {number}, {square}, пусто"
                key = str(number)
            else:
                color_name = "белая" if color == "white" else "чёрная"
                kind = "дамка" if piece == "K" else "шашка"
                aria = f"поле {number}, {square}, {color_name} {kind}"
                key = str(number)
            cells.append(
                {
                    "square": key,
                    "file": file,
                    "rank": rank,
                    "dark": (file + rank) % 2 == 0,
                    "number": number,
                    "piece": piece,
                    "color": color,
                    "aria": aria,
                }
            )
    return cells


def _status_line(
    *,
    mode: str,
    status: str,
    your_turn: bool,
    in_check: bool,
    finished: str | None,
    computer_name: str = "",
) -> str:
    if status == "waiting":
        return "Ожидаем второго игрока. Передайте код приглашения."
    if status == "finished":
        return finished or "Партия завершена."
    if in_check and your_turn:
        return "Шах. Ваш ход."
    if your_turn:
        return "Ваш ход."
    if mode == "online":
        return "Ход соперника."
    if mode == "vs_computer":
        return f"Ходит {computer_name}." if computer_name else "Ход компьютера."
    return "Ход другой стороны."


def _project_cards(
    game: dict[str, object],
    user: User,
    moves: list[dict[str, object]],
    seat: str | None,
    payloads: list[dict[str, object]],
    last_path: list[str],
) -> dict[str, object]:
    module = card_module(str(game["game_type"]))
    recorded = str(game["current_position"])
    if game["game_type"] == "uno":
        state = uno.aligned(str(game["initial_position"]), payloads, recorded)
    else:
        state = module.replay(str(game["initial_position"]), payloads)
        if game["game_type"] == "poker" and not poker.matches(state, recorded):
            raise ValueError("запись карточной партии не сходится")
    creator_id = _sid(game["user_id"])
    mode = str(game["mode"])
    status = str(game["status"])
    side = str(state.get("to_move") or "white")
    your_turn = user_may_move(mode, status, seat, side)
    card = module.view(state, seat)
    finished = result_message(
        str(game["game_type"]),
        _optional(game.get("result")),
        _optional(game.get("result_reason")),
    )
    opponent_name = _optional(game.get("opponent_name"))
    creator_name = str(game.get("creator_name") or "")
    if mode == "online":
        rival = opponent_name if str(user.id) == creator_id else creator_name
    elif mode == "vs_computer":
        rival = cpu_name(game["id"], other_side(str(game["player_side"])), _table_reserved(game))
    else:
        rival = None
    message = str(card["message"])
    stopped = stopped_badge(status, _optional(game.get("result")), _optional(game.get("result_reason")))
    if stopped:
        line = stopped
    elif status == "finished" and str(game["game_type"]) in {"poker", "preferans"}:
        line = message or finished
    elif status == "finished":
        line = finished or message
    elif your_turn:
        line = f"{message} Ваш ход."
    else:
        line = message
    table_seats = [item for item in game.get("table_seats") or [] if isinstance(item, dict)]
    computers = {str(item.get("seat_key")) for item in table_seats if item.get("kind") == "computer"}
    computer_turn = side in computers and side != seat
    cpu_keys = [str(item.get("seat_key")) for item in table_seats if item.get("kind") == "computer"]
    cpu_opponent = False
    card_game = str(game["game_type"]) in CARD_GAMES
    if card_game and mode == "vs_computer" and not cpu_keys:
        cpu_keys = [other_side(str(game["player_side"]))]
        cpu_opponent = True
    aliases = _cpu_aliases(game["id"], cpu_keys, _table_reserved(game)) if card_game and cpu_keys else {}
    counted = {str(item.get("key")): item for item in card.get("roster") or [] if isinstance(item, dict)}
    busted = {str(item) for item in card.get("busted") or []}
    public_seats = []
    for item in table_seats:
        key = str(item.get("seat_key"))
        info = counted.get(key) or {}
        if item.get("user_id") and str(item["user_id"]) == str(user.id):
            name, kind = user.display_name, "you"
        elif item.get("kind") == "computer":
            alias = aliases.get(key) or cpu_name(game["id"], key, _table_reserved(game))
            name, kind = alias, "computer"
        elif item.get("username"):
            name, kind = str(item["username"]), "human"
        else:
            name, kind = "Свободно", "open"
        if kind == "you":
            login, avatar = user.username, user.avatar
        elif kind == "human":
            login, avatar = str(item.get("login") or ""), str(item.get("avatar") or "")
        else:
            login, avatar = "", ""
        public_seats.append(
            {
                "key": key,
                "name": name,
                "login": login,
                "avatar": avatar,
                "kind": kind,
                "count": int(info.get("count") or 0),
                "folded": bool(info.get("folded")),
                "you": kind == "you",
                "turn": key == side and status == "active",
                "cpu": kind == "computer",
                "stack": 0 if key in busted else _chip(card.get("stacks"), key),
                "busted": key in busted,
                "bet": _chip(card.get("committed"), key) or 0,
                "dealer": str(card.get("button") or "") == key,
            }
        )
    report = _card_report(game, payloads, state)
    if str(game["game_type"]) == "uno":
        marks = {str(key): str(value) for key, value in (card.get("acts") or {}).items()}
    else:
        marks = (report.get("last") or {}) if report else {}
    for item in public_seats:
        item["mark"] = marks.get(str(item["key"]), "")
        item["winner"] = bool(report and report.get("winner") == item["key"])
    named = _side_names(
        mode, str(game["player_side"]), creator_name, opponent_name, game["engine_level"], game["id"]
    )
    named.update(_faces(game, mode, str(game["player_side"])))
    for key, alias in aliases.items():
        named[f"{key}_name"] = alias
    if mode == "vs_computer" and aliases:
        ordered = [aliases[key] for key in cpu_keys if key in aliases]
        if len(ordered) == 1:
            rival = ordered[0]
        elif ordered:
            rival = ", ".join(ordered)
    if not public_seats and str(game["game_type"]) in {"durak", "blackjack", "preferans"}:
        public_seats = _salon_faces(
            card,
            mode=mode,
            seat=seat,
            side=side,
            status=status,
            user=user,
            named=named,
            game_id=game["id"],
        )
        for item in public_seats:
            item["mark"] = marks.get(str(item["key"]), "")
            item["winner"] = bool(report and report.get("winner") == item["key"])
    summary = None
    if stopped:
        summary = _halted_card_summary(str(game["game_type"]), report, public_seats, named)
    elif report and report.get("done"):
        if str(game["game_type"]) == "uno":
            summary = _uno_summary(report, public_seats, named)
            line = str(summary["line"])
        elif str(game["game_type"]) == "poker":
            summary = _hand_summary(report, public_seats, named)
        else:
            summary = _parlor_summary(str(game["game_type"]), report, public_seats, named)
            line = str(summary["line"])
    return {
        "id": _sid(game["id"]),
        "you": str(user.id),
        "game_type": game["game_type"],
        "table": "cards",
        "variant": game["variant"],
        "mode": mode,
        "status": status,
        "version": int(game["position_version"]),  # type: ignore[arg-type]
        "your_side": seat if mode in {"vs_computer", "online"} else None,
        "side_to_move": side,
        "your_turn": your_turn,
        "watching": seat is None and mode in {"online", "vs_computer"},
        "black_at_bottom": False,
        "cells": [],
        "legal_moves": card["actions"] if your_turn else [],
        "hand": card["hand"],
        "board": card.get("board") or [],
        "winner_hand": card.get("winner_hand") or "",
        "pot": card["pot"],
        "phase": card["phase"],
        "stacks": card.get("stacks") or {},
        "committed": card.get("committed") or {},
        "button": card.get("button") or "",
        "cpu_opponent": cpu_opponent,
        "top": card.get("top") or "",
        "color": card.get("color"),
        "deck": int(card.get("deck") or 0),
        "shown": card.get("shown") or {},
        "pairs": card.get("pairs") or [],
        "trump": card.get("trump") or "",
        "trump_card": card.get("trump_card") or "",
        "hole": bool(card.get("hole")),
        "held": bool(card.get("held")),
        "talon": card.get("talon") or [],
        "contract": card.get("contract") or "",
        "sheet": card.get("sheet") or None,
        "scored": bool(card.get("scored")),
        "note": str(card.get("note") or ""),
        "note_tone": str(card.get("note_tone") or ""),
        "seats": public_seats
        if len(public_seats) > 2
        or (str(game["game_type"]) in {"uno", "durak", "blackjack", "preferans"} and len(public_seats) >= 1)
        else [],
        "marks": marks,
        "said": [str(item) for item in (card.get("said") or [])],
        "summary": summary,
        "computer_turn": computer_turn,
        "opponent_count": card["opponent_count"],
        "last_move": last_path,
        "in_check": False,
        "check_square": None,
        "moves": [
            {"ply": move["ply"], "notation": move["notation"], "algebraic": None, "by": None} for move in moves
        ],
        "result": game.get("result"),
        "result_reason": game.get("result_reason"),
        "result_message": finished,
        "result_tone": "stop" if stopped else None,
        "status_line": line,
        "can_hint": False,
        "can_engine": user_may_request_engine(mode, status, seat, side, computer_turn=computer_turn),
        "can_undo": False,
        "can_stop": str(user.id) == creator_id and status in {"waiting", "active"},
        "can_move": your_turn,
        "live": mode == "online" or (mode == "vs_computer" and seat is None),
        "in_call": mode == "online" and seat is not None,
        "call_roster": _call_roster(game),
        "audience": str(game.get("audience") or "closed"),
        "waiting": status == "waiting",
        "join_code": game.get("join_code") if mode == "online" and seat is not None else None,
        "opponent_name": rival,
        "engine_level": game["engine_level"],
        "engine_time_ms": game["engine_time_ms"],
        "creator_name": creator_name,
        "you_name": user.display_name,
        "seat_color": seat,
        "other_side": other_side(side),
        **_viewer_face(game, user, mode),
        **named,
    }


def _card_report(
    game: dict[str, object],
    payloads: list[dict[str, object]],
    state: dict[str, object] | None = None,
) -> dict[str, object] | None:
    kind = str(game.get("game_type"))
    try:
        if kind == "poker":
            return poker.chronicle(str(game["initial_position"]), payloads)
        if kind == "uno":
            final = state if isinstance(state, dict) else None
            return uno.chronicle(str(game["initial_position"]), payloads, final)
        if kind in CARD_GAMES:
            final = state if isinstance(state, dict) else None
            return card_module(kind).chronicle(str(game["initial_position"]), payloads, final)
    except (TypeError, ValueError, KeyError):
        return None
    return None


def _uno_summary(
    report: dict[str, object],
    seats: list[dict[str, object]],
    names: dict[str, str],
) -> dict[str, object]:
    source = seats or [
        {"key": "white", "name": names.get("white_name") or "Белые"},
        {"key": "black", "name": names.get("black_name") or "Чёрные"},
    ]
    winner = str(report.get("winner") or "")
    last = report["last"] if isinstance(report.get("last"), dict) else {}
    hands = report["hands"] if isinstance(report.get("hands"), dict) else {}
    said = {str(item) for item in report.get("said") or []}
    rows: list[dict[str, object]] = []
    winner_name = ""
    for item in source:
        key = str(item["key"])
        name = str(item["name"])
        if key == winner:
            winner_name = name
        cards = [str(card) for card in hands.get(key) or []]
        rows.append(
            {
                "key": key,
                "name": name,
                **_face_of(item, names, key),
                "winner": key == winner,
                "action": str(last.get(key) or ""),
                "cards": cards,
                "count": len(cards),
                "said": key in said,
            }
        )
    named_line = f"Победитель — {winner_name}." if winner_name else str(report.get("line") or "Партия окончена.")
    return {
        "kind": "uno",
        "winner": winner,
        "winner_name": winner_name,
        "line": named_line,
        "reason": report.get("reason") or "",
        "board": report.get("board") or [],
        "pot": report.get("pot") or 0,
        "counts": report.get("counts") or {},
        "seats": rows,
    }


def _hand_summary(
    report: dict[str, object],
    seats: list[dict[str, object]],
    names: dict[str, str],
) -> dict[str, object]:
    payout = report["payout"] if isinstance(report.get("payout"), dict) else {}
    last = report["last"] if isinstance(report.get("last"), dict) else {}
    source = seats or [
        {"key": "white", "name": names.get("white_name") or "Белые"},
        {"key": "black", "name": names.get("black_name") or "Чёрные"},
    ]
    rows: list[dict[str, object]] = []
    winner = report.get("winner")
    remaining = report.get("remaining") if isinstance(report.get("remaining"), dict) else {}
    invested = report.get("invested") if isinstance(report.get("invested"), dict) else {}
    hands = report.get("hands") if isinstance(report.get("hands"), dict) else {}
    named_hands = report.get("named") if isinstance(report.get("named"), dict) else {}
    for item in source:
        key = str(item.get("key") or "")
        left = int(remaining.get(key) or 0)
        rows.append(
            {
                "key": key,
                "name": str(item.get("name") or key),
                **_face_of(item, names, key),
                "action": str(last.get(key) or ""),
                "payout": int(payout.get(key) or 0),
                "invested": int(invested.get(key) or 0),
                "stack": left,
                "cards": list(hands.get(key) or []),
                "made": str(named_hands.get(key) or ""),
                "busted": left < poker.BB,
                "winner": key == winner,
            }
        )
    winner_name = next((str(row["name"]) for row in rows if row["winner"]), str(report.get("winner_label") or ""))
    folder_key = str(report.get("folded_by") or "")
    folder_name = next((str(row["name"]) for row in rows if row["key"] == folder_key), "")
    line = str(report.get("line") or "")
    if str(report.get("reason") or "") == "fold" and folder_name and winner_name:
        line = f"Последний пас — {folder_name}. Банк у {winner_name}."
    return {
        "winner": winner,
        "winner_label": report.get("winner_label") or "",
        "winner_name": winner_name,
        "combination": report.get("combination") or "",
        "line": line,
        "pot": report.get("pot") or 0,
        "counts": report.get("counts") or {},
        "board": list(report.get("board") or []) if isinstance(report.get("board"), list) else [],
        "reason": str(report.get("reason") or ""),
        "seats": rows,
    }


def _join_names(names: list[str]) -> str:
    if len(names) <= 1:
        return names[0] if names else ""
    if len(names) == 2:
        return f"{names[0]} и {names[1]}"
    return f"{', '.join(names[:-1])} и {names[-1]}"


def _parlor_summary(
    kind: str,
    report: dict[str, object],
    seats: list[dict[str, object]],
    names: dict[str, str],
) -> dict[str, object]:
    source = seats or [
        {"key": "white", "name": names.get("white_name") or "Белые"},
        {"key": "black", "name": names.get("black_name") or "Чёрные"},
    ]
    hands = report.get("hands") if isinstance(report.get("hands"), dict) else {}
    notes = report.get("notes") if isinstance(report.get("notes"), dict) else {}
    winner = str(report.get("winner") or "")
    loser = str(report.get("loser") or "")
    listed = report.get("winners") if isinstance(report.get("winners"), list) else None
    winner_keys = {str(item) for item in listed} if listed is not None else ({winner} if winner else set())
    rows: list[dict[str, object]] = []
    winner_name = ""
    loser_name = ""
    for item in source:
        key = str(item.get("key") or "")
        name = str(item.get("name") or key)
        if key in winner_keys and not winner_name:
            winner_name = name
        if key == loser:
            loser_name = name
        cards = [str(card) for card in hands.get(key) or []]
        rows.append(
            {
                "key": key,
                "name": name,
                "winner": key in winner_keys,
                "action": str(notes.get(key) or ""),
                "cards": cards,
                "count": len(cards),
                "said": False,
                "note": str(notes.get(key) or ""),
            }
        )
    won_names = [str(row["name"]) for row in rows if row["winner"]]
    if len(won_names) > 1:
        winner_name = _join_names(won_names)
    line = str(report.get("line") or "")
    headline = ""
    detail = ""
    if kind == "blackjack" and str(report.get("reason") or "") == "showdown":
        outcomes = report.get("outcomes") if isinstance(report.get("outcomes"), dict) else {}
        if len(won_names) == 1:
            headline = f"Победитель — {won_names[0]}."
        elif won_names:
            headline = f"Победители — {_join_names(won_names)}."
        elif any(str(code) == "push" for code in outcomes.values()) and all(
            str(code) in {"push", "out"} for code in outcomes.values()
        ):
            headline = "Ничья с дилером."
        else:
            headline = "Победитель — дилер."
        detail = str(report.get("detail") or "")
        line = headline
    elif kind == "durak" and loser_name:
        line = f"Дурак — {loser_name}."
    elif winner_name and kind != "durak":
        line = line or f"Победитель — {winner_name}."
    titles = {"durak": "Дурак", "blackjack": "Блэкджек", "preferans": "Преферанс"}
    return {
        "kind": "parlor",
        "game": kind,
        "title": titles.get(kind, "Партия"),
        "winner": next((str(row["key"]) for row in rows if row["winner"]), winner),
        "winners": [str(row["key"]) for row in rows if row["winner"]],
        "winner_name": winner_name,
        "headline": headline,
        "detail": detail,
        "line": line or "Партия окончена.",
        "reason": report.get("reason") or "",
        "board": report.get("board") or [],
        "pot": report.get("pot") or 0,
        "counts": report.get("counts") or {},
        "seats": rows,
        "sheet": report.get("sheet") or None,
    }


def _halted_card_summary(
    kind: str,
    report: dict[str, object] | None,
    seats: list[dict[str, object]],
    names: dict[str, str],
) -> dict[str, object]:
    source = seats or [
        {"key": "white", "name": names.get("white_name") or "Белые", "count": 0, "stack": None},
        {"key": "black", "name": names.get("black_name") or "Чёрные", "count": 0, "stack": None},
    ]
    rows: list[dict[str, object]] = []
    for item in source:
        rows.append(
            {
                "key": str(item.get("key") or ""),
                "name": str(item.get("name") or ""),
                **_face_of(item, names, str(item.get("key") or "")),
                "winner": False,
                "action": "",
                "cards": [],
                "count": int(item.get("count") or 0),
                "said": False,
                "payout": 0,
                "invested": 0,
                "stack": item.get("stack"),
                "made": "",
                "busted": False,
            }
        )
    counts = report.get("counts") if isinstance(report, dict) and isinstance(report.get("counts"), dict) else {}
    pot = int(report.get("pot") or 0) if isinstance(report, dict) else 0
    return {
        "kind": "parlor" if kind in {"durak", "blackjack", "preferans"} else ("uno" if kind == "uno" else "poker"),
        "winner": "",
        "winner_name": "",
        "winner_label": "",
        "combination": "",
        "line": "Партия остановлена.",
        "reason": "stopped",
        "board": [],
        "pot": pot,
        "counts": counts,
        "seats": rows,
    }


def _checkers_material(board: tuple[int, ...]) -> tuple[int, int, int, int]:
    white = black = white_kings = black_kings = 0
    for piece in board[1:]:
        if piece == WHITE_MAN:
            white += 1
        elif piece == WHITE_KING:
            white += 1
            white_kings += 1
        elif piece == BLACK_MAN:
            black += 1
        elif piece == BLACK_KING:
            black += 1
            black_kings += 1
    return white, black, white_kings, black_kings


def _board_summary(
    game_type: str,
    outcome: str | None,
    reason: str | None,
    moves: list[dict[str, object]],
    names: dict[str, str],
    *,
    chess_board: chess.Board | None,
    checkers_position: object,
    initial: str,
) -> dict[str, object]:
    halted = reason == "stopped"
    winner = "" if halted else {"white_win": "white", "black_win": "black"}.get(outcome or "", "")
    notations = [str(move.get("notation") or "") for move in moves]
    plies = len(moves)
    checks = sum(1 for text in notations if "+" in text or text.endswith("#"))
    white_kings = black_kings = 0
    if game_type == "chess" and chess_board is not None:
        start = chess.Board(initial)
        white = sum(1 for piece in chess_board.piece_map().values() if piece.color == chess.WHITE)
        black = sum(1 for piece in chess_board.piece_map().values() if piece.color == chess.BLACK)
        captures = max(0, len(start.piece_map()) - white - black)
        kings = 0
        move_count = (plies + 1) // 2
    else:
        white_kings = black_kings = 0
        position_board = getattr(checkers_position, "board", None)
        end = _checkers_material(position_board if isinstance(position_board, tuple) else tuple())
        start = _checkers_material(parse_rcp(initial).board)
        white, black, white_kings, black_kings = end
        captures = max(0, (start[0] + start[1]) - (white + black))
        kings = white_kings + black_kings
        move_count = plies
        checks = 0
    sides = (
        ("white", "Белые", white, white_kings if game_type == "checkers" else 0),
        ("black", "Чёрные", black, black_kings if game_type == "checkers" else 0),
    )
    rows: list[dict[str, object]] = []
    winner_name = ""
    for key, label, pieces, side_kings in sides:
        name = names.get(f"{key}_name") or label
        if key == winner:
            winner_name = name
        rows.append(
            {
                "key": key,
                "name": name,
                "login": names.get(f"{key}_login") or "",
                "avatar": names.get(f"{key}_avatar") or "",
                "side": label,
                "winner": key == winner,
                "pieces": pieces,
                "kings": side_kings,
            }
        )
    if halted:
        line = "Партия остановлена."
    else:
        line = result_message(game_type, outcome, reason) or "Партия завершена."
    return {
        "kind": "board",
        "game": game_type,
        "winner": winner,
        "winner_name": winner_name,
        "line": line,
        "reason": "stopped" if halted else (reason or ""),
        "counts": {
            "moves": move_count,
            "captures": captures,
            "checks": checks,
            "kings": kings,
            "white": white,
            "black": black,
        },
        "seats": rows,
    }


def _project_go(
    game: dict[str, object],
    user: User,
    moves: list[dict[str, object]],
    seat: str | None,
    payloads: list[dict[str, object]],
) -> dict[str, object]:
    creator_id = _sid(game["user_id"])
    creator_side = str(game["player_side"])
    mode = str(game["mode"])
    db_status = str(game["status"])
    initial = load_state(str(game["initial_position"]))
    current = load_state(str(game["current_position"]))
    same_bones(replay_go(initial, payloads), current)
    phase = str(current["phase"])
    shown = "scoring" if db_status == "active" and phase == "score" else db_status
    side = str(current["to_play"])
    your_turn = shown == "active" and seat == side and not current.get("result")
    near = seat if seat in {"black", "white"} else "black"
    outcome = _optional(game.get("result"))
    reason = _optional(game.get("result_reason"))
    margin = current.get("margin_half")
    if shown == "finished" and reason == "score" and isinstance(margin, int):
        winner = "Чёрные" if outcome == "black_win" else "Белые"
        finished = f"{winner} выиграли на {format_half(margin)}."
    elif shown == "finished":
        finished = result_message("go", outcome, reason)
    else:
        finished = None
    if shown == "waiting":
        status_line = "Ждём второго игрока"
    elif shown == "scoring":
        status_line = "Подсчёт результата"
    elif shown == "finished":
        status_line = finished or "Партия завершена"
    elif your_turn:
        status_line = "Ваш ход"
    elif mode == "vs_computer":
        status_line = f"Ходит {cpu_name(game['id'], other_side(creator_side), _table_reserved(game))}."
    else:
        status_line = "Ход соперника"
    last = current.get("last") if isinstance(current.get("last"), dict) else None
    notice = ""
    if isinstance(last, dict) and last.get("kind") == "pass" and shown in {"active", "scoring"}:
        if seat and last.get("color") == seat:
            notice = "Вы пропустили ход."
        elif mode == "vs_computer" and seat:
            notice = f"{cpu_name(game['id'], other_side(creator_side), _table_reserved(game))} пропустил ход."
        elif seat:
            notice = "Соперник пропустил ход."
        else:
            notice = "Пропуск хода."
    stopped = stopped_badge(db_status, outcome, reason)
    badge = stopped or (result_badge(outcome) if shown == "finished" else None)
    tone = "stop" if stopped else (result_tone(outcome, seat) if shown == "finished" else None)
    opponent_name = _optional(game.get("opponent_name"))
    creator_name = str(game.get("creator_name") or "")
    if mode == "online":
        rival = opponent_name if str(user.id) == creator_id else creator_name
    elif mode == "vs_computer":
        rival = cpu_name(game["id"], other_side(creator_side), _table_reserved(game))
    else:
        rival = None
    named = _side_names(mode, creator_side, creator_name, opponent_name, game["engine_level"], game["id"])
    named.update(_faces(game, mode, creator_side))
    scored = score_view(current) if phase == "score" or reason == "score" else None
    computer = other_side(seat) if mode == "vs_computer" and seat in {"black", "white"} else ""
    engine_due = bool(computer) and db_status == "active" and computer_pending(current, computer)
    agreed = bool(scored and seat and scored.get(f"{seat}_agreed"))
    playing = seat in {"black", "white"} and shown in {"active", "scoring"}
    return {
        "id": _sid(game["id"]),
        "you": str(user.id),
        "game_type": "go",
        "table": "go",
        "variant": game["variant"],
        "mode": mode,
        "status": shown,
        "phase": phase,
        "version": int(game["position_version"]),  # type: ignore[arg-type]
        "size": int(current["size"]),
        "board": str(current["board"]),
        "komi": format_half(KOMI_HALF),
        "rules": str(current["rules"]),
        "captures": current["captures"],
        "last": last,
        "notice": notice,
        "dead": current.get("dead") or [],
        "tally": scored,
        "legal": points_for(current, seat if your_turn else None),
        "near_color": near,
        "far_color": other_side(near),
        "computer_side": other_side(creator_side) if mode == "vs_computer" else "",
        "your_side": seat if mode in {"online", "vs_computer"} else None,
        "side_to_move": side,
        "your_turn": your_turn,
        "watching": seat is None and mode in {"online", "vs_computer"},
        "black_at_bottom": False,
        "cells": [],
        "legal_moves": [],
        "last_move": [],
        "in_check": False,
        "check_square": None,
        "moves": [
            {
                "ply": move["ply"],
                "notation": move["notation"],
                "algebraic": move["notation"],
                "by": (move.get("move_payload") or {}).get("by") or "human"
                if isinstance(move.get("move_payload"), dict)
                else "human",
            }
            for move in moves
        ],
        "result": game.get("result"),
        "result_reason": game.get("result_reason"),
        "result_message": finished,
        "result_tone": tone,
        "status_line": badge or status_line,
        "can_hint": False,
        "can_engine": engine_due,
        "can_undo": False,
        "can_stop": str(user.id) == creator_id and db_status in {"waiting", "active"},
        "can_move": your_turn,
        "can_pass": your_turn,
        "can_resign": playing,
        "can_mark": seat in {"black", "white"} and shown == "scoring",
        "can_agree": seat in {"black", "white"} and shown == "scoring" and not agreed,
        "can_resume": seat in {"black", "white"} and shown == "scoring",
        "live": mode == "online" or (mode == "vs_computer" and seat is None),
        "in_call": mode == "online" and seat is not None,
        "call_roster": _call_roster(game),
        "audience": str(game.get("audience") or "closed"),
        "waiting": db_status == "waiting",
        "join_code": game.get("join_code") if mode == "online" and seat is not None else None,
        "opponent_name": rival,
        "engine_level": game["engine_level"],
        "engine_time_ms": game["engine_time_ms"],
        "creator_name": creator_name,
        "you_name": user.display_name,
        "seat_color": seat,
        "other_side": other_side(side),
        "summary": None,
        **_viewer_face(game, user, mode),
        **named,
    }


def project(game: dict[str, object], user: User, moves: list[dict[str, object]]) -> dict[str, object]:
    creator_id = _sid(game["user_id"])
    opponent_raw = game.get("opponent_id")
    opponent_id = _sid(opponent_raw) if opponent_raw else None
    creator_side = str(game["player_side"])
    seat = _player_seat(game, str(user.id), creator_id, opponent_id, creator_side)
    flipped = bool(game["creator_flipped"]) if str(user.id) == creator_id else bool(game["opponent_flipped"])
    payloads = _payloads(moves)
    game_type = str(game["game_type"])
    mode = str(game["mode"])
    status = str(game["status"])
    last_path: list[str] = []
    if payloads:
        raw_path = payloads[-1].get("path") or []
        if isinstance(raw_path, list):
            last_path = [str(item) for item in raw_path]

    if game_type in CARD_GAMES:
        return _project_cards(game, user, moves, seat, payloads, last_path)

    if game_type == "go":
        return _project_go(game, user, moves, seat, payloads)

    legal: list[dict[str, object]] = []
    check: str | None = None
    side = "white"
    chess_board: chess.Board | None = None
    checkers_position = None
    if game_type == "chess":
        board = replay_chess(str(game["initial_position"]), payloads)
        chess_board = board
        if board.fen() != game["current_position"]:
            raise ValueError("запись шахматной партии не сходится")
        side = "white" if board.turn == chess.WHITE else "black"
        check = check_square(board)
        board_cells = chess_cells(board)
        if user_may_move(mode, status, seat, side):
            legal = [
                {
                    "path": list(item.path),
                    "promotion": item.promotion,
                    "notation": item.san,
                }
                for item in legal_records(board)
            ]
    else:
        position, _keys = replay_checkers(str(game["initial_position"]), payloads)
        checkers_position = position
        from app.checkers.serialization import dump_rcp

        if dump_rcp(position) != game["current_position"]:
            raise ValueError("запись шашечной партии не сходится")
        side = "white" if position.side == 0 else "black"
        board_cells = _checkers_cells(position.board)
        if user_may_move(mode, status, seat, side):
            for move in legal_moves(position):
                from app.checkers.notation import format_move

                legal.append(
                    {
                        "path": [str(square) for square in move.path],
                        "promotion": None,
                        "notation": format_move(move),
                    }
                )

    your_turn = user_may_move(mode, status, seat, side)
    your_side = seat if mode in {"vs_computer", "online"} else None
    outcome = _optional(game.get("result"))
    reason = _optional(game.get("result_reason"))
    finished = result_message(game_type, outcome, reason)
    stopped = stopped_badge(status, outcome, reason)
    badge = stopped or (result_badge(outcome) if status == "finished" else None)
    tone = "stop" if stopped else (result_tone(outcome, your_side) if status == "finished" else None)
    opponent_name = _optional(game.get("opponent_name"))
    creator_name = str(game.get("creator_name") or "")
    if mode == "online":
        rival = opponent_name if str(user.id) == creator_id else creator_name
    elif mode == "vs_computer":
        rival = cpu_name(game["id"], other_side(creator_side), _table_reserved(game))
    else:
        rival = None
    named = _side_names(mode, creator_side, creator_name, opponent_name, game["engine_level"], game["id"])
    named.update(_faces(game, mode, creator_side))
    summary = None
    if status == "finished":
        summary = _board_summary(
            game_type,
            outcome,
            "stopped" if stopped else reason,
            moves,
            named,
            chess_board=chess_board,
            checkers_position=checkers_position,
            initial=str(game["initial_position"]),
        )
    return {
        "id": _sid(game["id"]),
        "you": str(user.id),
        "game_type": game_type,
        "table": "board",
        "variant": game["variant"],
        "mode": mode,
        "status": status,
        "version": int(game["position_version"]),  # type: ignore[arg-type]
        "your_side": your_side,
        "side_to_move": side,
        "your_turn": your_turn,
        "watching": seat is None and mode in {"online", "vs_computer"},
        "black_at_bottom": black_at_bottom(seat if mode in {"vs_computer", "online"} else creator_side, flipped),
        "cells": board_cells,
        "legal_moves": legal,
        "last_move": last_path,
        "in_check": check is not None,
        "check_square": check,
        "moves": [
            {
                "ply": move["ply"],
                "notation": move["notation"],
                "algebraic": (move["move_payload"] or {}).get("algebraic")
                if isinstance(move["move_payload"], dict)
                else None,
                "by": (move["move_payload"] or {}).get("by") if isinstance(move["move_payload"], dict) else None,
            }
            for move in moves
        ],
        "result": game.get("result"),
        "result_reason": game.get("result_reason"),
        "result_message": finished,
        "result_tone": tone,
        "status_line": _status_line(
            mode=mode,
            status=status,
            your_turn=your_turn,
            in_check=check is not None,
            finished=badge or finished,
            computer_name=rival or "",
        ),
        "computer_side": other_side(creator_side) if mode == "vs_computer" else "",
        "can_hint": can_hint(user.role) and status == "active",
        "can_engine": user_may_request_engine(mode, status, seat, side),
        "can_undo": undo_count(mode, status, len(moves), side, seat) > 0,
        "can_stop": str(user.id) == creator_id and status in {"waiting", "active"},
        "can_move": your_turn,
        "live": mode == "online" or (mode == "vs_computer" and seat is None),
        "in_call": mode == "online" and seat is not None,
        "call_roster": _call_roster(game),
        "audience": str(game.get("audience") or "closed"),
        "waiting": status == "waiting",
        "join_code": game.get("join_code") if mode == "online" and seat is not None else None,
        "opponent_name": rival,
        "engine_level": game["engine_level"],
        "engine_time_ms": game["engine_time_ms"],
        "creator_name": creator_name,
        "you_name": user.display_name,
        "seat_color": seat,
        "other_side": other_side(side),
        "summary": summary,
        **_viewer_face(game, user, mode),
        **named,
    }


def rematch_view(game: dict[str, object], user: User, offer: dict[str, object] | None) -> dict[str, object]:
    seat = _player_seat(
        game,
        str(user.id),
        _sid(game["user_id"]),
        _sid(game["opponent_id"]) if game.get("opponent_id") else None,
        str(game["player_side"]),
    )
    mode = str(game["mode"])
    cards = str(game["game_type"]) in CARD_GAMES
    available = (
        str(game["game_type"]) in {"chess", "checkers", "go", *CARD_GAMES}
        and str(game["status"]) == "finished"
        and (cards or game.get("result") in {"white_win", "black_win"})
        and seat is not None
        and mode in {"online", "vs_computer"}
        and (cards or mode != "online" or game.get("opponent_id") is not None)
    )
    if not available:
        return {"available": False, "state": "idle", "game_id": None, "note": ""}
    if mode == "vs_computer" or offer is None:
        return {"available": True, "state": "idle", "game_id": None, "note": ""}
    new_game = _sid(offer["new_game_id"]) if offer.get("new_game_id") else None
    status = str(offer.get("status") or "")
    mine = _sid(offer.get("offered_by")) == str(user.id)
    if status == "accepted" and new_game:
        return {"available": True, "state": "accepted", "game_id": new_game, "note": ""}
    if status == "pending" and mine:
        return {
            "available": True,
            "state": "outgoing",
            "game_id": None,
            "note": "Предложение отправлено сопернику.",
        }
    if status == "pending":
        return {"available": True, "state": "incoming", "game_id": None, "note": "Соперник предлагает реванш."}
    if status == "declined" and mine:
        return {"available": True, "state": "declined", "game_id": None, "note": "Соперник отклонил реванш."}
    return {"available": True, "state": "idle", "game_id": None, "note": ""}


def _optional(value: object) -> str | None:
    if value is None:
        return None
    return str(value)
