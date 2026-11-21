"""Правила длинных и коротких нард."""

from __future__ import annotations

import json
import random

import pytest

from app.errors import AppError
from app.games.service import GameService
from app.nardy.rules import apply, chronicle, deal, hint_mark, legal, replay, suggest


def _play(state, path, dice=None):
    return apply(state, path, dice=dice)


def test_short_opening_and_hit() -> None:
    state = deal(variant="short")
    state = _play(state, ["dice", "roll"], dice=(6, 1))
    paths = {tuple(item["path"]) for item in legal(state)}
    assert ("move", "23", "6") in paths
    state = _play(state, ["move", "23", "6"])
    assert state["points"][17] == 1
    assert state["points"][23] == 1
    assert state["to_move"] == "white"
    state = _play(state, ["move", "23", "1"])
    assert state["to_move"] == "black"
    state = _play(state, ["dice", "roll"], dice=(6, 6))
    state = _play(state, ["move", "11", "6"])
    assert state["points"][17] == -1
    assert state["bar"]["white"] == 1


def test_short_must_use_both_dice_in_the_order_that_works() -> None:
    state = deal(variant="short")
    state["points"] = [0] * 24
    state["points"][8] = 1
    state["off"] = {"white": 14, "black": 0}
    state["points"][7] = -2
    state = _play(state, ["dice", "roll"], dice=(2, 1))
    assert {tuple(item["path"]) for item in legal(state)} == {("move", "8", "2")}


def test_short_uses_the_larger_die_when_only_one_fits() -> None:
    state = deal(variant="short")
    state["points"] = [0] * 24
    state["points"][2] = 1
    state["off"] = {"white": 14, "black": 0}
    state["points"][0] = -2
    state["points"][1] = -2
    state["points"][4] = -2
    state["points"][5] = -2
    state = _play(state, ["dice", "roll"], dice=(4, 2))
    paths = {tuple(item["path"]) for item in legal(state)}
    assert paths == {("move", "2", "4")}


def test_short_reenter_and_bear() -> None:
    state = deal(variant="short")
    state["points"] = [0] * 24
    state["bar"] = {"white": 1, "black": 0}
    state["off"] = {"white": 14, "black": 0}
    state["points"][23] = -2
    state = _play(state, ["dice", "roll"], dice=(1, 2))
    assert {tuple(item["path"]) for item in legal(state)} == {("move", "bar", "2")}
    state = _play(state, ["move", "bar", "2"])
    assert state["bar"]["white"] == 0
    assert state["points"][22] == 1
    home = deal(variant="short")
    home["points"] = [0] * 24
    home["points"][0] = 1
    home["off"] = {"white": 14, "black": 0}
    home = _play(home, ["dice", "roll"], dice=(3, 1))
    home = _play(home, ["move", "0", "3"])
    assert home["off"]["white"] == 15
    assert home["result"] == "white_win"
    assert home["reason"] == "gammon"


def test_short_cube() -> None:
    state = deal(variant="short")
    state = _play(state, ["dice", "double"])
    assert state["phase"] == "answer"
    assert state["to_move"] == "black"
    state = _play(state, ["dice", "take"])
    assert state["cube"] == 2
    assert state["cube_owner"] == "black"
    assert state["to_move"] == "white"
    state = _play(state, ["dice", "roll"], dice=(6, 1))
    state = _play(state, ["move", "23", "6"])
    state = _play(state, ["move", "23", "1"])
    state = _play(state, ["dice", "double"])
    dropped = _play(state, ["dice", "drop"])
    assert dropped["result"] == "black_win"
    assert dropped["reason"] == "drop"
    assert dropped["score"] == 2


def test_long_blocks_and_head() -> None:
    state = deal(variant="long")
    state = _play(state, ["dice", "roll"], dice=(6, 5))
    assert {tuple(item["path"]) for item in legal(state)} == {("move", "0", "6"), ("move", "0", "5")}
    state = _play(state, ["move", "0", "6"])
    state = _play(state, ["move", "0", "5"])
    assert state["to_move"] == "black"
    assert state["points"][6] == 1
    assert state["points"][5] == 1
    assert state["points"][0] == 13
    state = _play(state, ["dice", "roll"], dice=(3, 3))
    state = _play(state, ["move", "12", "3"])
    state = _play(state, ["move", "12", "3"])
    assert state["points"][15] == -2
    assert all(item["path"][1] != "12" for item in legal(state))


