import json

import pytest

from app.errors import AppError, IllegalMove
from app.games.service import GameService
from app.yahtzy.rules import (
    apply,
    deal,
    dumps,
    leave,
    legal,
    replay,
    stored_path,
    suggest,
    view,
)


def _score(state, category, dice):
    state = apply(state, ["dice", *[str(face) for face in dice]])
    return apply(state, ["score", category])


def _other(state, index):
    boxes = ("chance", "three", "four", "house", "small", "large", "ones", "twos")
    return _score(state, boxes[index], [1, 2, 3, 4, 6])


def test_upper_bonus_appears_at_sixty_three_and_zero_when_missed() -> None:
    state = deal(["white", "black"])
    for category, face in (
        ("sixes", 6),
        ("fives", 5),
        ("fours", 4),
        ("threes", 3),
    ):
        state = _score(state, category, [face, face, face, 1, 2])
        state = _other(state, ("sixes", "fives", "fours", "threes").index(category))
    assert state["scores"]["white"]["sixes"] == 18
    assert sum(state["scores"]["white"][key] for key in ("sixes", "fives", "fours", "threes")) == 54
    state = _score(state, "twos", [2, 2, 2, 2, 2])
    picture = view(state, "white")["yahtzy"]
    white = picture["columns"][0]
    assert white["upper"] == 64
    assert white["bonus"] == 35
    short = deal()
    for category in ("ones", "twos", "threes", "fours", "fives", "sixes"):
        short = _score(short, category, [1, 2, 3, 4, 6])
        short = _other(short, ("ones", "twos", "threes", "fours", "fives", "sixes").index(category))
    missed = view(short, "white")["yahtzy"]["columns"][0]
    assert missed["bonus"] == 0


def test_lower_boxes_use_the_printed_scores() -> None:
    state = deal()
    state = _score(state, "three", [4, 4, 4, 2, 1])
    state = _other(state, 0)
    state = _score(state, "four", [5, 5, 5, 5, 2])
    state = _other(state, 1)
    state = _score(state, "house", [6, 6, 6, 1, 1])
    state = _other(state, 2)
    state = _score(state, "small", [1, 2, 3, 4, 6])
    state = _other(state, 3)
    state = _score(state, "large", [2, 3, 4, 5, 6])
    state = _other(state, 4)
    state = _score(state, "yahtzy", [3, 3, 3, 3, 3])
    white = state["scores"]["white"]
    assert white["three"] == 15
    assert white["four"] == 22
    assert white["house"] == 25
    assert white["small"] == 30
    assert white["large"] == 40
    assert white["yahtzy"] == 50
    assert _score(deal(), "house", [6, 6, 6, 6, 6])["scores"]["white"]["house"] == 0
    assert _score(deal(), "three", [6, 6, 2, 3, 4])["scores"]["white"]["three"] == 0


def test_second_yahtzy_pays_a_hundred_and_locks_the_matching_upper_box() -> None:
    state = _score(deal(), "yahtzy", [6, 6, 6, 6, 6])
    state = _score(state, "chance", [1, 1, 1, 1, 2])
    state = apply(state, ["dice", "6", "6", "6", "6", "6"])
    assert [item["path"] for item in legal(state)] == [["roll"], ["score", "sixes"]]
    state = apply(state, ["score", "sixes"])
    assert state["scores"]["white"]["sixes"] == 30
    assert state["chips"]["white"] == 100
    state = _other(state, 1)
    state["scores"]["white"]["fives"] = 0
    state = apply(state, ["dice", "5", "5", "5", "5", "5"])
    open_boxes = [item["path"][1] for item in legal(state) if item["path"][0] == "score"]
    assert "fives" not in open_boxes
    assert "yahtzy" not in open_boxes
    assert "house" in open_boxes
    state = apply(state, ["score", "house"])
    assert state["scores"]["white"]["house"] == 25
    assert state["chips"]["white"] == 200


def test_a_crossed_yahtzy_box_does_not_pay_the_bonus_later() -> None:
    state = _score(deal(), "yahtzy", [1, 2, 3, 4, 5])
    state = _score(state, "chance", [1, 1, 1, 1, 2])
    state = _score(state, "chance", [6, 6, 6, 6, 6])
    assert state["scores"]["white"]["yahtzy"] == 0
    assert state["scores"]["white"]["chance"] == 30
    assert state["chips"]["white"] == 0


