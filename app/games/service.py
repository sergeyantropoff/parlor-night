"""Игровые сценарии: сохранение, онлайн-стол и компьютер."""

from __future__ import annotations

import hashlib
import json
import logging
import re
import secrets
import uuid
from dataclasses import asdict
from typing import Any

import asyncpg

import chess
from app.cards import poker, preferans, uno
from app.cards.registry import ADULT_GAMES, CARD_GAMES, CHIP_GAMES, card_module
from app.checkers.engine import LEVELS
from app.checkers.simple import ENGINE_NAME, ready as simple_ready
from app.checkers.evaluation import DEFAULT_WEIGHTS, EvalWeights
from app.checkers.notation import dump_game_record, format_algebraic, format_move, format_move_algebraic, parse_notation
from app.checkers.rules import apply_move, move_from_path
from app.checkers.rules import outcome as checkers_outcome
from app.checkers.serialization import INITIAL_RCP, dump_rcp, parse_rcp
from app.chess.engine import choose_line, level_budget
from app.chess.rules import (
    STARTING_FEN,
    export_pgn,
    import_pgn,
    legal_records,
    outcome_of,
    parse_board,
    push_user_move,
)
from app.config import Settings
from app.paging import page_links
from app.db.repositories import analysis as analysis_repo
from app.db.repositories import games as games_repo
from app.db.repositories import rate_limit
from app.db.repositories import settings as settings_repo
from app.db.repositories.settings import as_preferences
from app.db.repositories.users import User
from app.errors import AnalysisIncomplete, AppError, EngineError, IllegalMove
from app.games.access import (
    durak_can_step_aside,
    other_side,
    seat_of,
    undo_count,
    user_may_move,
    user_may_request_engine,
)
from app.games.outcome import for_viewer
from app.games.present import cpu_name, project, rematch_view
from app.games.replay import replay_checkers, replay_chess
from app.go.engine import LEVELS as GO_LEVELS
from app.go.engine import computer_pending
from app.go.match import apply_action, dump_state, load_state, new_match
from app.go.rules import GoRuleError
from app.go.sgf import export_sgf
from app.site_policy import load_policy
from app.turn import ice_servers
from app.wallet import adult_denial, already_paid, balance, charge, credit, poker_denial, seat_user
from app.workers.engines import EngineRuntime
from app.workers.remote import RemoteEngineRuntime

logger = logging.getLogger(__name__)


def _sid(value: object) -> str:
    return str(value)


def _open_seat(game: dict[str, Any], user: User) -> bool:
    if str(game.get("audience") or "closed") != "open":
        return False
    if str(game.get("status") or "") != "waiting":
        return False
    if str(game.get("mode") or "") not in {"online", "vs_computer"}:
        return False
    if game.get("user_id") == user.id or game.get("opponent_id") == user.id:
        return False
    seats = list(game.get("table_seats") or [])
    if any(item.get("user_id") == user.id for item in seats):
        return False
    if seats:
        return any(str(item.get("kind")) == "human" and item.get("user_id") is None for item in seats)
    return str(game.get("mode")) == "online" and game.get("opponent_id") is None


def _card_state(module: Any, game: dict[str, Any], payloads: list[dict[str, Any]]) -> dict[str, Any]:
    if game.get("game_type") == "uno":
        return module.aligned(str(game["initial_position"]), payloads, str(game["current_position"]))
    return module.replay(str(game["initial_position"]), payloads)


def _payload_list(rows: list[Any]) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for row in rows:
        payload = row["move_payload"]
        if isinstance(payload, str):
            payload = json.loads(payload)
        payloads.append(payload)
    return payloads


def _move_dicts(rows: list[Any]) -> list[dict[str, Any]]:
    result = []
    for row in rows:
        payload = row["move_payload"]
        if isinstance(payload, str):
            payload = json.loads(payload)
        result.append({"ply": row["ply"], "notation": row["notation"], "move_payload": payload})
    return result


def _hash(value: object) -> str:
    raw = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


def _checkers_hint_notation(line: dict[str, Any]) -> str:
    raw = str(line.get("notation") or "")
    try:
        squares = tuple(int(item) for item in line.get("path") or [])
    except (TypeError, ValueError):
        return raw
    if len(squares) < 2:
        return raw
    return format_algebraic(squares, ":" in raw)


def _weights(preferences: dict[str, Any]) -> EvalWeights:
    raw = preferences.get("weights")
    if not isinstance(raw, dict):
        return DEFAULT_WEIGHTS
    fields = {}
    for name in EvalWeights.__dataclass_fields__:
        if name in raw:
            fields[name] = int(raw[name])
    return EvalWeights(**fields)


RECENT_PAGE_SIZE = 10


def _pool_number(variant: str) -> int:
    text = str(variant or "")
    if text.startswith("pool-") and text.split("-", 1)[1].isdigit():
        return int(text.split("-", 1)[1])
    return 12


def _preferans_pool(data: dict[str, Any]) -> int:
    allowed = {6, 10, 12, 16, 20}
    try:
        size = int(data.get("pool") or 12)
    except (TypeError, ValueError):
        size = 12
    return size if size in allowed else 12


def _position_stake(row: Any) -> int:
    raw = row["current_position"]
    try:
        position = json.loads(raw) if isinstance(raw, str) else dict(raw or {})
    except (json.JSONDecodeError, TypeError):
        position = {}
    if not isinstance(position, dict):
        position = {}
    return preferans.stake_of(position.get("stake"))


_AVATAR = re.compile(r"^[0-9a-f]{32}\.(jpg|png|webp)$")


def _watch_people(rows: list[asyncpg.Record], user_id: uuid.UUID) -> list[dict[str, object]]:
    people: list[dict[str, object]] = []
    for row in rows:
        avatar = str(row["avatar"] or "")
        people.append(
            {
                "name": str(row["name"]),
                "username": str(row["username"]),
                "avatar": avatar if _AVATAR.fullmatch(avatar) else "",
                "self": row["user_id"] == user_id,
            }
        )
    return people


