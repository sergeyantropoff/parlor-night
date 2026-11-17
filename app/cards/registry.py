"""Какие карточные игры знает стол и где лежат их правила."""

from __future__ import annotations

from typing import Any

from app.cards import blackjack, durak, poker, preferans, uno

CARD_GAMES = frozenset({"poker", "uno", "durak", "blackjack", "preferans"})
ADULT_GAMES = frozenset({"poker", "blackjack", "preferans"})
CHIP_GAMES = frozenset({"poker", "blackjack", "preferans"})

_MODULES = {
    "poker": poker,
    "uno": uno,
    "durak": durak,
    "blackjack": blackjack,
    "preferans": preferans,
}


def card_module(game_type: str) -> Any:
    module = _MODULES.get(game_type)
    if module is None:
        raise KeyError(game_type)
    return module
