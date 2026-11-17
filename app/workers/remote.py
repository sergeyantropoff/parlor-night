"""Веб отдаёт позицию в очередь Valkey. Считает её отдельный под с движками, не сам сайт."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any

import chess
from app.chess.engine import EngineLine
from app.config import Settings
from app.errors import AnalysisIncomplete
from app.workers.engines import EngineRuntime

logger = logging.getLogger(__name__)
JOBS = "engine:jobs"
VERSION_KEY = "engine:chess:version"


class RemoteStockfish:
    def __init__(self) -> None:
        self.version = "remote"
        self.available = False


class RemoteEngineRuntime:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.stockfish = RemoteStockfish()
        self.client: Any = None

    async def start(self) -> None:
        if not self.settings.valkey_url:
            logger.warning("удалённым движкам нужен Valkey")
            return
        from valkey.asyncio import Valkey

        client = Valkey.from_url(
            self.settings.valkey_url,
            decode_responses=True,
            socket_connect_timeout=1.5,
            socket_timeout=None,
        )
        for _attempt in range(30):
            try:
                await client.ping()
                break
            except Exception:
                await asyncio.sleep(1)
        else:
            await client.aclose()
            logger.warning("удалённым движкам нужен Valkey")
            return
        self.client = client
        self.stockfish.available = True
        version = await client.get(VERSION_KEY)
        if version:
            self.stockfish.version = str(version)

    async def shutdown(self) -> None:
        if self.client is not None:
            await self.client.aclose()
            self.client = None

    async def chess(
        self,
        board: chess.Board,
        *,
        time_s: float,
        depth: int,
        multipv: int,
        skill: int | None,
    ) -> list[EngineLine]:
        payload = await self._ask(
            "chess",
            {
                "fen": board.fen(),
                "time_s": time_s,
                "depth": depth,
                "multipv": multipv,
                "skill": skill,
            },
            timeout=time_s + 5,
        )
        lines = payload if isinstance(payload, list) else []
        return [unpack_line(item) for item in lines if isinstance(item, dict)]

    async def checkers(
        self,
        position: str,
        *,
        depth: int,
        time_ms: int,
        weights: dict[str, int],
        variety: bool,
        slack: int = 0,
    ) -> dict[str, object]:
        found = await self._ask(
            "checkers",
            {
                "position": position,
                "depth": depth,
                "time_ms": time_ms,
                "weights": weights,
                "variety": variety,
                "slack": slack,
            },
            timeout=time_ms / 1000 + 5,
        )
        if not isinstance(found, dict):
            raise AnalysisIncomplete("Шашечный движок не смог выбрать ход.")
        return found

    async def go(
        self,
        state: dict[str, object],
        color: str,
        level: int,
        time_ms: int,
    ) -> dict[str, object]:
        found = await self._ask(
            "go",
            {"state": state, "color": color, "level": level, "time_ms": time_ms},
            timeout=time_ms / 1000 + 5,
        )
        if not isinstance(found, dict):
            raise AnalysisIncomplete("Движок го не смог выбрать ход.")
        return found

    async def _ask(self, kind: str, payload: dict[str, object], *, timeout: float) -> object:
        if self.client is None:
            raise AnalysisIncomplete("Очередь движков недоступна.")
        if self.stockfish.version == "remote":
            version = await self.client.get(VERSION_KEY)
            if version:
                self.stockfish.version = str(version)
        job_id = str(uuid.uuid4())
        await self.client.lpush(JOBS, json.dumps({"id": job_id, "kind": kind, "payload": payload}))
        found = await self.client.blpop(f"engine:result:{job_id}", timeout=max(1, int(timeout)))
        if not found:
            raise AnalysisIncomplete("Движок не ответил.")
        data = json.loads(found[1])
        if not isinstance(data, dict) or not data.get("ok"):
            detail = data.get("error") if isinstance(data, dict) else None
            raise AnalysisIncomplete(str(detail or "Движок не смог выбрать ход."))
        return data.get("result")


def pack_line(line: EngineLine) -> dict[str, object]:
    return {
        "uci": line.uci,
        "san": line.san,
        "path": list(line.path),
        "promotion": line.promotion,
        "score_white": line.score_white,
        "mate": line.mate,
        "pv": list(line.pv),
        "depth": line.depth,
        "nodes": line.nodes,
    }


def unpack_line(data: dict[str, object]) -> EngineLine:
    path = data.get("path") or []
    pv = data.get("pv") or []
    mate = data.get("mate")
    return EngineLine(
        uci=str(data.get("uci") or ""),
        san=str(data.get("san") or ""),
        path=tuple(str(item) for item in path) if isinstance(path, list) else (),
        promotion=str(data["promotion"]) if data.get("promotion") else None,
        score_white=int(data.get("score_white") or 0),
        mate=int(mate) if isinstance(mate, int) else None,
        pv=tuple(str(item) for item in pv) if isinstance(pv, list) else (),
        depth=int(data.get("depth") or 0),
        nodes=int(data.get("nodes") or 0),
    )


async def run_job(runtime: EngineRuntime, kind: str, payload: dict[str, Any]) -> object:
    if kind == "chess":
        board = chess.Board(str(payload["fen"]))
        skill = payload.get("skill")
        lines = await runtime.chess(
            board,
            time_s=float(payload["time_s"]),
            depth=int(payload["depth"]),
            multipv=int(payload["multipv"]),
            skill=int(skill) if isinstance(skill, int) else None,
        )
        return [pack_line(line) for line in lines]
    if kind == "checkers":
        weights = payload.get("weights") or {}
        return await runtime.checkers(
            str(payload["position"]),
            depth=int(payload["depth"]),
            time_ms=int(payload["time_ms"]),
            weights={str(key): int(value) for key, value in weights.items()} if isinstance(weights, dict) else {},
            variety=bool(payload.get("variety")),
            slack=int(payload.get("slack") or 0),
        )
    if kind == "go":
        state = payload.get("state")
        if not isinstance(state, dict):
            raise AnalysisIncomplete("Движок го не смог выбрать ход.")
        return await runtime.go(state, str(payload["color"]), int(payload["level"]), int(payload["time_ms"]))
    raise AnalysisIncomplete("Движок не смог выбрать ход.")
