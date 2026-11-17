from datetime import UTC, datetime

from app.profile_stats import tally


def test_counts_wins_losses_and_draws() -> None:
    user = "me"
    rows = [
        {"game_type": "chess", "result": "white_win", "player_side": "white", "user_id": user, "updated_at": datetime(2026, 11, 10, tzinfo=UTC)},
        {"game_type": "chess", "result": "white_win", "player_side": "white", "user_id": "other", "updated_at": datetime(2026, 11, 10, tzinfo=UTC)},
        {"game_type": "uno", "result": "p2_win", "seat_key": "p2", "user_id": user, "updated_at": datetime(2026, 11, 3, tzinfo=UTC)},
        {"game_type": "poker", "result": "draw", "player_side": "white", "user_id": user, "updated_at": datetime(2026, 11, 3, tzinfo=UTC)},
    ]
    stats = tally(rows, user, now=datetime(2026, 11, 16, tzinfo=UTC))
    assert stats["played"] == 4
    assert stats["wins"] == 2
    assert stats["losses"] == 1
    assert stats["draws"] == 1
    chess = next(item for item in stats["games"] if item["key"] == "chess")
    assert chess["wins"] == 1
    assert chess["losses"] == 1
    assert stats["line"]["dots"]


def test_line_spans_the_last_three_months() -> None:
    stats = tally([], "me", now=datetime(2026, 11, 17, tzinfo=UTC))
    labels = [dot["label"] for dot in stats["line"]["dots"]]
    assert labels[0] == "17 авг"
    assert labels[-1] == "16 ноя"
    assert len(labels) == 14