def test_three_rolls_then_the_box_is_required() -> None:
    state = deal()
    kept = []
    for _ in range(3):
        state = apply(state, ["roll", *kept])
        kept = ["0"]
    assert state["rolls_left"] == 0
    assert all(item["path"][0] == "score" for item in legal(state))
    with pytest.raises(ValueError, match="кончились"):
        apply(state, ["roll"])


def test_replay_keeps_the_faces_the_table_rolled(monkeypatch: pytest.MonkeyPatch) -> None:
    faces = iter([2, 4, 6, 1, 3, 5, 5, 1])
    monkeypatch.setattr("app.yahtzy.rules.secrets.randbelow", lambda _bound: next(faces) - 1)
    state = deal()
    state = apply(state, ["roll"])
    assert state["dice"] == [2, 4, 6, 1, 3]
    recorded = stored_path(["roll"], state)
    state = apply(state, ["roll", "0", "2"])
    assert state["dice"] == [2, 5, 6, 5, 1]
    assert state["motion"]["kept"] == [0, 2]
    initial = dumps(deal())
    again = replay(initial, [{"path": recorded}, {"path": stored_path(["roll", "0", "2"], state)}])
    assert again["dice"] == [2, 5, 6, 5, 1]
    with pytest.raises(ValueError, match="бросьте"):
        apply(deal(), ["roll", "1"])


def test_highest_total_wins_and_a_tie_names_both() -> None:
    state = deal(["p0", "p1", "p2"])
    for seat in ("p0", "p1", "p2"):
        assert state["to_move"] == seat
        state = _score(state, "chance", [6, 6, 6, 6, 6] if seat != "p2" else [1, 1, 1, 1, 1])
    for category in (
        "ones",
        "twos",
        "threes",
        "fours",
        "fives",
        "sixes",
        "three",
        "four",
        "house",
        "small",
        "large",
        "yahtzy",
    ):
        for seat in ("p0", "p1", "p2"):
            dice = [1, 2, 3, 4, 6]
            state = _score(state, category, dice)
    assert state["result"] == "draw"
    assert state["winners"] == ["p0", "p1"]
    assert "Ничья" in state["line_text"]
    left = leave(deal(["white", "black"]), "white")
    assert left["result"] == "black_win"


def test_the_computer_offers_one_legal_step() -> None:
    state = deal()
    first = suggest(state, 5)
    assert first == ["roll"]
    state = apply(state, ["dice", "6", "6", "6", "6", "2"])
    choice = suggest(state, 5)
    assert choice is not None
    assert choice[0] in {"roll", "score"}
    if choice[0] == "score":
        apply(state, choice)


def test_table_size_and_the_client_cannot_name_the_faces() -> None:
    with pytest.raises(ValueError, match="четырёх"):
        deal(["white"])
    ready = deal(["p0", "p1", "p2", "p3"])
    assert ready["order"] == ["p0", "p1", "p2", "p3"]
    service = GameService.__new__(GameService)
    body = {
        "game_type": "yahtzy",
        "mode": "vs_computer",
        "player_side": "white",
        "engine_level": 3,
        "engine_time_ms": 1000,
        "audience": "open",
        "computers": 1,
        "open_seats": 0,
    }
    service._validate_create(body)
    opened = json.loads(service._prepare_salon(body, None)["current"])
    assert opened["kind"] == "yahtzy"
    assert opened["order"] == ["white", "black"]
    game = {"game_type": "yahtzy", "initial_position": dumps(opened)}
    with pytest.raises(IllegalMove, match="нет"):
        service._push_card(game, [], ["dice", "6", "6", "6", "6", "6"], "human")
    played = service._push_card(game, [], ["roll"], "human")
    assert played["payload"]["path"][0] == "dice"
    assert len(played["payload"]["path"]) == 6
    for mode in ("free", "analysis", "lesson"):
        with pytest.raises(AppError, match="компьютером"):
            service._validate_create({**body, "mode": mode})
    with pytest.raises(AppError, match="четырёх"):
        service._validate_create({**body, "computers": 0, "open_seats": 0})
