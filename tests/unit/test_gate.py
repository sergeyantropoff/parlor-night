from app.gate import Gate


async def test_window_blocks_after_the_limit() -> None:
    gate = Gate()
    assert await gate.allow("login", 2, 60)
    assert await gate.allow("login", 2, 60)
    assert not await gate.allow("login", 2, 60)
    assert await gate.blocked("login", 2)


async def test_once_is_quiet_until_the_window_passes() -> None:
    gate = Gate()
    assert await gate.once("seen", 60)
    assert not await gate.once("seen", 60)
