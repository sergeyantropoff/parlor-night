"""Сигнализация видео и голоса. Потоки идут между игроками, сервер только знакомит.

Сокеты живут в процессе, который принял браузер. Список участников и сами сигналы
проходят через Valkey, поэтому игроки одного стола слышат друг друга с разных подов.
Без Valkey комната остаётся в памяти этого процесса.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import uuid
from typing import Any
from urllib.parse import urlparse

from fastapi import APIRouter, WebSocket
from starlette.websockets import WebSocketDisconnect

from app.cards.registry import ADULT_GAMES
from app.db.repositories import api_access
from app.db.repositories import games as games_repo
from app.db.repositories import sessions as session_repo
from app.site_policy import current_app
from app.wallet import is_adult

router = APIRouter()
logger = logging.getLogger(__name__)
_ROOM_LIMIT = 6
_BEAT_SECONDS = 30


class TableHub:
    def __init__(self) -> None:
        self.rooms: dict[str, dict[str, WebSocket]] = {}
        self.lock = asyncio.Lock()
        self.client: Any = None
        self.bus: Any = None
        self._tasks: list[asyncio.Task[None]] = []

    async def start(self, url: str) -> None:
        if not url:
            return
        from valkey.asyncio import Valkey

        last: Exception | None = None
        for _attempt in range(30):
            client = Valkey.from_url(url, decode_responses=True, socket_connect_timeout=1.5, socket_timeout=None)
            bus = Valkey.from_url(url, decode_responses=True, socket_connect_timeout=1.5, socket_timeout=None)
            try:
                await client.ping()
            except Exception as exc:
                last = exc
                await client.aclose()
                await bus.aclose()
                await asyncio.sleep(1)
                continue
            self.client = client
            self.bus = bus
            self._tasks = [
                asyncio.create_task(self._listen()),
                asyncio.create_task(self._pulse()),
            ]
            return
        if last is not None:
            raise last

    async def close(self) -> None:
        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._tasks = []
        for client in (self.bus, self.client):
            if client is not None:
                await client.aclose()
        self.bus = None
        self.client = None

    async def connect(self, game_id: str, user_id: str, socket: WebSocket) -> bool:
        if self.client is not None and not await self._admit(game_id, user_id):
            return False
        async with self.lock:
            room = self.rooms.setdefault(game_id, {})
            if self.client is None and user_id not in room and len(room) >= _ROOM_LIMIT:
                return False
            room[user_id] = socket
            local_peers = [item for item in room if item != user_id]
        peers = await self._live_peers(game_id, user_id) if self.client is not None else local_peers
        await self._send(game_id, user_id, {"type": "peers", "ids": peers})
        await self._announce({"kind": "joined", "game_id": game_id, "user_id": user_id})
        return True

    async def disconnect(self, game_id: str, user_id: str, socket: WebSocket | None = None) -> None:
        async with self.lock:
            room = self.rooms.get(game_id, {})
            current = room.get(user_id)
            if socket is not None and current is not None and current is not socket:
                return
            room.pop(user_id, None)
            if not room:
                self.rooms.pop(game_id, None)
        if self.client is not None:
            await self.client.srem(f"call:room:{game_id}", user_id)
            await self.client.delete(f"call:beat:{game_id}:{user_id}")
            if not await self.client.smembers(f"call:room:{game_id}"):
                await self.client.srem("call:rooms", game_id)
        await self._announce({"kind": "left", "game_id": game_id, "user_id": user_id})

    async def relay(self, game_id: str, sender: str, payload: dict[str, object]) -> None:
        target = str(payload.get("to") or "")
        if not target:
            return
        await self._announce(
            {
                "kind": "signal",
                "game_id": game_id,
                "user_id": sender,
                "target": target,
                "data": payload.get("data"),
            }
        )

    async def _admit(self, game_id: str, user_id: str) -> bool:
        room = f"call:room:{game_id}"
        if await self.client.sismember(room, user_id):
            await self.client.set(f"call:beat:{game_id}:{user_id}", "1", ex=_BEAT_SECONDS)
            await self.client.sadd("call:rooms", game_id)
            return True
        if int(await self.client.scard(room)) >= _ROOM_LIMIT:
            return False
        await self.client.sadd(room, user_id)
        await self.client.sadd("call:rooms", game_id)
        await self.client.set(f"call:beat:{game_id}:{user_id}", "1", ex=_BEAT_SECONDS)
        return True

    async def _live_peers(self, game_id: str, user_id: str) -> list[str]:
        members = await self.client.smembers(f"call:room:{game_id}")
        live: list[str] = []
        for member in members:
            if str(member) == user_id:
                continue
            if await self.client.exists(f"call:beat:{game_id}:{member}"):
                live.append(str(member))
        return live

    async def _announce(self, message: dict[str, object]) -> None:
        if self.client is None:
            await self._deliver(message)
            return
        try:
            await self.client.publish("call:fanout", json.dumps(message, ensure_ascii=False))
        except Exception:
            logger.warning("не удалось разослать сигнал созвона")
            await self._deliver(message)

    async def _deliver(self, message: dict[str, object]) -> None:
        kind = str(message.get("kind") or "")
        game_id = str(message.get("game_id") or "")
        user_id = str(message.get("user_id") or "")
        if kind == "signal":
            await self._send(
                game_id,
                str(message.get("target") or ""),
                {"type": "signal", "from": user_id, "data": message.get("data")},
            )
            return
        if kind == "joined":
            body: dict[str, object] = {"type": "peer-joined", "id": user_id}
        elif kind == "left":
            body = {"type": "peer-left", "id": user_id}
        else:
            return
        async with self.lock:
            sockets = [item for key, item in self.rooms.get(game_id, {}).items() if key != user_id]
        for socket in sockets:
            try:
                await socket.send_json(body)
            except Exception:
                continue

    async def _send(self, game_id: str, user_id: str, message: dict[str, object]) -> None:
        async with self.lock:
            socket = self.rooms.get(game_id, {}).get(user_id)
        if socket is None:
            return
        try:
            await socket.send_json(message)
        except Exception:
            return

    async def _listen(self) -> None:
        if self.bus is None:
            return
        pubsub = self.bus.pubsub()
        await pubsub.subscribe("call:fanout")
        try:
            async for incoming in pubsub.listen():
                if incoming.get("type") != "message":
                    continue
                try:
                    payload = json.loads(incoming["data"])
                except (TypeError, json.JSONDecodeError):
                    continue
                if isinstance(payload, dict):
                    await self._deliver(payload)
        except asyncio.CancelledError:
            await pubsub.aclose()
            raise

    async def _pulse(self) -> None:
        while True:
            try:
                await asyncio.sleep(10)
                await self._refresh_beats()
                await self._sweep()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.warning("не удалось обновить пульс созвона")

    async def _refresh_beats(self) -> None:
        if self.client is None:
            return
        async with self.lock:
            pairs = [(game_id, user_id) for game_id, room in self.rooms.items() for user_id in room]
        for game_id, user_id in pairs:
            await self.client.set(f"call:beat:{game_id}:{user_id}", "1", ex=_BEAT_SECONDS)

    async def _sweep(self) -> None:
        if self.client is None:
            return
        locked = await self.client.set("call:sweep", "1", nx=True, ex=12)
        if not locked:
            return
        games = await self.client.smembers("call:rooms")
        for game_id in list(games):
            members = await self.client.smembers(f"call:room:{game_id}")
            if not members:
                await self.client.srem("call:rooms", game_id)
                continue
            for user_id in list(members):
                if await self.client.exists(f"call:beat:{game_id}:{user_id}"):
                    continue
                await self.client.srem(f"call:room:{game_id}", user_id)
                await self._announce({"kind": "left", "game_id": str(game_id), "user_id": str(user_id)})


async def _viewer(socket: WebSocket) -> tuple[object | None, bool]:
    header = socket.headers.get("authorization", "")
    pool = getattr(socket.app.state, "pool", None)
    if header.lower().startswith("bearer "):
        token = header.split(" ", 1)[1].strip()
        if not token or pool is None:
            return None, True
        digest = hashlib.sha256(token.encode()).hexdigest()
        async with pool.acquire() as conn:
            found = await api_access.find_access(conn, digest)
        if found is None:
            return None, True
        return found.user, True
    token = socket.cookies.get("bm_session")
    if not token or pool is None:
        return None, False
    digest = hashlib.sha256(token.encode()).hexdigest()
    async with pool.acquire() as conn:
        found_session = await session_repo.find_session(conn, digest)
    if found_session is None:
        return None, False
    return found_session.user, False


def _same_origin(socket: WebSocket) -> bool:
    origin = socket.headers.get("origin", "")
    host = socket.headers.get("host", "")
    if not origin or not host:
        return False
    return urlparse(origin).netloc == host


@router.websocket("/ws/tables/{game_id}")
async def table_socket(socket: WebSocket, game_id: uuid.UUID) -> None:
    await socket.accept()
    client = socket.client.host if socket.client is not None else "unknown"
    user, bearer = await _viewer(socket)
    if (not bearer and not _same_origin(socket)) or not await socket.app.state.gate.allow(f"ws:{client}", 30, 60):
        await socket.close(code=4403)
        return
    if user is None:
        await socket.close(code=4401)
        return
    if (await current_app(socket.app)).maintenance and not user.is_admin:
        await socket.close(code=4403)
        return
    pool = socket.app.state.pool
    async with pool.acquire() as conn:
        row = await games_repo.get_visible(conn, game_id, user.id)
        if row is None:
            await socket.close(code=4404)
            return
        if row["game_type"] in ADULT_GAMES and not await is_adult(conn, user.id):
            await socket.close(code=4403)
            return
        seated = row["user_id"] == user.id or row["opponent_id"] == user.id
        if not seated:
            seated = (
                await conn.fetchval(
                    """
                    SELECT 1 FROM game_seats
                    WHERE game_id = $1 AND user_id = $2 AND kind = 'human'
                    """,
                    game_id,
                    user.id,
                )
                is not None
            )
    if not seated:
        await socket.send_json({"type": "watch"})
        await socket.close(code=1000)
        return
    hub: TableHub = socket.app.state.hub
    user_id = str(user.id)
    key = str(game_id)
    if not await hub.connect(key, user_id, socket):
        await socket.send_json({"type": "full"})
        await socket.close(code=4408)
        return
    try:
        while True:
            incoming = await socket.receive()
            if incoming["type"] == "websocket.disconnect":
                break
            text = incoming.get("text")
            if not isinstance(text, str) or len(text) > 8192:
                await socket.close(code=1009)
                break
            payload = json.loads(text)
            if isinstance(payload, dict) and payload.get("type") == "signal":
                await hub.relay(key, user_id, payload)
    except (WebSocketDisconnect, RuntimeError, json.JSONDecodeError, ValueError):
        pass
    finally:
        await hub.disconnect(key, user_id, socket)
