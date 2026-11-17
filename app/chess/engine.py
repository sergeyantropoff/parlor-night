"""Локальный UCI-движок. По умолчанию это Stockfish, без сети и без облака.

Лучший ход возвращается только если анализ завершился и ход легален.
"""

from __future__ import annotations

import asyncio
import logging
import random
import shutil
from dataclasses import dataclass
from pathlib import Path

import chess
import chess.engine
from app.chess.rules import legal_records
from app.config import Settings
from app.errors import AnalysisIncomplete, EngineUnavailable

logger = logging.getLogger(__name__)

# Глубина, потолок времени, Skill Level, число вариантов и допуск ошибки в сантипешках.
# Новичок видит только свой ход и выбирает среди посредственных. Мастер берёт лучший глубокий.
PLAY: dict[int, tuple[float, int, int, int, int]] = {
    1: (0.25, 1, 0, 30, 280),
    2: (0.40, 2, 2, 8, 110),
    3: (0.70, 5, 8, 3, 30),
    4: (1.20, 12, 16, 1, 0),
    5: (2.40, 20, 20, 1, 0),
}


@dataclass(frozen=True, slots=True)
class EngineLine:
    uci: str
    san: str
    path: tuple[str, str]
    promotion: str | None
    score_white: int
    mate: int | None
    pv: tuple[str, ...]
    depth: int
    nodes: int


class StockfishPool:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.path: str | None = None
        self.version = "unavailable"
        self.available = False
        self._queue: asyncio.Queue[chess.engine.UciProtocol] = asyncio.Queue()
        self._protocols: list[chess.engine.UciProtocol] = []

    def locate(self) -> str | None:
        candidates = [
            self.settings.chess_engine_path,
            "stockfish",
            "/usr/games/stockfish",
            "/usr/bin/stockfish",
            "/opt/homebrew/bin/stockfish",
        ]
        for candidate in candidates:
            if not candidate:
                continue
            direct = Path(candidate)
            if direct.is_file() and direct.stat().st_mode & 0o111:
                return str(direct)
            found = shutil.which(candidate)
            if found:
                return found
        return None

    async def start(self) -> None:
        self.path = self.locate()
        if self.path is None:
            logger.warning("chess engine binary is missing")
            return
        try:
            for _ in range(self.settings.chess_engine_pool_size):
                protocol = await self._spawn()
                self._protocols.append(protocol)
                await self._queue.put(protocol)
        except (OSError, chess.engine.EngineError):
            logger.warning("chess engine failed to start")
            await self.shutdown()
            return
        self.available = True

    async def _spawn(self) -> chess.engine.UciProtocol:
        assert self.path is not None
        _transport, protocol = await chess.engine.popen_uci(self.path)
        self.version = str(protocol.id.get("name") or "stockfish")
        try:
            await protocol.configure(
                {
                    "Threads": self.settings.chess_engine_threads,
                    "Hash": self.settings.chess_engine_hash_mb,
                }
            )
        except chess.engine.EngineError:
            logger.info("chess engine ignored unsupported options")
        return protocol

    async def shutdown(self) -> None:
        self.available = False
        while not self._queue.empty():
            self._queue.get_nowait()
        for protocol in self._protocols:
            try:
                await protocol.quit()
            except chess.engine.EngineError:
                continue
        self._protocols.clear()

    async def analyse(
        self,
        board: chess.Board,
        *,
        time_s: float,
        depth: int,
        multipv: int,
        skill: int | None,
    ) -> list[EngineLine]:
        if not self.available:
            raise EngineUnavailable(
                "Шахматный движок Stockfish не найден. Проверьте установку и CHESS_ENGINE_PATH."
            )
        protocol = await self._queue.get()
        failed = False
        try:
            await self._set_skill(protocol, 20 if skill is None else skill)
            limit = chess.engine.Limit(time=max(time_s, 0.05), depth=max(depth, 1))
            raw = await asyncio.wait_for(
                protocol.analyse(board, limit, multipv=max(1, multipv)),
                timeout=time_s + 3,
            )
            lines = self._parse(board, raw if isinstance(raw, list) else [raw])
            if not lines:
                raise AnalysisIncomplete("Движок не вернул ход. Повторите запрос.")
            return lines
        except (TimeoutError, chess.engine.EngineError) as exc:
            failed = True
            raise AnalysisIncomplete("Анализ не завершился. Ход движка не выбран.") from exc
        finally:
            if failed:
                await self._replace(protocol)
            else:
                await self._queue.put(protocol)

    async def _replace(self, protocol: chess.engine.UciProtocol) -> None:
        try:
            await protocol.quit()
        except chess.engine.EngineError:
            pass
        if protocol in self._protocols:
            self._protocols.remove(protocol)
        try:
            fresh = await self._spawn()
        except (OSError, chess.engine.EngineError):
            self.available = bool(self._protocols)
            return
        self._protocols.append(fresh)
        await self._queue.put(fresh)

    async def _set_skill(self, protocol: chess.engine.UciProtocol, skill: int) -> None:
        try:
            await protocol.configure({"Skill Level": max(0, min(20, skill))})
        except chess.engine.EngineError:
            return

    def _parse(self, board: chess.Board, infos: list[dict[str, object]]) -> list[EngineLine]:
        legal = {move.uci: move for move in legal_records(board)}
        lines: list[EngineLine] = []
        for info in infos:
            pv = info.get("pv") or []
            if not isinstance(pv, list) or not pv:
                continue
            first = pv[0]
            uci = first.uci() if isinstance(first, chess.Move) else str(first)
            record = legal.get(uci)
            if record is None:
                continue
            score = info.get("score")
            mate = None
            cp = 0
            if isinstance(score, chess.engine.PovScore):
                white = score.white()
                mate = white.mate()
                cp = white.score(mate_score=100_000) or 0
            pv_uci = tuple(move.uci() if isinstance(move, chess.Move) else str(move) for move in pv)
            depth = int(info.get("depth") or 0)
            nodes = int(info.get("nodes") or 0)
            lines.append(
                EngineLine(
                    uci=record.uci,
                    san=record.san,
                    path=record.path,
                    promotion=record.promotion,
                    score_white=int(cp),
                    mate=mate,
                    pv=pv_uci,
                    depth=depth,
                    nodes=nodes,
                )
            )
        return lines


def level_budget(level: int, requested_ms: int, maximum_ms: int) -> tuple[float, int, int, int, int]:
    bounded = max(1, min(5, level))
    time_cap, depth, skill, multipv, slack_cp = PLAY[bounded]
    millis = min(requested_ms, maximum_ms, int(time_cap * 1000))
    return max(millis / 1000, 0.05), depth, skill, multipv, slack_cp


def choose_line(
    lines: list[EngineLine],
    *,
    white_to_move: bool,
    slack_cp: int,
    rng: random.Random | None = None,
) -> EngineLine:
    """Слабый уровень берёт не лучший ход, а случайный из близких по оценке."""

    if not lines:
        raise AnalysisIncomplete("Движок не вернул ход. Повторите запрос.")
    if slack_cp <= 0 or len(lines) == 1:
        return lines[0]

    def side_score(line: EngineLine) -> int:
        return line.score_white if white_to_move else -line.score_white

    best = max(side_score(line) for line in lines)
    pool = [line for line in lines if best - side_score(line) <= slack_cp]
    return (rng or random).choice(pool or lines)
