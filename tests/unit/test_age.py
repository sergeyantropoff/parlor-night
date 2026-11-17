from datetime import date

import pytest

from app.wallet import age_years, format_born, parse_born_text, years_phrase


def test_adult_birthday_is_exact() -> None:
    assert age_years(date(1982, 9, 26), date(2026, 11, 16)) == 44
    assert age_years(date(1982, 9, 26), date(2000, 9, 25)) == 17
    assert age_years(date(1982, 9, 26), date(2000, 9, 26)) == 18
    assert format_born(date(1982, 9, 26)) == "26 сентября 1982"


def test_child_date_stays_closed() -> None:
    assert age_years(date(2015, 1, 1), date(2026, 11, 16)) == 11
    assert years_phrase(11) == "11 лет"
    assert years_phrase(44) == "44 года"
    assert years_phrase(21) == "21 год"


def test_birth_text_accepts_russian_and_iso() -> None:
    assert parse_born_text("26.09.1982", date(2026, 11, 16)) == date(1982, 9, 26)
    assert parse_born_text("1982-09-26", date(2026, 11, 16)) == date(1982, 9, 26)
    with pytest.raises(ValueError):
        parse_born_text("31.02.1982", date(2026, 11, 16))
    with pytest.raises(ValueError):
        parse_born_text("26.09.2030", date(2026, 11, 16))
