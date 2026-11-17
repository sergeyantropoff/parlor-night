"""Создание администратора из окружения или из терминала. Пароль в код не зашит."""

from __future__ import annotations

import asyncio
import getpass
import os
import sys

import asyncpg

from app.auth.passwords import Passwords
from app.auth.validation import normalize_username, validate_password, validate_username
from app.config import get_settings
from app.db.pool import create_pool
from app.db.repositories.users import create_user, get_auth_record


def _credentials() -> tuple[str, str]:
    username = normalize_username(os.environ.get("ADMIN_USERNAME", ""))
    password = os.environ.get("ADMIN_PASSWORD", "")
    if username and password:
        return username, password
    if not sys.stdin.isatty():
        raise SystemExit("Задайте ADMIN_USERNAME и ADMIN_PASSWORD.")
    username = normalize_username(input("Логин администратора: "))
    password = getpass.getpass("Пароль: ")
    again = getpass.getpass("Повтор пароля: ")
    if password != again:
        raise SystemExit("Пароли не совпали.")
    return username, password


async def _create() -> None:
    settings = get_settings()
    username, password = _credentials()
    username_error = validate_username(username)
    password_error = validate_password(password, relaxed=settings.env == "local")
    if username_error or password_error:
        raise SystemExit(username_error or password_error)
    passwords = Passwords(settings)
    pool = await create_pool(settings.database_url)
    try:
        async with pool.acquire() as conn:
            existing = await get_auth_record(conn, username)
            if existing is not None:
                raise SystemExit("Пользователь уже существует.")
            try:
                await create_user(
                    conn,
                    username=username,
                    password_hash=passwords.hash_password(password),
                    role="admin",
                )
            except asyncpg.UniqueViolationError:
                raise SystemExit("Пользователь уже существует.") from None
    finally:
        await pool.close()
    print(f"Администратор {username} создан.")


def main() -> None:
    asyncio.run(_create())


if __name__ == "__main__":
    main()
