"""Числа фишек, которые задаёт администратор."""

import pytest

from app.errors import AppError
from app.terms import defaults, read_form


def _form(**overrides: str) -> dict[str, str]:
    data: dict[str, str] = {}
    for row in defaults().rows:
        for field in row.fields():
            data[f"{row.game}_{field.key}"] = field.value
    data.update(overrides)
    return data


def test_default_note_keeps_the_parlor_awards() -> None:
    book = defaults()
    assert "30" in book.note("chess")
    assert "10" in book.note("chess")
    assert "20" in book.note("durak")
    assert "1000" in book.note("poker")
    assert book.blackjack.bets == (10, 25, 50, 100)
    assert book.preferans.points == 100
    assert book.preferans.prices == (1, 2, 5, 10)


def test_loss_round_trip_and_the_default() -> None:
    book = defaults()
    assert book.chess.loss == 10
    assert book.durak.loss == 10
    assert book.poker.loss == 0
    assert book.blackjack.loss == 0
    assert book.preferans.loss == 0
    saved = read_form(_form(chess_loss="15", durak_loss="0", poker_loss="4"))
    assert saved.chess.loss == 15
    assert saved.durak.loss == 0
    assert saved.poker.loss == 4
    assert "15" in saved.note("chess")
    assert "отдаёт 0" in saved.note("durak")


def test_form_round_trip_changes_a_win_and_a_blind() -> None:
    book = read_form(_form(chess_win="40", poker_small="10", poker_big="20"))
    assert book.chess.win == 40
    assert book.poker.small == 10
    assert book.poker.big == 20
    assert "40" in book.note("chess")


def test_preferans_prices_round_trip() -> None:
    book = read_form(_form(preferans_prices="1, 3, 8"))
    assert book.preferans.prices == (1, 3, 8)
    assert "1, 3, 8" in book.note("preferans")


def test_small_blind_must_stay_below_the_big_one() -> None:
    with pytest.raises(AppError):
        read_form(_form(poker_small="10", poker_big="10"))
