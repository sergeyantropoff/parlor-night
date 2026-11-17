"""Пулы движков. Шахматный процесс — локальный UCI, шашечный поиск — отдельные процессы."""

from __future__ import annotations

import asyncio
import logging
import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor

import chess
from app.checkers.engine import search_job
from app.chess.engine import EngineLine, StockfishPool
from app.config import Settings
from app.errors import AnalysisIncomplete
from app.go.engine import search_job as go_search_job

logger = logging.getLogger(__name__)

try:
    mp.set_start_method("spawn")
except RuntimeError:
    pass


class EngineRuntime:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.stockfish = StockfishPool(settings)
        self.semaphore = asyncio.Semaphore(settings.engine_max_concurrent)
        self.pool: ProcessPoolExecutor | None = None

    async def start(self) -> None:
        await self.stockfish.start()
        self.pool = ProcessPoolExecutor(max_workers=self.settings.checkers_workers)

    async def shutdown(self) -> None:
        await self.stockfish.shutdown()
        if self.pool is None:
            return
        processes = list(getattr(self.pool, "_processes", {}).values())
        self.pool.shutdown(wait=False, cancel_futures=True)
        for process in processes:
            process.terminate()
        self.pool = None

    async def chess(
        self,
        board: chess.Board,
        *,
        time_s: float,
        depth: int,
        multipv: int,
        skill: int | None,
    ) -> list[EngineLine]:
        async with self.semaphore:
            return await self.stockfish.analyse(
                board,
                time_s=time_s,
                depth=depth,
                multipv=multipv,
                skill=skill,
            )

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
        if self.pool is None:
            raise AnalysisIncomplete("Шашечный движок не запущен.")
        async with self.semaphore:
            loop = asyncio.get_running_loop()
            try:
                return await asyncio.wait_for(
                    loop.run_in_executor(
                        self.pool,
                        search_job,
                        position,
                        depth,
                        time_ms,
                        weights,
                        variety,
                        slack,
                    ),
                    timeout=time_ms / 1000 + 2,
                )
            except TimeoutError as exc:
                logger.warning("checkers search timed out")
                raise AnalysisIncomplete("Анализ шашек не завершился. Ход не выбран.") from exc

    async def go(
        self,
        state: dict[str, object],
        color: str,
        level: int,
        time_ms: int,
    ) -> dict[str, object]:
        if self.pool is None:
            return go_search_job(state, color, level, time_ms)
        async with self.semaphore:
            loop = asyncio.get_running_loop()
            try:
                return await asyncio.wait_for(
                    loop.run_in_executor(self.pool, go_search_job, state, color, level, time_ms),
                    timeout=time_ms / 1000 + 2,
                )
            except TimeoutError as exc:
                logger.warning("go search timed out")
                raise AnalysisIncomplete("Анализ го не завершился. Ход не выбран.") from exc
