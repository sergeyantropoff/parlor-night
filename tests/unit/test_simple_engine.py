from __future__ import annotations

import pytest

from app.checkers.serialization import INITIAL_RCP
from app.checkers.simple import play_simple, ready


@pytest.mark.skipif(not ready(), reason="py-draughts не установлен")
def test_simple_engine_plays_a_legal_opening() -> None:
    found = play_simple(INITIAL_RCP, 2, 400)
    assert found is not None
    assert found["engine"] == "py-draughts SimpleEngine"
    path = tuple(int(square) for square in found["path"])
    assert path in {
        (21, 17),
        (22, 17),
        (22, 18),
        (23, 18),
        (23, 19),
        (24, 19),
        (24, 20),
    }
