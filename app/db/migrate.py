"""Версионированные SQL-миграции."""

from __future__ import annotations

import re
from pathlib import Path

import asyncpg

MIGRATIONS = Path(__file__).parent / "migrations"
_DSN = re.compile(r"postgresql://[^\s]+")


def safe_db_error(exc: Exception) -> str:
    text = _DSN.sub("postgresql://***", str(exc))
    return f"{type(exc).__name__}: {text}"


async def apply_migrations(database_url: str) -> list[str]:
    conn = await asyncpg.connect(database_url)
    applied: list[str] = []
    try:
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version TEXT PRIMARY KEY,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        rows = await conn.fetch("SELECT version FROM schema_migrations")
        done = {row["version"] for row in rows}
        for path in sorted(MIGRATIONS.glob("*.sql")):
            if path.name in done:
                continue
            script = path.read_text(encoding="utf-8")
            async with conn.transaction():
                await conn.execute(script)
                await conn.execute(
                    "INSERT INTO schema_migrations (version) VALUES ($1)",
                    path.name,
                )
            applied.append(path.name)
    finally:
        await conn.close()
    return applied
