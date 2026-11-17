import pytest

from app.errors import AppError
from app.names import called, parse_full_name, shown, split_full_name


def test_full_name_keeps_three_parts() -> None:
    text = parse_full_name("Иванов", "Иван", "Иванович")
    assert shown(text, "ivan") == "Иванов Иван Иванович"
    assert split_full_name(text) == ("Иванов", "Иван", "Иванович")
    assert shown("", "ivan") == "ivan"
    assert shown(None, "ivan") == "ivan"


def test_patronymic_is_optional() -> None:
    text = parse_full_name("Smith", "Ann", "")
    assert shown(text, "ann") == "Smith Ann"
    assert split_full_name(text) == ("Smith", "Ann", "")
    assert split_full_name("Smith Ann") == ("Smith", "Ann", "")


def test_any_single_part_is_enough() -> None:
    family = parse_full_name("Иванов", "", "")
    given = parse_full_name("", "Иван", "")
    patronymic = parse_full_name("", "", "Иванович")
    assert shown(family, "u") == "Иванов"
    assert split_full_name(family) == ("Иванов", "", "")
    assert shown(given, "u") == "Иван"
    assert split_full_name(given) == ("", "Иван", "")
    assert shown(patronymic, "u") == "Иванович"
    assert split_full_name(patronymic) == ("", "", "Иванович")


def test_any_pair_is_enough() -> None:
    assert shown(parse_full_name("Иванов", "", "Иванович"), "u") == "Иванов Иванович"
    assert split_full_name(parse_full_name("Иванов", "", "Иванович")) == ("Иванов", "", "Иванович")
    assert shown(parse_full_name("", "Анна", "Сергеевна"), "u") == "Анна Сергеевна"
    assert split_full_name(parse_full_name("", "Анна", "Сергеевна")) == ("", "Анна", "Сергеевна")


def test_table_uses_the_given_name_before_the_login() -> None:
    assert called(parse_full_name("Иванов", "Иван", "Иванович"), "ivan") == "Иван"
    assert called(parse_full_name("Иванов", "", ""), "ivan") == "Иванов"
    assert called("", "user") == "user"


def test_empty_name_is_allowed() -> None:
    assert parse_full_name("", "  ", None) == ""
    assert split_full_name("") == ("", "", "")


def test_name_rejects_digits() -> None:
    with pytest.raises(AppError) as caught:
        parse_full_name("Иванов2", "", "")
    assert caught.value.status == 422
    with pytest.raises(AppError):
        parse_full_name("", "Иван1", "")
