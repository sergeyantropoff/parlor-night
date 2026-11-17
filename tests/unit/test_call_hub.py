from __future__ import annotations

import json

import pytest

from app.realtime import TableHub


class Sock:
    def __init__(self) -> None:
        self.sent: list[dict[str, object]] = []

    async def send_json(self, message: dict[str, object]) -> None:
        self.sent.append(message)


class MemoryBus:
    def __init__(self) -> None:
        self.sets: dict[str, set[str]] = {}
        self.kv: dict[str, str] = {}
        self.hubs: list[TableHub] = []

    async def publish(self, _channel: str, data: str) -> int:
        payload = json.loads(data)
        for hub in self.hubs:
            await hub._deliver(payload)
        return len(self.hubs)

    async def sadd(self, key: str, *members: str) -> int:
        bucket = self.sets.setdefault(key, set())
        bucket.update(str(member) for member in members)
        return len(members)

    async def srem(self, key: str, *members: str) -> None:
        bucket = self.sets.setdefault(key, set())
        for member in members:
            bucket.discard(str(member))

    async def smembers(self, key: str) -> set[str]:
        return set(self.sets.get(key, set()))

    async def sismember(self, key: str, member: str) -> bool:
        return str(member) in self.sets.get(key, set())

    async def scard(self, key: str) -> int:
        return len(self.sets.get(key, set()))

    async def set(self, key: str, value: str, ex: int | None = None, nx: bool = False) -> bool | None:
        if nx and key in self.kv:
            return None
        self.kv[key] = value
        return True

    async def exists(self, key: str) -> int:
        return 1 if key in self.kv else 0

    async def delete(self, *keys: str) -> None:
        for key in keys:
            self.kv.pop(key, None)


def _pair() -> tuple[TableHub, TableHub, MemoryBus]:
    bus = MemoryBus()
    left, right = TableHub(), TableHub()
    left.client = bus
    right.client = bus
    bus.hubs = [left, right]
    return left, right, bus


@pytest.mark.asyncio
async def test_signal_reaches_the_player_on_the_other_process() -> None:
    left, right, _bus = _pair()
    ann, pavel = Sock(), Sock()
    assert await left.connect("game", "ann", ann)
    assert await right.connect("game", "pavel", pavel)
    assert {"type": "peer-joined", "id": "pavel"} in ann.sent
    await left.relay("game", "ann", {"to": "pavel", "data": {"kind": "offer"}})
    assert pavel.sent[-1] == {"type": "signal", "from": "ann", "data": {"kind": "offer"}}


@pytest.mark.asyncio
async def test_seventh_person_does_not_enter_the_room() -> None:
    left, _right, _bus = _pair()
    for index in range(6):
        assert await left.connect("game", f"user-{index}", Sock())
    assert await left.connect("game", "late", Sock()) is False


@pytest.mark.asyncio
async def test_missing_heartbeat_tells_the_table_the_player_left() -> None:
    left, _right, bus = _pair()
    ann = Sock()
    assert await left.connect("game", "ann", ann)
    assert await left.connect("game", "pavel", Sock())
    await bus.delete("call:beat:game:pavel")
    await left._sweep()
    assert {"type": "peer-left", "id": "pavel"} in ann.sent
    assert "pavel" not in bus.sets["call:room:game"]