class GameService:
    def __init__(self, pool: asyncpg.Pool, engines: EngineRuntime | RemoteEngineRuntime, settings: Settings) -> None:
        self.pool = pool
        self.engines = engines
        self.settings = settings
        self.gate = None

    def _forget_purse(self, user_id: object) -> None:
        gate = self.gate
        if gate is None or user_id is None:
            return
        gate.chips.pop(str(user_id), None)

    async def create(self, user: User, data: dict[str, Any]) -> dict[str, Any]:
        self._validate_create(data)
        if data["game_type"] in ADULT_GAMES:
            await self._require_adult(user.id, str(data["game_type"]))
        buy_in = None
        if data["game_type"] in {"poker", "blackjack"} and data["mode"] == "vs_computer":
            async with self.pool.acquire() as conn:
                buy_in = await self._poker_buy_in(conn, [user.id])
        elif data["game_type"] == "preferans" and data["mode"] in {"vs_computer", "online"}:
            price = preferans.stake_of(data.get("stake"))
            async with self.pool.acquire() as conn:
                await self._preferans_buy_in(conn, [user.id], price)
            if data["mode"] == "vs_computer":
                buy_in = preferans.stack_for(price)
        prepared = self._prepare(data, buy_in=buy_in)
        status = prepared["status"]
        if data["mode"] == "online" and status == "active":
            status = "waiting"
        join_code = games_repo.new_join_code() if status == "waiting" else None
        variants = {
            "checkers": "russian",
            "poker": "holdem",
            "uno": "classic",
            "blackjack": "classic",
            "preferans": "classic",
        }
        if data["game_type"] == "durak":
            variant = self._salon_variant(data)
        elif data["game_type"] == "preferans":
            variant = f"pool-{_preferans_pool(data)}"
        elif data["game_type"] == "go":
            variant = str(int(data["board_size"]))
        else:
            variant = variants.get(data["game_type"], "standard")
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                policy = await load_policy(conn)
                if not policy.allows(str(data["game_type"])):
                    raise AppError(403, "game_closed", "Эта игра сейчас закрыта.")
                game_id = await games_repo.insert_game(
                    conn,
                    user_id=user.id,
                    game_type=data["game_type"],
                    variant=variant,
                    mode=data["mode"],
                    player_side=data["player_side"],
                    status=status,
                    initial_position=prepared["initial"],
                    current_position=prepared["current"],
                    result=prepared["result"],
                    result_reason=prepared["reason"],
                    engine_level=int(data["engine_level"]),
                    engine_time_ms=int(data["engine_time_ms"]),
                    join_code=join_code,
                    audience=str(data["audience"]),
                )
                for index, item in enumerate(prepared["moves"], start=1):
                    await games_repo.insert_move(
                        conn,
                        game_id=game_id,
                        ply=index,
                        notation=str(item["notation"]),
                        payload=item["payload"],
                        position_before=str(item["before"]),
                        position_after=str(item["after"]),
                    )
                seat_rows = list(prepared.get("seat_rows") or [])
                if seat_rows:
                    key, kind, _owner = seat_rows[0]
                    seat_rows[0] = (key, kind, user.id)
                    await games_repo.insert_seats(conn, game_id, seat_rows)
                seated = {
                    "id": game_id,
                    "user_id": user.id,
                    "opponent_id": None,
                    "player_side": data["player_side"],
                }
                known = [
                    {"seat_key": key, "kind": kind, "user_id": owner}
                    for key, kind, owner in seat_rows
                ]
                for seat, amount in prepared.get("charges") or []:
                    payer = seat_user(seated, str(seat), known or None)
                    if payer is not None:
                        await charge(conn, payer, int(amount), reason="ante", game_id=game_id)
                        self._forget_purse(payer)
        return await self.view(user, game_id)

    async def join(self, user: User, code: str) -> uuid.UUID:
        normalized = code.strip().lower()
        if len(normalized) != 8:
            raise AppError(422, "bad_code", "Код приглашения состоит из 8 символов.")
        async with self.pool.acquire() as conn:
            allowed = await rate_limit.consume_rate(
                conn,
                bucket=f"join:{user.id}",
                limit=10,
                window_seconds=60,
            )
        if not allowed:
            raise AppError(429, "rate_limited", "Слишком много попыток присоединиться. Подождите минуту.")
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                existing = await games_repo.find_by_code(conn, normalized)
                if existing is None:
                    raise AppError(404, "not_found", "Приглашение не найдено.")
                if existing["game_type"] in ADULT_GAMES:
                    await self._require_adult(user.id, str(existing["game_type"]))
                if existing["user_id"] == user.id or existing["opponent_id"] == user.id:
                    return existing["id"]
                already = await conn.fetchval(
                    "SELECT 1 FROM game_seats WHERE game_id = $1 AND user_id = $2",
                    existing["id"],
                    user.id,
                )
                if already:
                    return existing["id"]
                claimed = await games_repo.claim_seat(conn, existing["id"], user.id)
                if claimed == "self":
                    return existing["id"]
                if claimed is None:
                    raise AppError(409, "game_full", "Свободных мест за этим столом нет.")
                await self._activate_if_full(conn, existing, claimed)
                return existing["id"]

    async def sit_open(self, user: User, game_id: uuid.UUID) -> uuid.UUID:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow("SELECT * FROM games WHERE id = $1", game_id)
                if row is None or row["status"] != "waiting" or row["mode"] not in {"online", "vs_computer"}:
                    raise AppError(404, "not_found", "Этот стол уже не ждёт игроков.")
                if row["audience"] != "open":
                    raise AppError(403, "table_closed", "За закрытый стол садятся по коду приглашения.")
                if row["game_type"] in ADULT_GAMES:
                    reason = await adult_denial(conn, user.id, str(row["game_type"]))
                    if reason:
                        raise AppError(403, "adult_only", reason)
                claimed = await games_repo.claim_seat(conn, game_id, user.id)
                if claimed is None:
                    raise AppError(409, "game_full", "Свободных мест за этим столом нет.")
                if claimed != "self":
                    await self._activate_if_full(conn, row, claimed)
        return game_id

    async def watch(self, user: User, code: str) -> uuid.UUID:
        normalized = code.strip().lower()
        if len(normalized) != 8:
            raise AppError(422, "bad_code", "Код приглашения состоит из 8 символов.")
        async with self.pool.acquire() as conn:
            existing = await games_repo.find_by_code(conn, normalized)
            if existing is None:
                raise AppError(404, "not_found", "Приглашение не найдено.")
            if existing["game_type"] in ADULT_GAMES:
                await self._require_adult(user.id, str(existing["game_type"]))
            if existing["user_id"] == user.id or existing["opponent_id"] == user.id:
                return existing["id"]
            if existing["audience"] != "open":
                raise AppError(403, "table_closed", "Этот стол закрыт. Смотреть можно только открытую партию.")
            await games_repo.add_watcher(conn, existing["id"], user.id)
            return existing["id"]

    async def watch_table(self, user: User, game_id: uuid.UUID) -> uuid.UUID:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, user_id, opponent_id, game_type, mode, audience, status
                FROM games
                WHERE id = $1
                """,
                game_id,
            )
            playable = row is not None and row["mode"] in {"online", "vs_computer"}
            if not playable or row["status"] not in {"waiting", "active"}:
                raise AppError(404, "not_found", "Этот стол уже не идёт.")
            if row["game_type"] in ADULT_GAMES:
                reason = await adult_denial(conn, user.id, str(row["game_type"]))
                if reason:
                    raise AppError(403, "adult_only", reason)
            if row["user_id"] == user.id or row["opponent_id"] == user.id:
                return row["id"]
            if row["audience"] != "open":
                raise AppError(403, "table_closed", "Этот стол закрыт. Смотреть можно только открытую партию.")
            await games_repo.add_watcher(conn, row["id"], user.id)
            return row["id"]

    async def arrive_watch(self, user: User, game_id: uuid.UUID) -> None:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT user_id, opponent_id, mode, audience, status
                FROM games
                WHERE id = $1
                """,
                game_id,
            )
            if row is None or row["mode"] not in {"online", "vs_computer"} or row["audience"] != "open":
                return
            if row["status"] not in {"waiting", "active", "scoring", "finished"}:
                return
            if row["user_id"] == user.id or row["opponent_id"] == user.id:
                return
            seated = await conn.fetchval(
                "SELECT 1 FROM game_seats WHERE game_id = $1 AND user_id = $2",
                game_id,
                user.id,
            )
            if seated:
                await games_repo.drop_watcher(conn, game_id, user.id)
                return
            await games_repo.add_watcher(conn, game_id, user.id)

    async def touch_watch(self, user: User, game_id: uuid.UUID) -> None:
        await self.arrive_watch(user, game_id)

    async def _remember_spectator(self, conn: asyncpg.Connection, row: asyncpg.Record, user: User) -> None:
        if str(row["mode"]) not in {"online", "vs_computer"} or str(row["audience"] or "closed") != "open":
            return
        if str(row["status"]) not in {"waiting", "active", "scoring", "finished"}:
            return
        if row["user_id"] == user.id or row["opponent_id"] == user.id:
            return
        seated = await conn.fetchval(
            "SELECT 1 FROM game_seats WHERE game_id = $1 AND user_id = $2",
            row["id"],
            user.id,
        )
        if seated:
            return
        await games_repo.add_watcher(conn, row["id"], user.id)

    async def leave_watch(self, user: User, game_id: uuid.UUID) -> None:
        async with self.pool.acquire() as conn:
            await games_repo.drop_watcher(conn, game_id, user.id)

    async def watcher_list(self, user: User, game_id: uuid.UUID) -> list[dict[str, object]]:
        async with self.pool.acquire() as conn:
            row = await games_repo.get_visible(conn, game_id, user.id)
            if row is None:
                raise AppError(404, "not_found", "Партия не найдена.")
            if str(row["mode"]) not in {"online", "vs_computer"} or str(row["audience"] or "closed") != "open":
                return []
            await self._remember_spectator(conn, row, user)
            watched = await games_repo.list_watchers(conn, game_id)
        return _watch_people(watched, user.id)

    async def view(self, user: User, game_id: uuid.UUID) -> dict[str, Any]:
        async with self.pool.acquire() as conn:
            row = await games_repo.get_visible(conn, game_id, user.id)
            if row is None:
                raise AppError(404, "not_found", "Партия не найдена.")
            moves = await games_repo.list_moves(conn, game_id)
            seats = await games_repo.list_seats(conn, game_id)
            if row["game_type"] in ADULT_GAMES:
                reason = await adult_denial(conn, user.id, str(row["game_type"]))
                if reason:
                    raise AppError(403, "adult_only", reason)
            offer = await games_repo.get_rematch(conn, game_id)
            watched = []
            if str(row["mode"]) in {"online", "vs_computer"} and str(row["audience"] or "closed") == "open":
                await self._remember_spectator(conn, row, user)
                watched = await games_repo.list_watchers(conn, game_id)
        game = dict(row)
        game["table_seats"] = [dict(item) for item in seats]
        try:
            state = project(game, user, _move_dicts(moves))
        except (ValueError, IllegalMove) as exc:
            logger.warning("corrupt game=%s", game_id)
            raise AppError(500, "corrupt_game", "Партия не сходится с записью ходов.") from exc
        state["rematch"] = rematch_view(game, user, dict(offer) if offer else None)
        if str(game["game_type"]) == "poker" and state["rematch"].get("available"):
            state["rematch"] = self._rematch_if_solvent(game, state["rematch"], str(state.get("seat_color") or ""))
        state["can_sit"] = _open_seat(game, user)
        state["watchers"] = _watch_people(watched, user.id)
        state["ice_servers"] = ice_servers(self.settings, str(user.id))
        return state

    async def history(self, user: User, game_id: uuid.UUID) -> dict[str, Any]:
        state = await self.view(user, game_id)
        return {"version": state["version"], "moves": state["moves"]}

    async def legal(self, user: User, game_id: uuid.UUID) -> dict[str, Any]:
        state = await self.view(user, game_id)
        return {"version": state["version"], "moves": state["legal_moves"]}

    async def move(
        self,
        user: User,
        game_id: uuid.UUID,
        path: list[str],
        promotion: str | None,
        version: int,
    ) -> tuple[dict[str, Any], str | None]:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                row = await self._lock(conn, game_id, user.id, version)
                if row["game_type"] == "go":
                    raise AppError(422, "bad_move", "В го ход ставится на пересечение.")
                moves = await games_repo.list_moves(conn, game_id)
                game = await self._seated_game(conn, row)
                applied = self._push(game, _payload_list(moves), path, promotion, "human")
                seat = self._seat(game, user)
                if not user_may_move(row["mode"], row["status"], seat, applied["side_before"]):
                    raise AppError(409, "wrong_turn", "Сейчас ход другой стороны.")
                await games_repo.insert_move(
                    conn,
                    game_id=game_id,
                    ply=len(moves) + 1,
                    notation=applied["notation"],
                    payload=applied["payload"],
                    position_before=applied["before"],
                    position_after=applied["after"],
                )
                await self._settle(conn, row, applied)
                await self._save_position(conn, row, user.id, version, applied)
        return await self.view(user, game_id), None

    async def undo(self, user: User, game_id: uuid.UUID, version: int) -> dict[str, Any]:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                row = await self._lock(conn, game_id, user.id, version)
                if row["game_type"] in CARD_GAMES or row["game_type"] == "go":
                    raise AppError(409, "undo_rejected", "В этой игре ход не отменяется.")
                moves = await games_repo.list_moves(conn, game_id)
                rebuilt = self._rebuild(dict(row), _payload_list(moves))
                count = undo_count(
                    row["mode"],
                    row["status"],
                    len(moves),
                    rebuilt["side"],
                    self._seat(dict(row), user),
                )
                if count == 0:
                    raise AppError(409, "undo_rejected", "Этот ход нельзя отменить.")
                restored = await games_repo.delete_last_moves(conn, game_id, count)
                if restored is None:
                    raise AppError(409, "undo_rejected", "Этот ход нельзя отменить.")
                remaining = await games_repo.list_moves(conn, game_id)
                applied = self._rebuild(dict(row), _payload_list(remaining))
                if applied["position"] != restored:
                    raise AppError(500, "corrupt_game", "Партия не сходится с записью ходов.")
                await self._save_position(
                    conn,
                    row,
                    user.id,
                    version,
                    {
                        "after": applied["position"],
                        "result": applied["result"],
                        "reason": applied["reason"],
                        "status": "finished" if applied["result"] else "active",
                    },
                )
        return await self.view(user, game_id)

    async def resign(self, user: User, game_id: uuid.UUID, version: int) -> dict[str, Any]:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                row = await self._lock(conn, game_id, user.id, version)
                if row["status"] not in {"active", "waiting"}:
                    raise AppError(409, "finished", "Партия уже завершена.")
                if row["game_type"] == "go" and row["status"] != "active":
                    raise AppError(409, "not_started", "Сдаться можно в начатой партии.")
                game = await self._seated_game(conn, row)
                seat = self._seat(game, user)
                if seat is None:
                    raise AppError(403, "not_player", "Наблюдатель не заканчивает партию.")
                moves = await games_repo.list_moves(conn, game_id)
                applied = self._concede(dict(row), _payload_list(moves), seat)
                if applied["payload"] is not None:
                    await games_repo.insert_move(
                        conn,
                        game_id=game_id,
                        ply=len(moves) + 1,
                        notation=applied["notation"],
                        payload=applied["payload"],
                        position_before=applied["before"],
                        position_after=applied["after"],
                    )
                await self._settle(conn, row, applied)
                await self._save_position(conn, row, user.id, version, applied)
        return await self.view(user, game_id)

    async def step_aside(self, user: User, game_id: uuid.UUID, version: int, pace: str) -> dict[str, Any]:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                row = await self._lock(conn, game_id, user.id, version)
                if row["status"] != "active" or row["game_type"] != "durak":
                    raise AppError(409, "stay", "Так выходят только из начатой партии в дурака.")
                game = await self._seated_game(conn, row)
                seats = [dict(item) for item in game["table_seats"]]
                if not durak_can_step_aside(seats, str(user.id)):
                    raise AppError(
                        409,
                        "stay",
                        "Смотреть доигрывание можно, когда за столом несколько компьютеров и нет других людей.",
                    )
                seat = self._seat(game, user)
                if seat is None:
                    raise AppError(403, "not_player", "Наблюдатель не выходит из-за стола.")
                await games_repo.set_seat_kind(conn, game_id, seat, "computer")
        if pace == "fast":
            return await self.engine_move(user, game_id, version, steps=240)
        return await self.view(user, game_id)

    async def go_command(
        self,
        user: User,
        game_id: uuid.UUID,
        command_id: str,
        version: int,
        action: str,
        col: int | None,
        row: int | None,
    ) -> dict[str, Any]:
        if action in {"move", "mark"} and (col is None or row is None):
            raise AppError(422, "bad_point", "Укажите пересечение.")
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                locked = await games_repo.lock_visible(conn, game_id, user.id)
                if locked is None:
                    visible = await games_repo.get_visible(conn, game_id, user.id)
                    if visible is not None:
                        raise AppError(403, "not_player", "Наблюдатель не управляет партией.")
                    raise AppError(404, "not_found", "Партия не найдена.")
                if locked["game_type"] != "go":
                    raise AppError(422, "bad_game", "Это не партия го.")
                state = load_state(str(locked["current_position"]))
                known = {str(item) for item in state.get("acks") or []}
                if command_id not in known:
                    if int(locked["position_version"]) != version:
                        raise AppError(409, "stale_position", "Позиция уже изменилась. Обновите партию.")
                    if locked["status"] == "finished" or state.get("result"):
                        raise AppError(409, "finished", "Партия уже завершена.")
                    if locked["status"] != "active":
                        raise AppError(409, "not_started", "Партия ещё не началась.")
                    game = await self._seated_game(conn, locked)
                    try:
                        new_state, done = apply_action(
                            state,
                            action,
                            self._seat(game, user),
                            col=col,
                            row=row,
                        )
                    except GoRuleError as exc:
                        raise AppError(422, "illegal_move", exc.message) from exc
                    new_state["acks"] = [*list(new_state.get("acks") or []), command_id][-128:]
                    if done["payload"] is not None:
                        payload = dict(done["payload"])
                        payload["command_id"] = command_id
                        moves = await games_repo.list_moves(conn, game_id)
                        await games_repo.insert_move(
                            conn,
                            game_id=game_id,
                            ply=len(moves) + 1,
                            notation=str(done["notation"]),
                            payload=payload,
                            position_before=dump_state(state),
                            position_after=dump_state(new_state),
                        )
                    applied = {
                        "after": dump_state(new_state),
                        "result": done["result"],
                        "reason": done["reason"],
                        "status": "finished" if done["result"] else "active",
                    }
                    if done["result"]:
                        await self._settle(conn, locked, applied)
                    await self._save_position(conn, locked, user.id, version, applied)
        return await self.view(user, game_id)

    async def stop(self, user: User, game_id: uuid.UUID, version: int) -> dict[str, Any]:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                row = await self._lock(conn, game_id, user.id, version)
                if row["status"] not in {"active", "waiting"}:
                    raise AppError(409, "finished", "Партия уже завершена.")
                if row["user_id"] != user.id:
                    raise AppError(403, "stop_forbidden", "Остановить партию может только тот, кто её начал.")
                await self._refund_table(conn, row["id"])
                await conn.execute("UPDATE games SET join_code = NULL WHERE id = $1", row["id"])
                await self._save_position(
                    conn,
                    row,
                    user.id,
                    version,
                    {
                        "after": row["current_position"],
                        "result": None,
                        "reason": "stopped",
                        "status": "finished",
                    },
                )
        return await self.view(user, game_id)

    async def _refund_table(self, conn: asyncpg.Connection, game_id: uuid.UUID) -> None:
        rows = await conn.fetch(
            """
            SELECT user_id, COALESCE(SUM(-amount), 0) AS owed
            FROM ledger
            WHERE game_id = $1 AND amount < 0
            GROUP BY user_id
            """,
            game_id,
        )
        for row in rows:
            owed = int(row["owed"])
            if owed > 0:
                await credit(conn, row["user_id"], owed, reason="refund", game_id=game_id)
                self._forget_purse(row["user_id"])

    async def rematch(self, user: User, game_id: uuid.UUID) -> dict[str, Any]:
        async with self.pool.acquire() as conn:
            row = await games_repo.get_visible(conn, game_id, user.id)
        if row is None:
            raise AppError(404, "not_found", "Партия не найдена.")
        seat = self._require_rematch(row, user)
        if row["mode"] == "vs_computer":
            payload = {
                "game_type": row["game_type"],
                "mode": "vs_computer",
                "player_side": seat if seat in {"white", "black"} and row["game_type"] in CARD_GAMES else (
                    "white" if row["game_type"] in CARD_GAMES else other_side(seat)
                ),
                "engine_level": int(row["engine_level"]),
                "engine_time_ms": int(row["engine_time_ms"]),
                "audience": "closed",
            }
            plan = await self._saved_plan(row["id"])
            if plan is not None:
                payload["computers"] = plan[0]
                payload["open_seats"] = plan[1]
            if row["game_type"] == "durak":
                payload["durak_kind"] = str(row["variant"])
            if row["game_type"] == "preferans":
                payload["pool"] = _preferans_pool({"pool": _pool_number(str(row["variant"]))})
                payload["stake"] = _position_stake(row)
            if row["game_type"] == "go":
                payload["board_size"] = int(str(row["variant"]))
            if row["game_type"] == "poker":
                carried = await self._next_table(row, user.id)
                if carried is not None:
                    payload["seat_plan"] = carried["seat_plan"]
                    payload["purses"] = carried["purses"]
            state = await self.create(user, payload)
            return {"game_id": state["id"], "rematch": state["rematch"]}
        return await self._offer_rematch(user, game_id)

    async def decline_rematch(self, user: User, game_id: uuid.UUID) -> dict[str, Any]:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                row = await games_repo.lock_visible(conn, game_id, user.id)
                if row is None:
                    raise AppError(404, "not_found", "Партия не найдена.")
                self._require_rematch(row, user)
                offer = await games_repo.lock_rematch(conn, game_id)
                if offer is None or offer["status"] != "pending" or offer["offered_by"] == user.id:
                    raise AppError(409, "no_rematch", "Предложения реванша нет.")
                await games_repo.decline_rematch(conn, game_id)
                declined = {"offered_by": offer["offered_by"], "status": "declined", "new_game_id": None}
                fresh = dict(row)
        return {"game_id": None, "rematch": rematch_view(fresh, user, declined)}

    async def _offer_rematch(self, user: User, game_id: uuid.UUID) -> dict[str, Any]:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                row = await games_repo.lock_visible(conn, game_id, user.id)
                if row is None:
                    raise AppError(404, "not_found", "Партия не найдена.")
                seat = self._require_rematch(row, user)
                policy = await load_policy(conn)
                if not policy.allows(str(row["game_type"])):
                    raise AppError(403, "game_closed", "Эта игра сейчас закрыта.")
                offer = await games_repo.lock_rematch(conn, game_id)
                if offer is not None and offer["status"] == "accepted" and offer["new_game_id"]:
                    return {
                        "game_id": str(offer["new_game_id"]),
                        "rematch": rematch_view(dict(row), user, dict(offer)),
                    }
                if offer is not None and offer["status"] == "pending" and offer["offered_by"] != user.id:
                    new_id = await self._seat_rematch(conn, row, user, seat)
                    await games_repo.accept_rematch(conn, game_id, new_id)
                    accepted = {"offered_by": offer["offered_by"], "status": "accepted", "new_game_id": new_id}
                    return {
                        "game_id": str(new_id),
                        "rematch": rematch_view(dict(row), user, accepted),
                    }
                await games_repo.place_rematch(conn, game_id, user.id)
                pending = {"offered_by": user.id, "status": "pending", "new_game_id": None}
                return {"game_id": None, "rematch": rematch_view(dict(row), user, pending)}

    async def _seat_rematch(
        self,
        conn: asyncpg.Connection,
        row: asyncpg.Record,
        user: User,
        old_seat: str,
    ) -> uuid.UUID:
        rival = row["opponent_id"] if row["user_id"] == user.id else row["user_id"]
        side = old_seat if old_seat in {"white", "black"} else "white"
        if row["game_type"] not in CARD_GAMES:
            side = other_side(old_seat)
        buy_in = None
        if row["game_type"] == "poker":
            buy_in = await self._poker_buy_in(conn, [user.id, rival])
        payload = {
            "game_type": row["game_type"],
            "mode": "online",
            "player_side": side,
            "engine_level": int(row["engine_level"]),
            "engine_time_ms": int(row["engine_time_ms"]),
            "audience": "closed",
        }
        if row["game_type"] == "durak":
            payload["durak_kind"] = str(row["variant"])
        if row["game_type"] == "preferans":
            payload["pool"] = _preferans_pool({"pool": _pool_number(str(row["variant"]))})
            payload["stake"] = _position_stake(row)
        if row["game_type"] == "go":
            payload["board_size"] = int(str(row["variant"]))
        plan = await self._saved_plan(row["id"])
        if plan is not None and row["game_type"] in CARD_GAMES:
            payload["computers"] = plan[0]
            payload["open_seats"] = plan[1]
        elif row["game_type"] in {"durak", "blackjack", "preferans"}:
            payload["computers"] = 0
            payload["open_seats"] = 2 if row["game_type"] == "preferans" else 1
        prepared = self._prepare(payload, buy_in=buy_in)
        variants = {
            "checkers": "russian",
            "poker": "holdem",
            "uno": "classic",
            "blackjack": "classic",
            "preferans": str(row["variant"]) if str(row["variant"]).startswith("pool-") else "pool-12",
            "durak": str(row["variant"]) if row["game_type"] == "durak" else "podkidnoy",
            "go": str(row["variant"]),
        }
        return await games_repo.insert_game(
            conn,
            user_id=user.id,
            opponent_id=rival,
            game_type=str(row["game_type"]),
            variant=variants.get(str(row["game_type"]), "standard"),
            mode="online",
            player_side=side,
            status="active",
            initial_position=prepared["initial"],
            current_position=prepared["current"],
            result=None,
            result_reason=None,
            engine_level=int(row["engine_level"]),
            engine_time_ms=int(row["engine_time_ms"]),
            join_code=None,
            audience="closed",
        )

    async def _saved_plan(self, game_id: uuid.UUID) -> tuple[int, int] | None:
        async with self.pool.acquire() as conn:
            seats = await games_repo.list_seats(conn, game_id)
        if not seats:
            return None
        computers = sum(1 for seat in seats if seat["kind"] == "computer")
        humans = sum(1 for seat in seats if seat["kind"] == "human")
        return computers, max(0, humans - 1)

    def _require_rematch(self, row: asyncpg.Record, user: User) -> str:
        cards = row["game_type"] in CARD_GAMES
        if row["game_type"] not in {"chess", "checkers", "go", *CARD_GAMES} or row["status"] != "finished":
            raise AppError(409, "no_rematch", "Новую партию предлагают после законченной игры.")
        if not cards and row["result"] not in {"white_win", "black_win"}:
            raise AppError(409, "no_rematch", "Реванш предлагают после победы или поражения.")
        if row["mode"] not in {"online", "vs_computer"}:
            raise AppError(409, "no_rematch", "Реванш есть в партии с соперником или компьютером.")
        seat = self._seat(dict(row), user)
        if seat is None:
            raise AppError(403, "not_player", "Наблюдатель не предлагает реванш.")
        if row["mode"] == "online" and row["opponent_id"] is None and not cards:
            raise AppError(409, "no_rematch", "Соперник ещё не сел за стол.")
        return seat

    def _concede(self, game: dict[str, Any], payloads: list[dict[str, Any]], seat: str) -> dict[str, Any]:
        if game["game_type"] == "go":
            position = str(game["current_position"])
            return {
                "before": position,
                "after": position,
                "notation": "Сдался",
                "payload": None,
                "result": f"{other_side(seat)}_win",
                "reason": "resign",
                "status": "finished",
                "charges": [],
            }
        if game["game_type"] in CARD_GAMES:
            module = card_module(str(game["game_type"]))
            state = _card_state(module, game, payloads)
            before = module.dumps(state)
            after_state = module.leave(state, seat)
            return {
                "before": before,
                "after": module.dumps(after_state),
                "notation": "Вышел из-за стола",
                "payload": {"leave": True, "seat": seat, "by": "human"},
                "result": after_state.get("result"),
                "reason": after_state.get("reason") or "left",
                "status": "finished",
                "charges": [],
            }
        rebuilt = self._rebuild(game, payloads)
        if game["status"] == "waiting":
            result = None
            reason = "left"
        else:
            result = f"{other_side(seat)}_win"
            reason = "resign"
        return {
            "before": rebuilt["position"],
            "after": rebuilt["position"],
            "notation": "Сдался",
            "payload": None,
            "result": result,
            "reason": reason,
            "status": "finished",
            "charges": [],
        }

    async def engine_move(
        self,
        user: User,
        game_id: uuid.UUID,
        version: int,
        steps: int = 40,
    ) -> dict[str, Any]:
        await self._limit_engine(user)
        current = version
        view: dict[str, Any] | None = None
        bound = max(1, min(int(steps), 240))
        for _step in range(bound):
            view = await self._engine_step(user, game_id, current)
            if view["status"] != "active" or not view.get("computer_turn"):
                break
            if bound <= 40 and view.get("table") == "cards" and view.get("held"):
                break
            current = int(view["version"])
        return view or await self.view(user, game_id)

    async def _engine_step(self, user: User, game_id: uuid.UUID, version: int) -> dict[str, Any]:
        async with self.pool.acquire() as conn:
            row = await games_repo.get_visible(conn, game_id, user.id)
            if row is None:
                raise AppError(404, "not_found", "Партия не найдена.")
            moves = await games_repo.list_moves(conn, game_id)
        if row["game_type"] == "go":
            return await self._go_engine_step(user, game_id, version)
        if row["position_version"] != version:
            raise AppError(409, "stale_position", "Позиция уже изменилась. Обновите партию.")
        async with self.pool.acquire() as conn:
            seat_rows = await games_repo.list_seats(conn, game_id)
        game = dict(row)
        game["table_seats"] = [dict(item) for item in seat_rows]
        rebuilt = self._rebuild(game, _payload_list(moves))
        seat = self._seat(game, user)
        computers = {str(item["seat_key"]) for item in seat_rows if item["kind"] == "computer"}
        computer_turn = rebuilt["side"] in computers
        if not user_may_request_engine(
            row["mode"],
            row["status"],
            seat,
            rebuilt["side"],
            computer_turn=computer_turn,
        ):
            raise AppError(409, "engine_rejected", "Сейчас компьютер не может сделать ход.")
        analysis = await self._analyse(user, dict(row), _payload_list(moves), hint=False)
        path = [str(item) for item in analysis["path"]]
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                locked = await self._lock(conn, game_id, user.id, version)
                current_moves = await games_repo.list_moves(conn, game_id)
                applied = self._push(
                    dict(locked),
                    _payload_list(current_moves),
                    path,
                    analysis.get("promotion"),
                    "engine",
                )
                await games_repo.insert_move(
                    conn,
                    game_id=game_id,
                    ply=len(current_moves) + 1,
                    notation=applied["notation"],
                    payload=applied["payload"],
                    position_before=applied["before"],
                    position_after=applied["after"],
                )
                await self._settle(conn, locked, applied)
                await self._save_position(conn, locked, user.id, version, applied)
        return await self.view(user, game_id)

    async def _go_engine_step(self, user: User, game_id: uuid.UUID, version: int) -> dict[str, Any]:
        async with self.pool.acquire() as conn:
            row = await games_repo.get_visible(conn, game_id, user.id)
            seats = await games_repo.list_seats(conn, game_id) if row is not None else []
        if row is None:
            raise AppError(404, "not_found", "Партия не найдена.")
        if row["mode"] != "vs_computer" or row["status"] != "active":
            raise AppError(409, "engine_rejected", "Сейчас компьютер не может сделать ход.")
        if int(row["position_version"]) != version:
            raise AppError(409, "stale_position", "Позиция уже изменилась. Обновите партию.")
        game = dict(row)
        game["table_seats"] = [dict(item) for item in seats]
        seat = self._seat(game, user)
        if seat not in {"black", "white"}:
            raise AppError(409, "engine_rejected", "Сейчас компьютер не может сделать ход.")
        computer = other_side(seat)
        state = load_state(str(row["current_position"]))
        if not computer_pending(state, computer):
            raise AppError(409, "engine_rejected", "Сейчас компьютер не может сделать ход.")
        level = max(1, min(5, int(row["engine_level"])))
        _depth, budget, _slack = GO_LEVELS[level]
        time_ms = max(50, min(int(row["engine_time_ms"]), self.settings.engine_max_time_ms, budget))
        try:
            found = await self.engines.go(state, computer, level, time_ms)
        except AnalysisIncomplete:
            raise
        except Exception as exc:
            logger.warning("go engine failed game=%s error=%s", game_id, type(exc).__name__)
            raise AnalysisIncomplete("Движок го не смог выбрать ход.") from exc
        actions = [item for item in (found.get("actions") or []) if isinstance(item, dict)]
        if not actions:
            raise AnalysisIncomplete("Движок го не смог выбрать ход.")
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                locked = await self._lock(conn, game_id, user.id, version)
                if str(locked["current_position"]) != str(row["current_position"]):
                    raise AppError(409, "stale_position", "Позиция уже изменилась. Обновите партию.")
                cursor = state
                result = None
                reason = None
                ply = len(await games_repo.list_moves(conn, game_id))
                for action in actions:
                    before = dump_state(cursor)
                    try:
                        cursor, done = apply_action(
                            cursor,
                            str(action.get("action") or ""),
                            computer,
                            col=action.get("col") if action.get("col") is None else int(action["col"]),
                            row=action.get("row") if action.get("row") is None else int(action["row"]),
                        )
                    except (GoRuleError, TypeError, ValueError) as exc:
                        raise AnalysisIncomplete("Движок го вернул ход, который правила не допускают.") from exc
                    if done["payload"] is not None:
                        ply += 1
                        payload = dict(done["payload"])
                        payload["by"] = "engine"
                        await games_repo.insert_move(
                            conn,
                            game_id=game_id,
                            ply=ply,
                            notation=str(done["notation"]),
                            payload=payload,
                            position_before=before,
                            position_after=dump_state(cursor),
                        )
                    if done["result"]:
                        result = done["result"]
                        reason = done["reason"]
                applied = {
                    "after": dump_state(cursor),
                    "result": result,
                    "reason": reason,
                    "status": "finished" if result else "active",
                }
                if result:
                    await self._settle(conn, locked, applied)
                await self._save_position(conn, locked, user.id, version, applied)
        return await self.view(user, game_id)

    async def hint(self, user: User, game_id: uuid.UUID, version: int) -> dict[str, Any]:
        if not user.is_admin:
            raise AppError(403, "hint_forbidden", "Действие недоступно.")
        await self._limit_engine(user)
        async with self.pool.acquire() as conn:
            row = await games_repo.get_visible(conn, game_id, user.id)
        if row is None:
            raise AppError(404, "not_found", "Партия не найдена.")
        if row["status"] != "active":
            raise AppError(409, "not_active", "Сейчас это действие недоступно.")
        if row["position_version"] != version:
            raise AppError(409, "stale_position", "Позиция уже изменилась.")
        async with self.pool.acquire() as conn:
            moves = await games_repo.list_moves(conn, game_id)
        try:
            analysis = await self._analyse(user, dict(row), _payload_list(moves), hint=True)
        except (EngineError, AnalysisIncomplete):
            logger.warning("hint failed game=%s", game_id)
            raise
        async with self.pool.acquire() as conn:
            fresh = await games_repo.get_visible(conn, game_id, user.id)
        if fresh is None or fresh["position_version"] != version:
            raise AppError(409, "stale_position", "Позиция уже изменилась.")
        lines = [dict(item) for item in analysis["lines"]]
        if row["game_type"] == "checkers":
            for line in lines:
                line["notation"] = _checkers_hint_notation(line)
        return {
            "version": version,
            "private": True,
            "engine": analysis["engine"],
            "nodes": analysis["nodes"],
            "lines": lines,
        }

    async def flip(self, user: User, game_id: uuid.UUID) -> dict[str, Any]:
        async with self.pool.acquire() as conn:
            row = await games_repo.get_visible(conn, game_id, user.id)
            if row is None:
                raise AppError(404, "not_found", "Партия не найдена.")
            creator = row["user_id"] == user.id
            current = row["creator_flipped"] if creator else row["opponent_flipped"]
            await games_repo.set_flip(
                conn,
                game_id=game_id,
                user_id=user.id,
                creator=creator,
                flipped=not current,
            )
        return await self.view(user, game_id)

    async def save(self, user: User, game_id: uuid.UUID) -> dict[str, Any]:
        async with self.pool.acquire() as conn:
            row = await games_repo.get_visible(conn, game_id, user.id)
            if row is None:
                raise AppError(404, "not_found", "Партия не найдена.")
            await games_repo.touch(conn, game_id, user.id)
            fresh = await games_repo.get_visible(conn, game_id, user.id)
        assert fresh is not None
        return {"saved": True, "updated_at": fresh["updated_at"].isoformat()}

    async def export(self, user: User, game_id: uuid.UUID) -> tuple[str, str, str]:
        async with self.pool.acquire() as conn:
            row = await games_repo.get_visible(conn, game_id, user.id)
            if row is None:
                raise AppError(404, "not_found", "Партия не найдена.")
            if row["game_type"] in ADULT_GAMES:
                reason = await adult_denial(conn, user.id, str(row["game_type"]))
                if reason:
                    raise AppError(403, "adult_only", reason)
            moves = await games_repo.list_moves(conn, game_id)
        payloads = _payload_list(moves)
        white_name, black_name = self._names(dict(row))
        if row["game_type"] in CARD_GAMES:
            notations = [row_move["notation"] for row_move in moves]
            text = "\n".join(notations) if notations else "Партия без записанных ходов."
            return text, "text/plain; charset=utf-8", f"{row['game_type']}.txt"
        if row["game_type"] == "go":
            state = load_state(str(row["current_position"]))
            created = row["created_at"]
            played_on = created.date().isoformat() if hasattr(created, "date") else ""
            text = export_sgf(
                size=int(state["size"]),
                moves=[item for item in payloads if item.get("kind") in {"move", "pass"}],
                black_name=black_name,
                white_name=white_name,
                played_on=played_on,
                result=row["result"],
                reason=row["result_reason"],
                margin_half=state.get("margin_half") if isinstance(state.get("margin_half"), int) else None,
            )
            return text, "application/x-go-sgf; charset=utf-8", "game.sgf"
        if row["game_type"] == "chess":
            text = export_pgn(
                row["initial_position"],
                [str(item["uci"]) for item in payloads],
                white_name=white_name,
                black_name=black_name,
                result=row["result"],
            )
            return text, "text/plain; charset=utf-8", "game.pgn"
        notations = [row_move["notation"] for row_move in moves]
        text = dump_game_record(row["initial_position"], notations, row["result"])
        return text, "text/plain; charset=utf-8", "checkers.txt"

    async def dashboard(self, user: User, *, page: int = 1) -> dict[str, Any]:
        page_size = RECENT_PAGE_SIZE
        requested = page if page > 0 else 1
        async with self.pool.acquire() as conn:
            total = await games_repo.count_recent(conn, user.id)
            pages = max(1, (total + page_size - 1) // page_size)
            current = min(requested, pages)
            recent = await games_repo.list_recent(
                conn,
                user.id,
                limit=page_size,
                offset=(current - 1) * page_size,
            )
            opened = await games_repo.latest_open(conn, user.id)
            prefs = await settings_repo.get_settings(conn, user.id)
        start = (current - 1) * page_size + 1 if recent else 0
        end = start + len(recent) - 1 if recent else 0
        shown = f"{start} из {total}" if recent and start == end else ""
        if recent and start != end:
            shown = f"{start}–{end} из {total}"
        shown_recent = []
        for row in recent:
            item = dict(row)
            item["you_mark"] = for_viewer(item, user.id)
            item.pop("finish_position", None)
            shown_recent.append(item)
        return {
            "continue_id": opened["id"] if opened else None,
            "continue_game": dict(opened) if opened else None,
            "recent": shown_recent,
            "page": current,
            "pages": pages,
            "total": total,
            "shown": shown,
            "page_links": page_links(current, pages),
            "settings": dict(prefs),
        }

    async def _analyse(
        self,
        user: User,
        game: dict[str, Any],
        payloads: list[dict[str, Any]],
        *,
        hint: bool,
    ) -> dict[str, Any]:
        async with self.pool.acquire() as conn:
            prefs_row = await settings_repo.get_settings(conn, user.id)
        preferences = as_preferences(prefs_row["analysis_preferences"])
        if game["game_type"] == "go":
            raise AppError(409, "engine_rejected", "В го нет подсказок компьютера.")
        if game["game_type"] in CARD_GAMES:
            return self._card_line(game, payloads)
        if game["game_type"] == "chess":
            return await self._analyse_chess(game, payloads, preferences, hint=hint)
        return await self._analyse_checkers(game, payloads, preferences, hint=hint)

    async def _analyse_chess(
        self,
        game: dict[str, Any],
        payloads: list[dict[str, Any]],
        preferences: dict[str, Any],
        *,
        hint: bool,
    ) -> dict[str, Any]:
        board = replay_chess(str(game["initial_position"]), payloads)
        if hint:
            depth = int(preferences.get("chess_depth") or 12)
            time_s = min(int(preferences.get("chess_time_ms") or 1000), self.settings.engine_max_time_ms) / 1000
            multipv = max(1, min(3, int(preferences.get("chess_multipv") or 1)))
            skill = None
            slack_cp = 0
        else:
            time_s, depth, skill, multipv, slack_cp = level_budget(
                int(game["engine_level"]),
                int(game["engine_time_ms"]),
                self.settings.engine_max_time_ms,
            )
        settings_hash = _hash(
            {
                "time": round(time_s, 3),
                "depth": depth,
                "multipv": multipv,
                "skill": skill or 20,
                "slack": slack_cp,
            }
        )
        cached = await self._read_cache(
            game,
            board.fen(),
            self.engines.stockfish.version,
            settings_hash,
        )
        if cached and self._chess_cached_ok(board, cached):
            return cached
        lines = await self.engines.chess(board, time_s=time_s, depth=depth, multipv=multipv, skill=skill)
        if not hint:
            chosen = choose_line(
                lines,
                white_to_move=board.turn == chess.WHITE,
                slack_cp=slack_cp,
            )
            lines = [chosen, *[line for line in lines if line is not chosen]]
        rendered = []
        for line in lines:
            probe = board.copy(stack=False)
            pv_san: list[str] = []
            for uci in line.pv:
                move = chess.Move.from_uci(uci)
                if move not in probe.legal_moves:
                    break
                pv_san.append(probe.san(move))
                probe.push(move)
            rendered.append(
                {
                    "notation": line.san,
                    "path": list(line.path),
                    "promotion": line.promotion,
                    "score_white": line.score_white,
                    "mate": line.mate,
                    "pv": pv_san,
                    "depth": line.depth,
                }
            )
        if not rendered:
            raise AnalysisIncomplete("Движок не вернул легальный ход.")
        result = {
            "engine": self.engines.stockfish.version,
            "nodes": lines[0].nodes,
            "path": rendered[0]["path"],
            "promotion": rendered[0]["promotion"],
            "lines": rendered,
        }
        await self._write_cache(
            game,
            board.fen(),
            self.engines.stockfish.version,
            settings_hash,
            result,
            rendered[0]["depth"],
        )
        return result

    async def _analyse_checkers(
        self,
        game: dict[str, Any],
        payloads: list[dict[str, Any]],
        preferences: dict[str, Any],
        *,
        hint: bool,
    ) -> dict[str, Any]:
        position, _keys = replay_checkers(str(game["initial_position"]), payloads)
        level = int(preferences.get("checkers_level") or game["engine_level"]) if hint else int(game["engine_level"])
        level = max(1, min(5, level))
        depth, budget, slack = LEVELS[level]
        requested = int(preferences.get("checkers_time_ms") or budget) if hint else int(game["engine_time_ms"])
        time_ms = max(50, min(requested, self.settings.engine_max_time_ms))
        if hint:
            slack = 0
        else:
            time_ms = min(time_ms, budget)
        weights = _weights(preferences) if hint else DEFAULT_WEIGHTS
        variety = bool(preferences.get("variety")) and hint
        settings_hash = _hash(
            {"depth": depth, "time_ms": time_ms, "weights": asdict(weights), "variety": variety, "slack": slack}
        )
        position_text = dump_rcp(position)
        engine_token = ENGINE_NAME if simple_ready() else "boardmentor-checkers 1.0.0"
        cached = await self._read_cache(game, position_text, engine_token, settings_hash)
        if cached and self._checkers_cached_ok(position, cached):
            return cached
        try:
            found = await self.engines.checkers(
                position_text,
                depth=depth,
                time_ms=time_ms,
                weights=asdict(weights),
                variety=variety,
                slack=slack,
            )
        except AnalysisIncomplete:
            raise
        except Exception as exc:
            logger.warning("checkers engine failed game=%s error=%s", game["id"], type(exc).__name__)
            raise AnalysisIncomplete("Шашечный движок не смог выбрать ход.") from exc
        path = [str(item) for item in found["path"]]
        if not self._checkers_path_ok(position, path):
            raise AnalysisIncomplete("Движок вернул ход, который правила не допускают.")
        line = {
            "notation": found["notation"],
            "path": path,
            "promotion": None,
            "score_white": found["score_white"],
            "mate": None,
            "pv": found["pv"],
            "depth": found["depth"],
        }
        result = {
            "engine": str(found.get("engine") or engine_token),
            "nodes": found["nodes"],
            "path": path,
            "promotion": None,
            "lines": [line],
        }
        await self._write_cache(game, position_text, engine_token, settings_hash, result, int(found["depth"]))
        return result

    def _validate_create(self, data: dict[str, Any]) -> None:
        if data["game_type"] not in {"chess", "checkers", "go", *CARD_GAMES}:
            raise AppError(422, "bad_game", "Выберите игру из каталога.")
        if data["game_type"] == "go":
            if data["mode"] not in {"online", "vs_computer"}:
                raise AppError(422, "bad_mode", "Го играется с человеком или с компьютером.")
            try:
                size = int(data.get("board_size") or 19)
            except (TypeError, ValueError):
                size = 0
            if size not in {9, 13, 19}:
                raise AppError(422, "bad_board", "Размер доски го: 9, 13 или 19.")
            data["board_size"] = size
        if data["mode"] not in {"vs_computer", "free", "analysis", "lesson", "online"}:
            raise AppError(422, "bad_mode", "Неизвестный режим партии.")
        if data["player_side"] not in {"white", "black"}:
            raise AppError(422, "bad_side", "Сторона должна быть белой или чёрной.")
        level = int(data["engine_level"])
        think = int(data["engine_time_ms"])
        if not 1 <= level <= 5 or not 100 <= think <= 10000:
            raise AppError(422, "bad_engine", "Проверьте уровень и время расчёта.")
        if data["game_type"] in CARD_GAMES and (
            data.get("computers") is not None or data.get("open_seats") is not None
        ):
            computers = int(data.get("computers") or 0)
            opens = int(data.get("open_seats") or 0)
            total = computers + opens
            if data["game_type"] == "preferans":
                if computers < 0 or opens < 0 or total != 2:
                    raise AppError(422, "bad_seats", "В преферансе за столом трое: вы и ещё двое.")
            elif data["game_type"] == "blackjack":
                if computers < 0 or opens < 0 or computers > 5 or opens > 5 or total > 5:
                    raise AppError(422, "bad_seats", "Кроме вас за блэкджеком не больше пяти мест.")
            elif computers < 0 or opens < 0 or computers > 5 or opens > 5 or not 1 <= total <= 5:
                raise AppError(
                    422,
                    "bad_seats",
                    "Кроме вас за столом от одного до пяти мест, и компьютеров не больше пяти.",
                )
            data["computers"] = computers
            data["open_seats"] = opens
            data["mode"] = "online" if opens else "vs_computer"
        audience = str(data.get("audience") or "closed")
        if data["mode"] not in {"online", "vs_computer"}:
            data["audience"] = "closed"
        elif audience not in {"open", "closed"}:
            raise AppError(422, "bad_audience", "Выберите открытый или закрытый стол.")
        else:
            data["audience"] = audience

    def _rematch_if_solvent(self, game: dict[str, Any], offer: dict[str, Any], seat_key: str) -> dict[str, Any]:
        raw = game.get("current_position")
        try:
            position = json.loads(raw) if isinstance(raw, str) else dict(raw or {})
        except json.JSONDecodeError:
            return offer
        cash = poker.cash_out(position)
        if cash is None:
            return offer
        solvent = [seat for seat, amount in cash.items() if int(amount) >= poker.BB]
        if len(solvent) < 2 or int(cash.get(seat_key, 0)) < poker.BB:
            return {
                "available": False,
                "state": "idle",
                "game_id": None,
                "note": "Фишки кончились. Этот стол закончен.",
            }
        return offer

    async def _next_table(self, row: Any, user_id: uuid.UUID) -> dict[str, Any] | None:
        raw = row["current_position"]
        try:
            position = json.loads(raw) if isinstance(raw, str) else dict(raw)
        except json.JSONDecodeError:
            return None
        cash = poker.cash_out(position)
        if cash is None:
            return None
        async with self.pool.acquire() as conn:
            seats = [dict(item) for item in await games_repo.list_seats(conn, row["id"])]
            wallet = int(await balance(conn, user_id))
        if seats:
            plan = []
            for item in seats:
                key = str(item["seat_key"])
                amount = int(cash.get(key, 0))
                if item.get("kind") == "human" and item.get("user_id") == user_id:
                    amount = min(amount, wallet)
                plan.append({"key": key, "kind": str(item["kind"]), "purse": amount})
        else:
            human = str(row["player_side"])
            other = "black" if human == "white" else "white"
            plan = [
                {"key": human, "kind": "human", "purse": min(int(cash.get(human, 0)), wallet)},
                {"key": other, "kind": "computer", "purse": int(cash.get(other, 0))},
            ]
        solvent = [item for item in plan if int(item["purse"]) >= poker.BB]
        human_can = any(item["kind"] == "human" and int(item["purse"]) >= poker.BB for item in solvent)
        if len(solvent) < 2 or not human_can:
            raise AppError(409, "table_done", "Фишки кончились. Этот стол закончен.")
        return {"seat_plan": plan, "purses": {str(item["key"]): int(item["purse"]) for item in plan}}

    async def _poker_buy_in(self, conn: asyncpg.Connection, user_ids: list[Any]) -> int:
        purses: list[int] = []
        seen: set[Any] = set()
        for user_id in user_ids:
            if user_id is None or user_id in seen:
                continue
            seen.add(user_id)
            purses.append(int(await balance(conn, user_id)))
        if not purses:
            return poker.STACK
        return min(poker.STACK, max(min(purses), 0))

    async def _preferans_buy_in(self, conn: asyncpg.Connection, user_ids: list[Any], stake: object) -> int:
        price = preferans.stake_of(stake)
        need = preferans.stack_for(price)
        for user_id in user_ids:
            if user_id is None:
                continue
            if int(await balance(conn, user_id)) < need:
                raise AppError(
                    409,
                    "no_chips",
                    f"Не хватает фишек: при цене очка {price} на стол нужно {need}. "
                    "Остальное остаётся на счёте, в долг партия не идёт.",
                )
        return need

    def _prepare(self, data: dict[str, Any], buy_in: int | None = None) -> dict[str, Any]:
        game_type = data["game_type"]
        if data.get("pgn") and game_type != "chess":
            raise AppError(422, "bad_import", "PGN используется только для шахмат.")
        if data.get("initial_fen") and game_type != "chess":
            raise AppError(422, "bad_import", "Для шашек используйте формат позиции RCP, а не FEN.")
        if data.get("initial_position") and game_type != "checkers":
            raise AppError(422, "bad_import", "Формат RCP относится к русским шашкам.")
        try:
            if game_type in CARD_GAMES:
                return self._prepare_cards(data, buy_in)
            if game_type == "chess":
                return self._prepare_chess(data)
            if game_type == "go":
                return self._prepare_go(data)
            return self._prepare_checkers(data)
        except (ValueError, IllegalMove) as exc:
            message = exc.message if isinstance(exc, IllegalMove) else str(exc)
            raise AppError(422, "bad_import", message) from exc

    def _fresh_purses(self, human: str, computers: list[str], purse: int) -> dict[str, int]:
        spread = poker.spread_purses(computers, purse, secrets.randbits(32))
        amounts = {human: purse, **spread}
        return amounts

    def _salon_variant(self, data: dict[str, Any]) -> str:
        kind = str(data.get("durak_kind") or "podkidnoy")
        if kind not in {"podkidnoy", "perevodnoy"}:
            raise AppError(422, "bad_variant", "Выберите подкидного или переводного дурака.")
        return kind

    def _mark_dealer(self, game: str, state: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
        if game != "blackjack":
            return state
        try:
            level = int(data.get("engine_level") or 3)
        except (TypeError, ValueError):
            level = 3
        state["level"] = max(1, min(5, level))
        return state

    def _prepare_salon(self, data: dict[str, Any], buy_in: int | None) -> dict[str, Any]:
        game = str(data["game_type"])
        module = card_module(game)

        def arm(table: dict[str, Any]) -> dict[str, Any]:
            if game == "preferans":
                table["stake"] = preferans.stake_of(data.get("stake"))
            return table

        if game == "durak":
            variant = self._salon_variant(data)
        elif game == "preferans":
            variant = f"pool-{_preferans_pool(data)}"
        else:
            variant = "classic"
        explicit = data.get("computers") is not None or data.get("open_seats") is not None
        if not explicit and data["mode"] == "online":
            if game == "preferans":
                keys = ["p0", "p1", "p2"]
                rows = [("p0", "human", None), ("p1", "human", None), ("p2", "human", None)]
            else:
                keys = ["white", "black"]
                rows = None
            waiting_state = self._mark_dealer(game, module.waiting(keys, variant), data)
            return self._salon_ready(module, arm(waiting_state), rows, waiting=True)
        computers = data.get("computers")
        opens = data.get("open_seats")
        if game == "preferans":
            computers = 2 if computers is None else int(computers)
            opens = 0 if opens is None else int(opens)
        elif game == "blackjack":
            computers = 0 if computers is None else int(computers)
            opens = 0 if opens is None else int(opens)
        else:
            computers = 1 if computers is None else int(computers)
            opens = 0 if opens is None else int(opens)
        extra = computers + opens
        if game == "preferans" and buy_in is not None:
            purse = int(buy_in)
        else:
            purse = int(buy_in or 200)
        if extra == 0:
            data["player_side"] = "white"
            data["mode"] = "vs_computer"
            state = self._mark_dealer(game, module.deal(["white"], variant, {"white": purse}), data)
            return self._salon_ready(module, arm(state), None, waiting=False)
        if extra == 1 and game != "preferans":
            keys = ["white", "black"]
            rows = None
        else:
            keys = [f"p{index}" for index in range(extra + 1)]
            kinds = ["human", *["computer"] * int(computers), *["human"] * int(opens)]
            rows = [(key, kind, None) for key, kind in zip(keys, kinds, strict=True)]
        if opens:
            state = self._mark_dealer(game, module.waiting(keys, variant), data)
            return self._salon_ready(module, arm(state), rows, waiting=True)
        if game == "preferans" and rows:
            bank = int(buy_in) if buy_in is not None else 0
            purses = {key: bank for key, _kind, _owner in rows}
        else:
            purses = {key: purse for key in keys}
        state = self._mark_dealer(game, module.deal(keys, variant, purses), data)
        return self._salon_ready(module, arm(state), rows, waiting=False)

    def _salon_ready(
        self,
        module: Any,
        state: dict[str, Any],
        rows: list[tuple[str, str, None]] | None,
        *,
        waiting: bool,
    ) -> dict[str, Any]:
        charges = []
        if not waiting:
            bag = state.get("stacks") if state.get("kind") == "preferans" else state.get("committed")
            charges = [
                (str(seat), int(amount))
                for seat, amount in (bag or {}).items()
                if int(amount or 0)
            ]
        text = module.dumps(state)
        ready = {
            "initial": text,
            "current": text,
            "moves": [],
            "status": "waiting" if waiting else ("finished" if state.get("result") else "active"),
            "result": None if waiting else state.get("result"),
            "reason": None if waiting else state.get("reason"),
            "charges": [] if waiting else charges,
        }
        if rows:
            ready["seat_rows"] = rows
        return ready

    def _prepare_cards(self, data: dict[str, Any], buy_in: int | None = None) -> dict[str, Any]:
        if data["mode"] not in {"vs_computer", "online"}:
            raise AppError(422, "bad_mode", "Карточная игра идёт против компьютера или онлайн.")
        if data["game_type"] not in {"poker", "uno"}:
            return self._prepare_salon(data, buy_in)
        module = poker if data["game_type"] == "poker" else uno
        plan = data.get("seat_plan")
        if data["game_type"] == "poker" and isinstance(plan, list) and plan:
            playing = [item for item in plan if int(item["purse"]) >= poker.BB]
            if len(playing) < 2:
                raise AppError(409, "table_done", "За столом остались фишки только у одного игрока.")
            keys = [str(item["key"]) for item in playing]
            rows = [(str(item["key"]), str(item["kind"]), None) for item in plan]
            purses = {str(item["key"]): int(item["purse"]) for item in playing}
            busted = [str(item["key"]) for item in plan if int(item["purse"]) < poker.BB]
            state = poker.deal_table(keys, buy_in or poker.STACK, purses, busted)
            charges = [(seat, int(amount)) for seat, amount in state.get("committed", {}).items() if int(amount)]
            text = module.dumps(state)
            return {
                "initial": text,
                "current": text,
                "moves": [],
                "status": "finished" if state.get("result") else "active",
                "result": state.get("result"),
                "reason": state.get("reason"),
                "charges": charges,
                "seat_rows": rows,
            }
        computers = data.get("computers")
        opens = data.get("open_seats")
        extra = int(computers or 0) + int(opens or 0)
        purse = int(buy_in or poker.STACK)
        if computers is not None and extra > 1:
            keys = [f"p{index}" for index in range(extra + 1)]
            kinds = ["human", *["computer"] * int(computers), *["human"] * int(opens)]
            rows = [(key, kind, None) for key, kind in zip(keys, kinds, strict=True)]
            if data["mode"] == "online":
                state = module.waiting_table(keys)
                charges: list[tuple[str, int]] = []
                status = "waiting"
            else:
                if data["game_type"] == "poker":
                    comp = [key for key, kind in zip(keys, kinds, strict=True) if kind == "computer"]
                    state = poker.deal_table(keys, purse, self._fresh_purses(keys[0], comp, purse))
                else:
                    state = module.deal_table(keys)
                charges = (
                    [(seat, int(amount)) for seat, amount in state.get("committed", {}).items() if int(amount)]
                    if data["game_type"] == "poker"
                    else []
                )
                status = "finished" if state.get("result") else "active"
            text = module.dumps(state)
            return {
                "initial": text,
                "current": text,
                "moves": [],
                "status": status,
                "result": state.get("result"),
                "reason": state.get("reason"),
                "charges": charges,
                "seat_rows": rows,
            }
        if data["mode"] == "online":
            text = module.dumps(module.waiting())
            return {
                "initial": text,
                "current": text,
                "moves": [],
                "status": "waiting",
                "result": None,
                "reason": None,
                "charges": [],
            }
        if data["game_type"] == "poker":
            human = str(data["player_side"])
            computer = "black" if human == "white" else "white"
            carried = data.get("purses") if isinstance(data.get("purses"), dict) else None
            amounts = carried or self._fresh_purses(human, [computer], purse)
            state = poker.deal(purse, amounts)
        else:
            state = module.deal()
        text = module.dumps(state)
        charges = [(data["player_side"], poker.blind_for(data["player_side"]))] if data["game_type"] == "poker" else []
        return {
            "initial": text,
            "current": text,
            "moves": [],
            "status": "finished" if state.get("result") else "active",
            "result": state.get("result"),
            "reason": state.get("reason"),
            "charges": charges,
        }

    def _prepare_go(self, data: dict[str, Any]) -> dict[str, Any]:
        text = dump_state(new_match(int(data["board_size"])))
        return {
            "initial": text,
            "current": text,
            "moves": [],
            "status": "active",
            "result": None,
            "reason": None,
        }

    def _prepare_chess(self, data: dict[str, Any]) -> dict[str, Any]:
        if data.get("pgn"):
            initial, records, board = import_pgn(str(data["pgn"]))
            moves = []
            cursor = parse_board(initial)
            for record in records:
                before = cursor.fen()
                push_user_move(cursor, list(record.path), record.promotion)
                moves.append(
                    {
                        "notation": record.san,
                        "before": before,
                        "after": cursor.fen(),
                        "payload": {
                            "uci": record.uci,
                            "path": list(record.path),
                            "promotion": record.promotion,
                            "by": "human",
                        },
                    }
                )
            stored = [item["payload"] for item in moves]
            outcome = self._rebuild({"game_type": "chess", "initial_position": initial}, stored)
            return {
                "initial": initial,
                "current": board.fen(),
                "moves": moves,
                "status": "finished" if outcome["result"] else "active",
                "result": outcome["result"],
                "reason": outcome["reason"],
            }
        initial = parse_board(str(data["initial_fen"])).fen() if data.get("initial_fen") else STARTING_FEN
        specs = []
        for text in data.get("moves") or []:
            specs.append(_uci_spec(str(text)))
        current, stored = _apply_listed_chess(initial, specs)
        outcome = self._rebuild(
            {"game_type": "chess", "initial_position": initial},
            [item["payload"] for item in stored],
        )
        return {
            "initial": initial,
            "current": current,
            "moves": stored,
            "status": "finished" if outcome["result"] else "active",
            "result": outcome["result"],
            "reason": outcome["reason"],
        }

    def _prepare_checkers(self, data: dict[str, Any]) -> dict[str, Any]:
        initial = dump_rcp(parse_rcp(str(data["initial_position"]))) if data.get("initial_position") else INITIAL_RCP
        position = parse_rcp(initial)
        moves = []
        for text in data.get("moves") or []:
            before = dump_rcp(position)
            move = move_from_path(position, parse_notation(str(text)))
            position = apply_move(position, move)
            moves.append(
                {
                    "notation": format_move(move),
                    "before": before,
                    "after": dump_rcp(position),
                    "payload": {
                        "path": list(move.path),
                        "algebraic": format_move_algebraic(move),
                        "by": "human",
                    },
                }
            )
        outcome = self._rebuild(
            {"game_type": "checkers", "initial_position": initial},
            [item["payload"] for item in moves],
        )
        return {
            "initial": initial,
            "current": dump_rcp(position),
            "moves": moves,
            "status": "finished" if outcome["result"] else "active",
            "result": outcome["result"],
            "reason": outcome["reason"],
        }

    def _push(
        self,
        game: dict[str, Any],
        payloads: list[dict[str, Any]],
        path: list[str],
        promotion: str | None,
        actor: str,
    ) -> dict[str, Any]:
        if game["game_type"] in CARD_GAMES:
            return self._push_card(game, payloads, path, actor)
        if game["game_type"] == "checkers" and promotion:
            raise IllegalMove("У шашки нет выбора фигуры превращения.")
        self._rebuild(game, payloads)
        if game["game_type"] == "chess":
            board = replay_chess(str(game["initial_position"]), payloads)
            before = board.fen()
            side_before = "white" if board.turn == chess.WHITE else "black"
            record = push_user_move(board, path, promotion)
            after_board = board
            outcome = self._rebuild(game, [*payloads, {"uci": record.uci, "path": list(record.path)}])
            return {
                "before": before,
                "after": after_board.fen(),
                "notation": record.san,
                "payload": {
                    "uci": record.uci,
                    "path": list(record.path),
                    "promotion": record.promotion,
                    "by": actor,
                },
                "side_before": side_before,
                "side_after": "white" if after_board.turn == chess.WHITE else "black",
                "result": outcome["result"],
                "reason": outcome["reason"],
                "status": "finished" if outcome["result"] else "active",
            }
        position, _keys = replay_checkers(str(game["initial_position"]), payloads)
        side_before = "white" if position.side == 0 else "black"
        before = dump_rcp(position)
        move = move_from_path(position, tuple(int(square) for square in path))
        outcome = self._rebuild(game, [*payloads, {"path": list(move.path)}])
        after = apply_move(position, move)
        return {
            "before": before,
            "after": dump_rcp(after),
            "notation": format_move(move),
            "payload": {
                "path": list(move.path),
                "algebraic": format_move_algebraic(move),
                "by": actor,
            },
            "side_before": side_before,
            "side_after": "white" if after.side == 0 else "black",
            "result": outcome["result"],
            "reason": outcome["reason"],
            "status": "finished" if outcome["result"] else "active",
        }

    def _push_card(
        self,
        game: dict[str, Any],
        payloads: list[dict[str, Any]],
        path: list[str],
        actor: str,
    ) -> dict[str, Any]:
        module = card_module(str(game["game_type"]))
        state = _card_state(module, game, payloads)
        actions = module.legal(state)
        notation = next((item["notation"] for item in actions if list(item["path"]) == list(path)), "")
        if not notation and len(path) >= 3 and path[1] in {"bet", "raise"}:
            sized = next((item for item in actions if list(item["path"])[:2] == list(path)[:2]), None)
            try:
                amount = int(path[2])
            except (TypeError, ValueError):
                amount = 0
            ceiling = int(sized.get("max") or 0) if isinstance(sized, dict) else 0
            if sized and amount and ceiling and amount >= ceiling:
                notation = "Ва-банк"
            elif path[1] == "bet":
                notation = f"Ставка {amount}"
            else:
                notation = f"Повысить до {amount}"
        if not notation:
            notation = " ".join(path)
        side_before = str(state.get("to_move") or "white")
        before = module.dumps(state)
        try:
            played = module.apply(state, path)
            if isinstance(played, tuple):
                after_state, charges = played
            else:
                after_state = played
                charges = []
            if game["game_type"] == "uno" and (after_state.get("acts") or {}).get(side_before) == "miss" and "УНО" not in notation:
                notation = f"{notation} · не сказал УНО"
        except ValueError as exc:
            raise IllegalMove(str(exc)) from exc
        return {
            "before": before,
            "after": module.dumps(after_state),
            "notation": notation,
            "payload": {"path": list(path), "by": actor, "seat": side_before},
            "side_before": side_before,
            "side_after": str(after_state.get("to_move") or side_before),
            "result": after_state.get("result"),
            "reason": after_state.get("reason"),
            "status": "finished" if after_state.get("result") else "active",
            "charges": charges,
        }

    def _card_line(self, game: dict[str, Any], payloads: list[dict[str, Any]]) -> dict[str, Any]:
        module = card_module(str(game["game_type"]))
        state = _card_state(module, game, payloads)
        path = module.suggest(state, int(game["engine_level"])) or []
        notation = next((item["notation"] for item in module.legal(state) if list(item["path"]) == list(path)), "")
        line = {
            "notation": notation,
            "path": path,
            "promotion": None,
            "score_white": 0,
            "mate": None,
            "pv": [],
            "depth": 1,
        }
        return {"engine": str(game["game_type"]), "nodes": 1, "path": path, "promotion": None, "lines": [line]}

    def _rebuild(self, game: dict[str, Any], payloads: list[dict[str, Any]]) -> dict[str, Any]:
        if game["game_type"] == "go":
            state = load_state(str(game["current_position"]))
            return {
                "position": str(game["current_position"]),
                "side": str(state["to_play"]),
                "result": game.get("result"),
                "reason": game.get("result_reason"),
            }
        if game["game_type"] in CARD_GAMES:
            module = card_module(str(game["game_type"]))
            state = _card_state(module, game, payloads)
            return {
                "position": module.dumps(state),
                "side": str(state.get("to_move") or "white"),
                "result": state.get("result"),
                "reason": state.get("reason"),
            }
        if game["game_type"] == "chess":
            board = replay_chess(str(game["initial_position"]), payloads)
            outcome = outcome_of(board)
            return {
                "position": board.fen(),
                "side": "white" if board.turn == chess.WHITE else "black",
                "result": None if outcome is None else outcome.result,
                "reason": None if outcome is None else outcome.reason,
            }
        position, keys = replay_checkers(str(game["initial_position"]), payloads)
        end = checkers_outcome(position, keys, len(keys) - 1)
        return {
            "position": dump_rcp(position),
            "side": "white" if position.side == 0 else "black",
            "result": None if end is None else end.result,
            "reason": None if end is None else end.reason,
        }

    async def _lock(
        self,
        conn: asyncpg.Connection,
        game_id: uuid.UUID,
        user_id: uuid.UUID,
        version: int,
    ) -> Any:
        row = await games_repo.lock_visible(conn, game_id, user_id)
        if row is None:
            raise AppError(404, "not_found", "Партия не найдена.")
        if row["position_version"] != version:
            raise AppError(409, "stale_position", "Позиция уже изменилась. Обновите партию.")
        return row

    async def _save_position(
        self,
        conn: asyncpg.Connection,
        row: Any,
        user_id: uuid.UUID,
        version: int,
        applied: dict[str, Any],
    ) -> None:
        saved = await games_repo.update_position(
            conn,
            game_id=row["id"],
            user_id=user_id,
            version=version,
            current_position=str(applied["after"]),
            status=str(applied["status"]),
            result=applied["result"],
            result_reason=applied["reason"],
        )
        if not saved:
            raise AppError(409, "stale_position", "Позиция уже изменилась. Обновите партию.")

    async def _settle(self, conn: asyncpg.Connection, row: Any, applied: dict[str, Any]) -> None:
        game = dict(row)
        game_id = game["id"]
        seats = [dict(item) for item in await games_repo.list_seats(conn, game_id)]
        for seat, amount in applied.get("charges") or []:
            payer = seat_user(game, str(seat), seats or None)
            if payer is not None:
                await charge(conn, payer, int(amount), reason="stake", game_id=game_id)
                self._forget_purse(payer)
        if not applied.get("result") or game.get("result") is not None:
            return
        if str(game["game_type"]) in CHIP_GAMES:
            if await already_paid(conn, game_id, "pot"):
                return
            try:
                payout = json.loads(str(applied["after"])).get("payout") or {}
            except json.JSONDecodeError:
                payout = {}
            for seat, amount in payout.items():
                winner = seat_user(game, str(seat), seats or None)
                if winner is not None and int(amount) > 0:
                    await credit(conn, winner, int(amount), reason="pot", game_id=game_id)
                    self._forget_purse(winner)
            return
        if await already_paid(conn, game_id, "table"):
            return
        result = str(applied["result"])
        if str(game["game_type"]) == "durak":
            try:
                final = json.loads(str(applied["after"]))
            except json.JSONDecodeError:
                final = {}
            loser = str(final.get("loser") or "")
            for seat in list(final.get("order") or ["white", "black"]):
                player = seat_user(game, str(seat), seats or None)
                if player is None:
                    continue
                if result == f"{seat}_win":
                    amount = 30
                elif result == "draw" and not loser:
                    amount = 10
                elif result == "draw" and loser and str(seat) != loser:
                    amount = 20
                else:
                    continue
                await credit(conn, player, amount, reason="table", game_id=game_id)
                self._forget_purse(player)
            return
        for seat in ("white", "black"):
            player = seat_user(game, seat)
            if player is None:
                continue
            if result == "draw":
                amount = 10
            elif result == f"{seat}_win":
                amount = 30
            else:
                continue
            await credit(conn, player, amount, reason="table", game_id=game_id)
            self._forget_purse(player)

    async def _activate_if_full(self, conn: asyncpg.Connection, row: Any, claimed: str) -> None:
        if claimed == "self":
            return
        game_id = row["id"]
        if claimed == "multi" and await games_repo.vacancies(conn, game_id) > 0:
            return
        if row["game_type"] in CARD_GAMES:
            await self._open_table(conn, game_id, row["user_id"])
            return
        await conn.execute(
            """
            UPDATE games
            SET status = 'active', position_version = position_version + 1, updated_at = now()
            WHERE id = $1 AND status = 'waiting'
            """,
            game_id,
        )

    async def _open_table(self, conn: asyncpg.Connection, game_id: uuid.UUID, joiner_id: uuid.UUID) -> None:
        row = await conn.fetchrow("SELECT * FROM games WHERE id = $1", game_id)
        if row is None or row["game_type"] not in CARD_GAMES:
            return
        if row["game_type"] in ADULT_GAMES:
            reason = await adult_denial(conn, joiner_id, str(row["game_type"]))
            if reason:
                raise AppError(403, "adult_only", reason)
        raw = row["current_position"]
        state = json.loads(raw) if isinstance(raw, str) else dict(raw)
        if state.get("phase") != "waiting":
            return
        module = card_module(str(row["game_type"]))
        order = state.get("order")
        seats = [dict(item) for item in await games_repo.list_seats(conn, game_id)]
        buy_in = poker.STACK
        purses = None
        if row["game_type"] == "poker":
            ids = [item.get("user_id") for item in seats]
            ids.extend([row["user_id"], row["opponent_id"]])
            buy_in = await self._poker_buy_in(conn, ids)
            humans = [str(item["seat_key"]) for item in seats if item.get("user_id")]
            computers = [str(item["seat_key"]) for item in seats if item.get("kind") == "computer"]
            if not humans and not computers:
                human = str(row["player_side"])
                computers = ["black" if human == "white" else "white"]
                humans = [human]
            anchor = humans[0] if humans else computers[0]
            purses = self._fresh_purses(anchor, [item for item in computers if item != anchor], buy_in)
            for item in seats:
                if item.get("user_id"):
                    own = int(await balance(conn, item["user_id"]))
                    purses[str(item["seat_key"])] = min(own, buy_in)
            if humans and humans[0] not in {str(item.get("seat_key")) for item in seats}:
                purses[humans[0]] = buy_in
        if row["game_type"] in {"durak", "blackjack", "preferans"}:
            keys = [str(item) for item in order] if isinstance(order, list) and order else ["white", "black"]
            salon_purses = None
            if row["game_type"] == "blackjack":
                salon_purses = {}
                if seats:
                    for item in seats:
                        key = str(item["seat_key"])
                        if item.get("user_id"):
                            salon_purses[key] = min(int(await balance(conn, item["user_id"])), 200)
                        else:
                            salon_purses[key] = 200
                else:
                    human = str(row["player_side"])
                    other = "black" if human == "white" else "white"
                    salon_purses[human] = min(int(await balance(conn, row["user_id"])), 200)
                    salon_purses[other] = 200
            elif row["game_type"] == "preferans":
                payers = [item["user_id"] for item in seats if item.get("user_id")]
                if not payers and row["user_id"]:
                    payers = [row["user_id"]]
                price = preferans.stake_of(state.get("stake"))
                need = await self._preferans_buy_in(conn, payers, price)
                salon_purses = {key: need for key in keys}
            opened = module.deal(keys, str(row["variant"]), salon_purses)
            if row["game_type"] == "preferans":
                opened["stake"] = preferans.stake_of(state.get("stake"))
        elif isinstance(order, list) and len(order) > 2:
            opened = (
                poker.deal_table([str(item) for item in order], buy_in, purses)
                if row["game_type"] == "poker"
                else module.deal_table([str(item) for item in order])
            )
        else:
            opened = poker.deal(buy_in, purses) if row["game_type"] == "poker" else module.deal()
        self._mark_dealer(str(row["game_type"]), opened, {"engine_level": row["engine_level"]})
        if row["game_type"] in CHIP_GAMES:
            bag = opened.get("stacks") if row["game_type"] == "preferans" else opened.get("committed")
            if bag:
                for seat, amount in bag.items():
                    if not int(amount):
                        continue
                    payer = seat_user(dict(row), str(seat), seats or None)
                    if payer is not None:
                        await charge(conn, payer, int(amount), reason="ante", game_id=game_id)
                        self._forget_purse(payer)
            elif row["game_type"] != "preferans":
                for seat in ("white", "black"):
                    payer = seat_user(dict(row), seat)
                    if payer is not None:
                        await charge(conn, payer, poker.blind_for(seat), reason="ante", game_id=game_id)
                        self._forget_purse(payer)
        await games_repo.replace_deal(conn, game_id, module.dumps(opened))

    async def _require_adult(self, user_id: uuid.UUID, game_type: str = "poker") -> None:
        async with self.pool.acquire() as conn:
            reason = await adult_denial(conn, user_id, game_type)
        if reason:
            raise AppError(403, "adult_only", reason)

    async def _limit_engine(self, user: User) -> None:
        async with self.pool.acquire() as conn:
            allowed = await rate_limit.consume_rate(
                conn,
                bucket=f"engine:{user.id}",
                limit=self.settings.engine_rate_per_minute,
                window_seconds=60,
            )
        if not allowed:
            raise AppError(429, "rate_limited", "Слишком много запросов к движку. Подождите минуту.")

    async def _read_cache(
        self,
        game: dict[str, Any],
        position: str,
        engine_version: str,
        settings_hash: str,
    ) -> dict[str, Any] | None:
        engine_name = "stockfish" if game["game_type"] == "chess" else "boardmentor-checkers"
        async with self.pool.acquire() as conn:
            row = await analysis_repo.get_cached(
                conn,
                game_type=str(game["game_type"]),
                variant=str(game["variant"]),
                position_hash=_hash(position),
                engine_name=engine_name,
                engine_version=engine_version[:128],
                settings_hash=settings_hash,
            )
        if row is None:
            return None
        best = row["best_move"]
        if isinstance(best, str):
            best = json.loads(best)
        evaluation = row["evaluation"]
        if isinstance(evaluation, str):
            evaluation = json.loads(evaluation)
        return {
            "engine": engine_name,
            "nodes": row["nodes"] or 0,
            "path": best["path"],
            "promotion": best.get("promotion"),
            "lines": evaluation["lines"],
        }

    async def _write_cache(
        self,
        game: dict[str, Any],
        position: str,
        engine_version: str,
        settings_hash: str,
        result: dict[str, Any],
        depth: int,
    ) -> None:
        engine_name = "stockfish" if game["game_type"] == "chess" else "boardmentor-checkers"
        async with self.pool.acquire() as conn:
            await analysis_repo.put_cached(
                conn,
                game_type=str(game["game_type"]),
                variant=str(game["variant"]),
                position_hash=_hash(position),
                engine_name=engine_name,
                engine_version=engine_version[:128],
                settings_hash=settings_hash,
                best_move={"path": result["path"], "promotion": result.get("promotion")},
                evaluation={"lines": result["lines"]},
                principal_variation=result["lines"][0]["pv"],
                depth=depth,
                nodes=int(result["nodes"] or 0),
            )

    def _chess_cached_ok(self, board: chess.Board, cached: dict[str, Any]) -> bool:
        wanted = tuple(str(item) for item in cached["path"])
        return any(move.path == wanted for move in legal_records(board))

    def _checkers_cached_ok(self, position: Any, cached: dict[str, Any]) -> bool:
        return self._checkers_path_ok(position, [str(item) for item in cached["path"]])

    def _checkers_path_ok(self, position: Any, path: list[str]) -> bool:
        try:
            move_from_path(position, tuple(int(square) for square in path))
        except (IllegalMove, ValueError):
            return False
        return True

    async def _seated_game(self, conn: asyncpg.Connection, row: Any) -> dict[str, Any]:
        game = dict(row)
        game["table_seats"] = [dict(item) for item in await games_repo.list_seats(conn, row["id"])]
        return game

    def _seat(self, game: dict[str, Any], user: User) -> str | None:
        for item in game.get("table_seats") or []:
            if item.get("user_id") and str(item["user_id"]) == str(user.id):
                return str(item["seat_key"])
        opponent = game.get("opponent_id")
        return seat_of(
            str(user.id),
            str(game["user_id"]),
            str(opponent) if opponent else None,
            str(game["player_side"]),
        )

    def _names(self, game: dict[str, Any]) -> tuple[str, str]:
        creator = str(game.get("creator_name") or "Игрок")
        opponent = str(game.get("opponent_name") or "Соперник")
        if game["mode"] == "vs_computer":
            human, computer = creator, cpu_name(
                game["id"], other_side(str(game["player_side"])), [creator]
            )
            if game["player_side"] == "white":
                return human, computer
            return computer, human
        if game["mode"] == "online":
            if game["player_side"] == "white":
                return creator, opponent
            return opponent, creator
        return "Белые", "Чёрные"


def _uci_spec(text: str) -> tuple[list[str], str | None]:
    cleaned = text.strip().lower()
    if len(cleaned) not in {4, 5}:
        raise IllegalMove("Ход в списке должен быть в формате UCI, например e2e4.")
    promotion = cleaned[4] if len(cleaned) == 5 else None
    return [cleaned[0:2], cleaned[2:4]], promotion


def _apply_listed_chess(initial: str, specs: list[tuple[list[str], str | None]]) -> tuple[str, list[dict[str, Any]]]:
    board = parse_board(initial)
    stored: list[dict[str, Any]] = []
    for path, promotion in specs:
        before = board.fen()
        record = push_user_move(board, path, promotion)
        stored.append(
            {
                "notation": record.san,
                "before": before,
                "after": board.fen(),
                "payload": {
                    "uci": record.uci,
                    "path": list(record.path),
                    "promotion": record.promotion,
                    "by": "human",
                },
            }
        )
    return board.fen(), stored


def _summarize(rows: list[Any], user_id: uuid.UUID) -> dict[str, dict[str, int]]:
    summary = {
        "chess": {"total": 0, "active": 0, "wins": 0, "losses": 0, "draws": 0},
        "checkers": {"total": 0, "active": 0, "wins": 0, "losses": 0, "draws": 0},
        "go": {"total": 0, "active": 0, "wins": 0, "losses": 0, "draws": 0},
        "poker": {"total": 0, "active": 0, "wins": 0, "losses": 0, "draws": 0},
        "uno": {"total": 0, "active": 0, "wins": 0, "losses": 0, "draws": 0},
        "durak": {"total": 0, "active": 0, "wins": 0, "losses": 0, "draws": 0},
        "blackjack": {"total": 0, "active": 0, "wins": 0, "losses": 0, "draws": 0},
        "preferans": {"total": 0, "active": 0, "wins": 0, "losses": 0, "draws": 0},
    }
    for row in rows:
        bucket = summary.setdefault(
            row["game_type"],
            {"total": 0, "active": 0, "wins": 0, "losses": 0, "draws": 0},
        )
        bucket["total"] += 1
        if row["status"] in {"active", "waiting"}:
            bucket["active"] += 1
        seated = row["seat_key"] if row["seat_key"] else None
        mark = for_viewer(row, user_id)
        if mark is None and row["result"]:
            seat = str(seated) if seated else seat_of(
                str(user_id),
                str(row["user_id"]),
                str(row["opponent_id"]) if row["opponent_id"] else None,
                row["player_side"],
            )
            mark = "win" if seat and row["result"] == f"{seat}_win" else "loss"
            if row["result"] == "draw":
                mark = "draw"
        if mark == "win":
            bucket["wins"] += 1
        elif mark == "loss":
            bucket["losses"] += 1
        elif mark == "draw":
            bucket["draws"] += 1
    return summary
