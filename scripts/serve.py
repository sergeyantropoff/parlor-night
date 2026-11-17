"""Применение миграций и запуск uvicorn."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from app.config import get_settings
from app.db.migrate import apply_migrations, safe_db_error


async def _migrate() -> None:
    settings = get_settings()
    last = "база недоступна"
    for _ in range(30):
        try:
            applied = await apply_migrations(settings.database_url)
        except Exception as exc:
            last = safe_db_error(exc)
            await asyncio.sleep(1)
            continue
        if applied:
            print("Применены миграции: " + ", ".join(applied), flush=True)
        return
    print(f"Не удалось применить миграции: {last}", file=sys.stderr)
    raise SystemExit(1)


def main() -> None:
    asyncio.run(_migrate())
    settings = get_settings()
    args = [
        sys.executable,
        "-m",
        "uvicorn",
        "app.main:app",
        "--host",
        "0.0.0.0",
        "--port",
        "8000",
        "--no-access-log",
        "--timeout-graceful-shutdown",
        "15",
        "--limit-concurrency",
        "200",
        "--timeout-keep-alive",
        "5",
        "--h11-max-incomplete-event-size",
        "16384",
    ]
    if settings.env == "local":
        app_dir = Path(__file__).resolve().parent.parent / "app"
        args.extend(["--reload", "--reload-dir", str(app_dir)])
    else:
        args.extend(["--workers", "1"])
    if settings.trust_proxy:
        args.extend(["--proxy-headers", "--forwarded-allow-ips", settings.forwarded_allow_ips])
    os.execv(sys.executable, args)


if __name__ == "__main__":
    main()
