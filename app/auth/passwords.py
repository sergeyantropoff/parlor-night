"""Хеширование паролей Argon2id. Исходные пароли не сохраняются."""

from __future__ import annotations

import asyncio

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from argon2.low_level import Type

from app.config import Settings


class Passwords:
    def __init__(self, settings: Settings) -> None:
        self._hasher = PasswordHasher(
            time_cost=settings.argon_time_cost,
            memory_cost=settings.argon_memory_cost,
            parallelism=settings.argon_parallelism,
            hash_len=32,
            type=Type.ID,
        )
        self._dummy = self._hasher.hash("dummy-password-not-used")
        self._slots = asyncio.Semaphore(2)

    def hash_password(self, password: str) -> str:
        return self._hasher.hash(password)

    async def verify_async(self, password_hash: str | None, password: str) -> bool:
        async with self._slots:
            return await asyncio.to_thread(self.verify, password_hash, password)

    def verify(self, password_hash: str | None, password: str) -> bool:
        material = password_hash or self._dummy
        try:
            return bool(self._hasher.verify(material, password)) and password_hash is not None
        except (VerifyMismatchError, InvalidHashError):
            return False
