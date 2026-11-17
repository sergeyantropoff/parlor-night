"""Общая колода гостиной: коды карт и подписи."""

from __future__ import annotations

import secrets

SUITS = "CDHS"
SUIT_NAME = {"S": "пики", "H": "черви", "D": "бубны", "C": "трефы"}
RANK_NAME = {
    "A": "туз",
    "K": "король",
    "Q": "дама",
    "J": "валет",
    "T": "десятка",
    "9": "девятка",
    "8": "восьмёрка",
    "7": "семёрка",
    "6": "шестёрка",
    "5": "пятёрка",
    "4": "четвёрка",
    "3": "тройка",
    "2": "двойка",
}


def pack(ranks: str) -> list[str]:
    cards = [rank + suit for rank in ranks for suit in SUITS]
    secrets.SystemRandom().shuffle(cards)
    return cards


def label(card: str) -> str:
    if not card or len(card) < 2:
        return "карта"
    return f"{RANK_NAME.get(card[0], card[0])} {SUIT_NAME.get(card[1], card[1])}"


def rank_value(card: str, order: str) -> int:
    return order.index(card[0])
