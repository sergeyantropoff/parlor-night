import pytest

from app.errors import AppError
from app.site_policy import normalize


def _payload(**overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "registration_open": "on",
        "username_min": "3",
        "username_max": "32",
        "password_min": "10",
        "password_needs_letter": "",
        "password_needs_digit": "",
        "session_hours": "24",
        "login_failures": "5",
        "login_window_minutes": "15",
        "starting_chips": "100",
        "notice": "  Тихий   вечер  ",
        "games": ["chess"],
        "maintenance": "",
    }
    data.update(overrides)
    return data


def test_local_rules_can_be_relaxed() -> None:
    policy = normalize(_payload(password_min="4"), local=True)
    assert policy.registration_open is True
    assert policy.password_min == 4
    assert policy.password_needs_letter is False
    assert policy.password_needs_digit is False
    assert policy.notice == "Тихий вечер"
    assert policy.allows("chess") is True
    assert policy.allows("poker") is False


def test_deployed_rules_keep_password_floor() -> None:
    with pytest.raises(AppError):
        normalize(_payload(password_min="4"), local=False)
    policy = normalize(_payload(password_needs_letter="", password_needs_digit=""), local=False)
    assert policy.password_min == 10
    assert policy.password_needs_letter is False
    assert policy.password_needs_digit is False
    assert policy.for_staff().allows("poker") is True


def test_registration_has_three_modes() -> None:
    closed = normalize(_payload(registration_open=""), local=True)
    assert closed.registration_mode == "closed"
    assert closed.registration_open is False
    linked = normalize(_payload(registration_mode="referral"), local=True)
    assert linked.registration_mode == "referral"
    assert linked.registration_open is False
    opened = normalize(_payload(registration_mode="open"), local=True)
    assert opened.registration_mode == "open"
    assert opened.registration_open is True


def test_site_form_rejects_empty_catalog() -> None:
    with pytest.raises(AppError):
        normalize(_payload(games=[]), local=False)
