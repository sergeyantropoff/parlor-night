"""Под с движками. Забирает позиции из Valkey и возвращает ход."""

from __future__ import annotations

import asyncio
import json
import logging

from app.config import get_settings
from app.errors import AnalysisIncomplete
from app.logging_config import configure_logging
from app.workers.engines import EngineRuntime
from app.workers.remote import JOBS, VERSION_KEY, run_job

logger = logging.getLogger(__name__)


async def _serve() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    if not settings.valkey_url:
        raise SystemExit("Движкам нужен VALKEY_URL")
    from valkey.asyncio import Valkey

    client = Valkey.from_url(
        settings.valkey_url,
        decode_responses=True,
        socket_connect_timeout=1.5,
        socket_timeout=None,
    )
    for _ in range(60):
        try:
            await client.ping()
            break
        except Exception:
            await asyncio.sleep(1)
    else:
        raise SystemExit("Valkey для движков недоступен")
    runtime = EngineRuntime(settings)
    await runtime.start()
    await client.set(VERSION_KEY, runtime.stockfish.version)
    logger.info("engine worker ready version=%s", runtime.stockfish.version)
    try:
        while True:
            await client.set("engine:ready", "1", ex=15)
            found = await client.blpop(JOBS, timeout=5)
            if not found:
                continue
            try:
                job = json.loads(found[1])
            except json.JSONDecodeError:
                continue
            if not isinstance(job, dict):
                continue
            job_id = str(job.get("id") or "")
            kind = str(job.get("kind") or "")
            payload = job.get("payload") if isinstance(job.get("payload"), dict) else {}
            try:
                result = await run_job(runtime, kind, payload)
                reply = {"ok": True, "result": result}
            except AnalysisIncomplete as exc:
                reply = {"ok": False, "error": str(exc)}
            except Exception:
                logger.exception("engine job failed kind=%s", kind)
                reply = {"ok": False, "error": "Движок не смог выбрать ход."}
            if job_id:
                key = f"engine:result:{job_id}"
                await client.lpush(key, json.dumps(reply, ensure_ascii=False))
                await client.expire(key, 60)
    finally:
        await runtime.shutdown()
        await client.aclose()


def main() -> None:
    asyncio.run(_serve())


if __name__ == "__main__":
    main()
