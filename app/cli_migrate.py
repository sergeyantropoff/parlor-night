"""Команда миграций."""

from __future__ import annotations

import asyncio
import sys

from app.config import get_settings
from app.db.migrate import apply_migrations, safe_db_error


def main() -> None:
    settings = get_settings()
    try:
        applied = asyncio.run(apply_migrations(settings.database_url))
    except Exception as exc:
        print(f"Не удалось применить миграции: {safe_db_error(exc)}", file=sys.stderr)
        raise SystemExit(1) from exc
    if applied:
        print("Применены миграции: " + ", ".join(applied))
    else:
        print("Миграции уже применены.")


if __name__ == "__main__":
    main()
