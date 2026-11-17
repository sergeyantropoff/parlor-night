"""Общая проверка логина и пароля для сайта и мобильного API."""

from __future__ import annotations

from starlette.requests import Request

from app.db.repositories import rate_limit, users
from app.db.repositories.users import UserRecord
from app.errors import AppError
from app.site_policy import current


async def authenticate(request: Request, username: str, password: str) -> UserRecord:
    pool = request.app.state.pool
    policy = await current(request)
    name = username or "unknown"
    ip_address = request.state.client_ip
    gate = request.app.state.gate
    user_bucket = f"login:user:{name}"
    ip_bucket = f"login:ip:{ip_address}"
    limit = policy.login_failures
    window = policy.login_window_seconds
    async with pool.acquire() as conn:
        blocked = await gate.blocked(user_bucket, limit) or await gate.blocked(ip_bucket, limit * 4)
        if not blocked:
            by_name = await rate_limit.login_failures(
                conn, username=name, ip_address=None, window_seconds=window
            )
            by_ip = await rate_limit.login_failures(
                conn, username=None, ip_address=ip_address, window_seconds=window
            )
            blocked = by_name >= limit or by_ip >= limit * 4
        record = await users.get_auth_record(conn, username) if username and not blocked else None
    if blocked:
        raise AppError(429, "rate_limited", "Слишком много попыток входа. Подождите и попробуйте снова.")
    digest = record.password_hash if record else None
    password_ok = record is not None and await request.app.state.passwords.verify_async(digest, password)
    active = record is not None and record.is_active
    valid = password_ok and active
    async with pool.acquire() as conn:
        await rate_limit.record_login(conn, username=name, ip_address=ip_address, success=valid)
        if not valid:
            await gate.add(user_bucket, window)
            await gate.add(ip_bucket, window)
    if password_ok and not active:
        raise AppError(403, "account_disabled", "Учётная запись заблокирована.")
    if not valid or record is None:
        raise AppError(401, "unauthorized", "Неверный логин или пароль.")
    return record
