"""Какие карточные игры знает стол и где лежат их правила."""

from __future__ import annotations

from typing import Any

from app.cards import blackjack, domino, durak, poker, preferans, uno
from app.nardy import rules as nardy
from app.yahtzy import rules as yahtzy

CARD_GAMES = frozenset({"poker", "uno", "durak", "blackjack", "preferans", "domino", "nardy", "yahtzy"})
ADULT_GAMES = frozenset({"poker", "blackjack", "preferans"})
CHIP_GAMES = frozenset({"poker", "blackjack", "preferans"})

_MODULES = {
    "poker": poker,
    "uno": uno,
    "durak": durak,
    "blackjack": blackjack,
    "preferans": preferans,
    "domino": domino,
    "nardy": nardy,
    "yahtzy": yahtzy,
}


def card_module(game_type: str) -> Any:
    module = _MODULES.get(game_type)
    if module is None:
        raise KeyError(game_type)
    return module