def test_long_prime_is_illegal_and_mars_scores() -> None:
    state = deal(variant="long")
    state["points"] = [0] * 24
    state["points"][17] = 1
    state["points"][18] = 1
    state["points"][19] = 1
    state["points"][20] = 1
    state["points"][21] = 1
    state["points"][22] = 1
    state["off"] = {"white": 9, "black": 0}
    state["points"][12] = -15
    state["debut"] = {"white": False, "black": False}
    state = _play(state, ["dice", "roll"], dice=(6, 1))
    assert ("move", "17", "6") not in {tuple(item["path"]) for item in legal(state)}
    race = deal(variant="long")
    race["points"] = [0] * 24
    race["points"][23] = 1
    race["off"] = {"white": 14, "black": 0}
    race["points"][12] = -15
    race["debut"] = {"white": False, "black": True}
    race = _play(race, ["dice", "roll"], dice=(1, 2))
    race = _play(race, ["move", "23", "2"])
    assert race["result"] == "white_win"
    assert race["reason"] == "cox"
    assert race["score"] == 3


def test_hint_marks_the_best_landing() -> None:
    state = deal(variant="short")
    state = _play(state, ["dice", "roll"], dice=(6, 1))
    choice = suggest(state, 5)
    assert choice
    mark = hint_mark(state, choice)
    assert mark["seat"] == "white"
    assert mark["to"]
    again = hint_mark(state, choice)
    assert again == mark
    state = deal(variant="short")
    initial = __import__("json").dumps(state)
    payloads = []
    rng = random.Random(7)
    for _turn in range(80):
        if state.get("result"):
            break
        phase = state["phase"]
        if phase == "roll":
            pair = (rng.randint(1, 6), rng.randint(1, 6))
            state = apply(state, ["dice", "roll"], dice=pair)
            payloads.append({"path": ["dice", "roll", str(pair[0]), str(pair[1])]})
        else:
            choice = suggest(state, 4)
            assert choice
            state = apply(state, choice)
            payloads.append({"path": choice})
    again = replay(initial, payloads)
    assert again["points"] == state["points"]
    assert again["off"] == state["off"]
    assert chronicle(initial, payloads, again)["done"] is bool(again.get("result"))


def test_nardy_opens_long_or_short_with_a_person_or_a_computer() -> None:
    service = GameService.__new__(GameService)
    short = {
        "game_type": "nardy",
        "mode": "vs_computer",
        "player_side": "black",
        "engine_level": 4,
        "engine_time_ms": 1000,
        "audience": "closed",
        "computers": 1,
        "open_seats": 0,
        "nardy_kind": "short",
    }
    service._validate_create(short)
    assert short["computers"] is None
    assert short["nardy_kind"] == "short"
    ready = service._prepare_salon(short, None)
    state = json.loads(ready["current"])
    assert state["variant"] == "short"
    assert state["phase"] == "roll"
    assert state["points"][23] == 2
    waiting = service._prepare_salon({**short, "mode": "online", "nardy_kind": "long"}, None)
    opened = json.loads(waiting["current"])
    assert waiting["status"] == "waiting"
    assert opened["phase"] == "waiting"
    assert opened["variant"] == "long"
    for mode in ("free", "analysis", "lesson"):
        with pytest.raises(AppError, match="компьютером"):
            service._validate_create(
                {
                    "game_type": "nardy",
                    "mode": mode,
                    "player_side": "white",
                    "engine_level": 3,
                    "engine_time_ms": 1000,
                    "audience": "closed",
                    "nardy_kind": "long",
                }
            )


def test_long_game_can_finish() -> None:
    state = deal(variant="long")
    rng = random.Random(3)
    for _turn in range(500):
        if state.get("result"):
            break
        if state["phase"] == "roll":
            state = apply(state, ["dice", "roll"], dice=(rng.randint(1, 6), rng.randint(1, 6)))
            continue
        choice = suggest(state, 3)
        assert choice
        state = apply(state, choice)
    assert state["result"] in {"white_win", "black_win"}
    assert state["reason"] in {"oin", "mars", "cox"}
