import pytest

from app.broadcast import clean_broadcast
from app.errors import AppError


def test_empty_broadcast_clears_the_message() -> None:
    assert clean_broadcast("   ", "error") == ("", "info")


def test_broadcast_keeps_a_known_tone() -> None:
    assert clean_broadcast("  Скоро вечер.  ", "warning") == ("Скоро вечер.", "warning")


def test_broadcast_rejects_an_unknown_tone() -> None:
    with pytest.raises(AppError) as caught:
        clean_broadcast("Привет", "loud")
    assert caught.value.status == 422


def test_broadcast_rejects_a_long_phrase() -> None:
    with pytest.raises(AppError):
        clean_broadcast("а" * 501, "info")
