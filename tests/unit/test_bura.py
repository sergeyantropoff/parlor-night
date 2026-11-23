"""Правила буры: масть, козырь, очки и добор."""

import json

import pytest

from app.cards import bura


def _table(**overrides: object) -> dict:
    state = {
        "kind": "bura",
        "phase": "lead",
        "variant": "classic",
        "order": ["white", "black"],
        "hands": {"white": ["KH", "JH", "QS"], "black": ["AH", "TH", "JS"]},
        "deck": ["TS", "AD"],
        "trump": "S",
        "trump_card": "TS",
        "table": [],
        "tricks": {"white": [], "black": []},
        "scores": {"white": 0, "black": 0},
        "to_move": "white",
        "result": None,
        "reason": None,
        "line": "",
        "previous": {},
    }
    state.update(overrides)
    return state


def test_deal_keeps_twenty_cards_and_trump_at_the_bottom() -> None:
    state = bura.deal()
    dealt = state["hands"]["white"] + state["hands"]["black"] + state["deck"]
    assert len(dealt) == 20
    assert len(set(dealt)) == 20
    assert len(state["hands"]["white"]) == 3
    assert len(state["hands"]["black"]) == 3
    assert state["deck"][0] == state["trump_card"]
    assert state["trump"] == state["trump_card"][1]
    assert state["to_move"] == "black"


def test_ten_beats_king_and_trump_beats_an_ace() -> None:
    led = bura.apply(_table(hands={"white": ["KH", "JH", "QS"], "black": ["AH", "QH", "JS"]}), ["play", "KH"])
    answer = {tuple(item["path"]) for item in bura.legal(led)}
    assert ("play", "AH") in answer
    assert ("play", "QH") not in answer
    assert ("play", "JS") in answer
    assert ("act", "pass") in answer
    ten = bura.apply(_table(hands={"white": ["KH"], "black": ["TH"]}, deck=[]), ["play", "KH"])
    assert ("play", "TH") in {tuple(item["path"]) for item in bura.legal(ten)}
    beaten = bura.apply(led, ["play", "AH"])
    assert beaten["scores"]["black"] == 15
    assert beaten["to_move"] == "black"
    assert "AD" in beaten["hands"]["black"]

    bare = _table(hands={"white": ["KH"], "black": ["JS"]}, deck=[], trump="S", trump_card="")
    opened = bura.apply(bare, ["play", "KH"])
    covered = bura.apply(opened, ["play", "JS"])
    assert covered["scores"]["black"] == 6


def test_lead_must_be_one_suit_and_a_short_beat_does_not_count() -> None:
    state = _table()
    paths = [item["path"] for item in bura.legal(state)]
    assert ["play", "KH", "JH"] in paths
    assert ["play", "KH", "QS"] not in paths
    with pytest.raises(ValueError):
        bura.apply(state, ["play"])
    led = bura.apply(state, ["play", "KH", "JH"])
    with pytest.raises(ValueError):
        bura.apply(led, ["play", "AH"])


def test_pass_gives_the_trick_to_the_leader_and_winner_draws_first() -> None:
    led = bura.apply(_table(), ["play", "KH"])
    after = bura.apply(led, ["act", "pass"])
    assert after["scores"]["white"] == 4
    assert after["scores"]["black"] == 0
    assert after["to_move"] == "white"
    assert "AD" in after["hands"]["white"]
    assert after["deck"] == ["TS"]
    assert after["previous"]["seat"] == "white"


def test_even_points_draw_and_more_than_half_wins() -> None:
    even = _table(hands={"white": [], "black": []}, deck=[])
    even["tricks"] = {
        "white": ["AH", "AD", "AC", "AS", "TH", "KD", "JH"],
        "black": ["TD", "TC", "TS", "KH", "KC", "KS", "QH", "QD", "QC", "QS", "JD", "JC", "JS"],
    }
    bura._finish(even)
    assert even["result"] == "draw"
    assert even["scores"]["white"] == 60
    assert even["scores"]["black"] == 60
    assert even["line"].startswith("60 — 60")

    won = _table(hands={"white": [], "black": []}, deck=[])
    won["tricks"] = {
        "white": ["AH", "AD", "AC", "AS", "TH"],
        "black": ["TD", "TC", "TS", "KH", "KC", "KS", "QH", "QD", "QC", "QS", "JH", "JD", "JC", "JS", "KD"],
    }
    bura._finish(won)
    assert won["result"] == "black_win"
    assert won["reason"] == "points"
    assert won["scores"]["black"] == 66


def test_answer_without_a_beating_card_says_so() -> None:
    state = _table(
        phase="answer",
        trump="D",
        trump_card="AD",
        hands={"white": ["JC", "JS", "QC"], "black": ["KD", "QD"]},
        table=["JD"],
        deck=["AD", "TD", "TH", "JH"],
    )
    shown = bura.view(state, "white")
    assert "побить нельзя" in shown["message"]
    assert [item["path"] for item in bura.legal(state)] == [["act", "pass"]]


def test_suggest_is_always_a_legal_path() -> None:
    state = bura.deal(["white", "black"])
    seen = 0
    while not state.get("result") and seen < 80:
        path = bura.suggest(state, 3)
        legal = [item["path"] for item in bura.legal(state)]
        assert path in legal
        state = bura.apply(state, path)
        seen += 1
    assert state["result"] in {"white_win", "black_win", "draw"}
    assert sum(state["scores"].values()) == 120
    assert json.loads(bura.dumps(state))["kind"] == "bura"
