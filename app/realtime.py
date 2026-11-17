"""Сигнализация видео и голоса. Потоки идут между игроками, сервер только знакомит."""

from __future__ import annotations

import asyncio
import hashlib
import json
import uuid
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


class TableHub:
    def __init__(self) -> None:
        self.rooms: dict[str, dict[str, WebSocket]] = {}
        self.lock = asyncio.Lock()

    async def connect(self, game_id: str, user_id: str, socket: WebSocket) -> bool:
        async with self.lock:
            room = self.rooms.setdefault(game_id, {})
            if user_id not in room and len(room) >= 6:
                return False
            room[user_id] = socket
            peers = [item for item in room if item != user_id]
        await self._send(game_id, user_id, {"type": "peers", "ids": peers})
        await self.broadcast(game_id, user_id, {"type": "peer-joined", "id": user_id})
        return True

    async def disconnect(self, game_id: str, user_id: str) -> None:
        async with self.lock:
            room = self.rooms.get(game_id, {})
            room.pop(user_id, None)
            if not room:
                self.rooms.pop(game_id, None)
        await self.broadcast(game_id, user_id, {"type": "peer-left", "id": user_id})

    async def relay(self, game_id: str, sender: str, payload: dict[str, object]) -> None:
        target = str(payload.get("to") or "")
        async with self.lock:
            socket = self.rooms.get(game_id, {}).get(target)
        if socket is None:
            return
        try:
            await socket.send_json({"type": "signal", "from": sender, "data": payload.get("data")})
        except Exception:
            return

    async def broadcast(self, game_id: str, sender: str, message: dict[str, object]) -> None:
        async with self.lock:
            sockets = [item for key, item in self.rooms.get(game_id, {}).items() if key != sender]
        for socket in sockets:
            try:
                await socket.send_json(message)
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
        await hub.disconnect(key, user_id)
