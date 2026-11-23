"""Личный итог не путает ничью с победой и поражением."""

from app.games.outcome import loss_seats, personal_mark


def test_board_games_keep_a_real_draw() -> None:
    assert personal_mark("chess", "draw", "white") == "draw"
    assert personal_mark("checkers", "white_win", "black") == "loss"
    assert personal_mark("go", "black_win", "black") == "win"
    assert personal_mark("uno", "p0_win", "p0") == "win"
    assert personal_mark("uno", "p0_win", "p2") == "loss"


def test_durak_draw_is_a_win_for_everyone_but_the_fool() -> None:
    position = {"loser": "p1"}
    assert personal_mark("durak", "draw", "p0", position=position) == "win"
    assert personal_mark("durak", "draw", "p1", position=position) == "loss"
    assert personal_mark("durak", "draw", "p0", position={"loser": ""}) == "draw"


def test_blackjack_draw_follows_the_stake() -> None:
    position = {
        "committed": {"p0": 25, "p1": 25, "p2": 25},
        "payout": {"p0": 50, "p1": 25, "p2": 0},
    }
    assert personal_mark("blackjack", "draw", "p0", position=position) == "win"
    assert personal_mark("blackjack", "draw", "p1", position=position) == "draw"
    assert personal_mark("blackjack", "draw", "p2", position=position) == "loss"


def test_poker_split_is_a_draw_only_for_those_who_took_the_pot() -> None:
    position = {"payout": {"p0": 40, "p1": 40, "p2": 0}}
    assert personal_mark("poker", "draw", "p0", position=position) == "draw"
    assert personal_mark("poker", "draw", "p2", position=position) == "loss"
    assert personal_mark("poker", "p1_win", "p1") == "win"


def test_preferans_tie_is_a_loss_for_the_worse_score() -> None:
    position = {
        "order": ["p0", "p1", "p2"],
        "bullet": {"p0": 12, "p1": 12, "p2": 8},
        "mountain": {"p0": 0, "p1": 0, "p2": 4},
        "whists": {"p0": {}, "p1": {}, "p2": {}},
    }
    assert personal_mark("preferans", "draw", "p0", position=position) == "draw"
    assert personal_mark("preferans", "draw", "p2", position=position) == "loss"
    assert personal_mark("preferans", "p1_win", "p1") == "win"


def test_only_the_loser_pays_the_table() -> None:
    assert loss_seats("chess", "white_win", ["white", "black"]) == ["black"]
    assert loss_seats("chess", "draw", ["white", "black"]) == []
    assert loss_seats("durak", "draw", ["p0", "p1", "p2"], {"loser": "p1"}) == ["p1"]
    assert loss_seats("yahtzy", "draw", ["p0", "p1", "p2"], {"winners": ["p0", "p1"]}) == ["p2"]
    assert loss_seats("uno", "p0_win", ["p0", "p1", "p2"]) == ["p1", "p2"]
