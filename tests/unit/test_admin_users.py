from datetime import UTC, datetime
from types import SimpleNamespace

from app.admin.routes import _users_back
from app.auth.routes import user_list_context
from app.clock import activate
from app.templating import _format_dt


def test_users_back_keeps_search_and_page() -> None:
    form = SimpleNamespace(get=lambda key: {"q": "  сережа  ", "page": "3"}.get(key))
    assert _users_back(form) == "/admin/users?q=%D1%81%D0%B5%D1%80%D0%B5%D0%B6%D0%B0&page=3"


def test_users_back_drops_the_first_page() -> None:
    form = SimpleNamespace(get=lambda key: {"q": "   ", "page": "1"}.get(key))
    assert _users_back(form) == "/admin/users"


def test_user_list_uses_the_shown_name() -> None:
    people = user_list_context(
        [{"username": "inecs", "full_name": "qwe\x1fqwe\x1f", "role": "user"}],
        None,
    )
    assert people["accounts"][0]["name"] == "qwe qwe"
    assert people["create_role"] == "user"


def test_clock_follows_the_visitor_zone() -> None:
    moment = datetime(2026, 11, 17, 6, 6, tzinfo=UTC)
    activate("Asia/Yekaterinburg")
    assert _format_dt(moment) == "17.11.2026 11:06"
    activate("нет такого пояса")
    assert _format_dt(moment) == "17.11.2026 09:06"
    assert _format_dt(datetime(2026, 11, 17, 6, 6)) == "17.11.2026 09:06"
