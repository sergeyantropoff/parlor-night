"""Быстрые счётчики. Valkey держит их для всех процессов, без него работает память процесса."""

from __future__ import annotations

import time
from typing import Any


class Gate:
    def __init__(self) -> None:
        self.client: Any = None
        self._windows: dict[str, tuple[float, int, int]] = {}
        self._once: dict[str, float] = {}
        self.chips: dict[str, int] = {}

    async def start(self, url: str) -> None:
        if not url:
            return
        from valkey.asyncio import Valkey

        client = Valkey.from_url(url, decode_responses=True, socket_connect_timeout=1.5)
        await client.ping()
        self.client = client

    async def close(self) -> None:
        if self.client is not None:
            await self.client.aclose()
            self.client = None

    async def healthy(self) -> str:
        if self.client is None:
            return "memory"
        try:
            await self.client.ping()
        except Exception:
            return "unavailable"
        return "ok"

    async def blocked(self, bucket: str, limit: int) -> bool:
        count = await self._read(bucket)
        return count >= limit

    async def add(self, bucket: str, window_seconds: int) -> None:
        await self._bump(bucket, window_seconds)

    async def allow(self, bucket: str, limit: int, window_seconds: int) -> bool:
        count = await self._bump(bucket, window_seconds)
        return count <= limit

    async def once(self, bucket: str, window_seconds: int) -> bool:
        now = time.monotonic()
        if self.client is not None:
            try:
                stored = await self.client.set(f"once:{bucket}", "1", ex=window_seconds, nx=True)
                return bool(stored)
            except Exception:
                self.client = None
        previous = self._once.get(bucket, 0)
        if now - previous < window_seconds:
            return False
        self._once[bucket] = now
        return True

    async def clear_login_buckets(self) -> None:
        self._windows = {key: value for key, value in self._windows.items() if not key.startswith("login:")}
        if self.client is None:
            return
        try:
            cursor = 0
            while True:
                cursor, keys = await self.client.scan(cursor=cursor, match="rl:login:*", count=200)
                if keys:
                    await self.client.delete(*keys)
                if int(cursor) == 0:
                    break
        except Exception:
            self.client = None

    def remember_chips(self, user_id: str, amount: int) -> None:
        self.chips[user_id] = amount

    async def _read(self, bucket: str) -> int:
        if self.client is not None:
            try:
                value = await self.client.get(f"rl:{bucket}")
                return int(value or 0)
            except Exception:
                self.client = None
        started, count, window = self._windows.get(bucket, (0.0, 0, 1))
        if time.monotonic() - started >= window:
            return 0
        return count

    async def _bump(self, bucket: str, window_seconds: int) -> int:
        if self.client is not None:
            try:
                key = f"rl:{bucket}"
                count = int(await self.client.incr(key))
                if count == 1:
                    await self.client.expire(key, window_seconds)
                return count
            except Exception:
                self.client = None
        now = time.monotonic()
        started, count, window = self._windows.get(bucket, (now, 0, window_seconds))
        if now - started >= window:
            started, count = now, 0
        count += 1
        self._windows[bucket] = (started, count, window_seconds)
        return count
