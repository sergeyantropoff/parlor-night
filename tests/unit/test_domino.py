"""Домино в линию: сдача, концы, базар, рыба и скрытая рука."""

from __future__ import annotations

from app.cards.domino import _pack, apply, deal, legal, replay, suggest, view


def test_pack_has_every_double_six_tile() -> None:
    tiles = _pack()
    assert len(tiles) == 28
    assert len(set(tiles)) == 28
    assert "6-6" in tiles
    assert "0-0" in tiles
    assert "6-0" in tiles


def test_two_players_take_seven_and_the_leader_opens_with_the_double() -> None:
    deck = _pack()
    state = deal(["white", "black"], deck=deck)
    assert len(state["hands"]["white"]) == 7
    assert len(state["hands"]["black"]) == 7
    assert len(state["boneyard"]) == 14
    assert state["to_move"] == "white"
    assert state["must"] == "6-6"
    assert [item["path"] for item in legal(state)] == [["play", "6-6", "R"]]
    opened = apply(state, ["play", "6-6", "R"])
    assert opened["line"] == [{"tile": "6-6", "a": 6, "b": 6}]
    assert "6-6" not in opened["hands"]["white"]


def test_a_tile_joins_only_a_matching_end() -> None:
    state = deal(["white", "black"], deck=_pack())
    state = apply(state, ["play", "6-6", "R"])
    state["hands"]["black"] = ["6-1", "0-0"]
    state["to_move"] = "black"
    paths = [item["path"] for item in legal(state)]
    assert ["play", "6-1", "L"] in paths
    assert ["play", "6-1", "R"] in paths
    assert ["play", "0-0", "L"] not in paths
    laid = apply(state, ["play", "6-1", "R"])
    assert laid["line"][-1] == {"tile": "6-1", "a": 6, "b": 1}
    shown = view(laid, "white")
    assert shown["chain"][-1]["hi_left"] is True
    assert "0-0" not in shown["hand"]
    assert view(laid, "black")["hand"] == ["0-0"]


def test_draw_stays_with_the_same_player_until_a_tile_fits() -> None:
    state = {
        "kind": "domino",
        "phase": "play",
        "order": ["white", "black"],
        "hands": {"white": ["1-0"], "black": ["2-0"]},
        "boneyard": ["0-0", "6-3"],
        "line": [{"tile": "6-6", "a": 6, "b": 6}],
        "to_move": "white",
        "must": "",
        "passes": 0,
        "result": None,
        "reason": None,
        "line_text": "",
    }
    assert legal(state) == [{"path": ["draw", "1"], "notation": "Взять из базара", "promotion": None}]
    drawn = apply(state, ["draw", "1"])
    assert drawn["to_move"] == "white"
    assert "6-3" in drawn["hands"]["white"]
    played = apply(drawn, ["play", "6-3", "R"])
    assert played["to_move"] == "black"
    assert played["line"][-1]["b"] == 3


def test_a_blocked_table_goes_to_the_smaller_hand() -> None:
    state = {
        "kind": "domino",
        "phase": "play",
        "order": ["white", "black"],
        "hands": {"white": ["1-0"], "black": ["2-2"]},
        "boneyard": [],
        "line": [{"tile": "6-6", "a": 6, "b": 6}],
        "to_move": "white",
        "must": "",
        "passes": 0,
        "result": None,
        "reason": None,
        "line_text": "",
    }
    state = apply(state, ["pass", "1"])
    state = apply(state, ["pass", "1"])
    assert state["result"] == "white_win"
    assert state["reason"] == "blocked"
    assert state["scores"] == {"white": 1, "black": 4}


def test_equal_block_is_a_draw_and_an_empty_hand_wins_at_once() -> None:
    tied = {
        "kind": "domino",
        "phase": "play",
        "order": ["white", "black"],
        "hands": {"white": ["1-0"], "black": ["1-0"]},
        "boneyard": [],
        "line": [{"tile": "6-6", "a": 6, "b": 6}],
        "to_move": "white",
        "must": "",
        "passes": 1,
        "result": None,
        "reason": None,
        "line_text": "",
    }
    # У чёрных та же кость уже невозможна в наборе, здесь проверяется только счёт.
    done = apply(tied, ["pass", "1"])
    assert done["result"] == "draw"

    race = {
        "kind": "domino",
        "phase": "play",
        "order": ["white", "black"],
        "hands": {"white": ["6-5"], "black": ["0-0"]},
        "boneyard": [],
        "line": [{"tile": "5-1", "a": 5, "b": 1}],
        "to_move": "white",
        "must": "",
        "passes": 0,
        "result": None,
        "reason": None,
        "line_text": "",
    }
    won = apply(race, ["play", "6-5", "L"])
    assert won["result"] == "white_win"
    assert won["reason"] == "empty"


def test_suggest_always_plays_a_legal_move_until_the_table_ends() -> None:
    state = deal(["p0", "p1", "p2"])
    assert len(state["hands"]["p0"]) == 5
    assert len(state["boneyard"]) == 13
    seen = dumps_roundtrip(state)
    for _ in range(90):
        if seen["result"]:
            break
        path = suggest(seen, 4)
        assert path is not None
        assert list(path) in [list(item["path"]) for item in legal(seen)]
        seen = apply(seen, path)
    assert seen["result"]
    again = replay(deal_text(state), [])
    assert again["must"] == state["must"]


def deal_text(state: dict) -> str:
    from app.cards.domino import dumps

    return dumps(state)


def dumps_roundtrip(state: dict) -> dict:
    from app.cards.domino import dumps, loads

    return loads(dumps(state))
