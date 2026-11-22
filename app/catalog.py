"""Каталог игр. Новая игра — запись здесь и свой модуль правил."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class GameSpec:
    key: str
    title: str
    family: str
    adult: bool
    blurb: str


def visible_games(adult: bool) -> dict[str, GameSpec]:
    if adult:
        return GAMES
    return {key: spec for key, spec in GAMES.items() if not spec.adult}


GAMES: dict[str, GameSpec] = {
    "chess": GameSpec("chess", "Шахматы", "board", False, "Классическая партия и разбор."),
    "checkers": GameSpec("checkers", "Русские шашки", "board", False, "Шашки 8×8, обязательное взятие."),
    "go": GameSpec("go", "Го", "board", False, "Стратегия чёрных и белых камней. С человеком или с компьютером."),
    "domino": GameSpec(
        "domino",
        "Домино",
        "cards",
        False,
        "Кости в линию, от двух до четырёх. С человеком или с компьютером.",
    ),
    "nardy": GameSpec(
        "nardy",
        "Нарды",
        "board",
        False,
        "Длинные и короткие. С человеком или с компьютером.",
    ),
    "yahtzy": GameSpec(
        "yahtzy",
        "Яцзы",
        "cards",
        False,
        "Пять костей и бланк. С человеком или с компьютером.",
    ),
    "uno": GameSpec("uno", "Уно", "cards", False, "Цвета, цифры и дикие карты. Без денег."),
    "poker": GameSpec(
        "poker",
        "Покер",
        "cards",
        True,
        "Техасский холдем до шести игроков, на игровые фишки. Не на деньги. С 18 лет.",
    ),
    "durak": GameSpec(
        "durak",
        "Дурак",
        "cards",
        False,
        "Подкидной или переводной. Вид выбирается при старте. Колода в 36 карт.",
    ),
    "blackjack": GameSpec(
        "blackjack",
        "Блэкджек",
        "cards",
        True,
        "Против дилера на игровые фишки. Не на деньги. С 18 лет.",
    ),
    "preferans": GameSpec(
        "preferans",
        "Преферанс",
        "cards",
        True,
        "Трое игроков, торг и взятки на игровые фишки. С 18 лет.",
    ),
}


def spec(key: str) -> GameSpec | None:
    return GAMES.get(key)


def titles() -> dict[str, str]:
    return {key: item.title for key, item in GAMES.items()}
