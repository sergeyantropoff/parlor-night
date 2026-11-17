from datetime import datetime

from app.greeting import day_part, greeting


def test_day_part_follows_the_clock() -> None:
    assert day_part(0) == "Доброй ночи"
    assert day_part(4) == "Доброй ночи"
    assert day_part(5) == "Доброе утро"
    assert day_part(11) == "Доброе утро"
    assert day_part(12) == "Добрый день"
    assert day_part(16) == "Добрый день"
    assert day_part(17) == "Добрый вечер"
    assert day_part(22) == "Добрый вечер"
    assert day_part(23) == "Доброй ночи"


def test_greeting_uses_the_given_moment() -> None:
    moment = datetime(2026, 11, 16, 11, 40)
    assert greeting("admin", moment) == "Доброе утро, admin"
