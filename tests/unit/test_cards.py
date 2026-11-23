from app.cards.poker import apply as play_poker
from app.cards.poker import deal, rank_hand
from app.cards.uno import apply as play_uno
from app.cards.uno import deal as deal_uno
from app.cards.uno import legal as legal_uno


def test_poker_hand_order() -> None:
    assert rank_hand(["AH", "KH", "QH", "JH", "TH"]) > rank_hand(["AS", "AH", "AD", "AC", "2D"])
    assert rank_hand(["AS", "2H", "3D", "4C", "5S"]) > rank_hand(["KS", "QH", "JD", "9C", "8S"])
    assert rank_hand(["2C", "2D", "2H", "2S", "9D"]) > rank_hand(["AS", "AH", "AD", "KC", "KD"])


def test_poker_fold_pays_the_other_seat() -> None:
    state = deal()
    state, charges = play_poker(state, ["act", "fold"])
    assert charges == []
    assert state["result"] == "black_win"
    assert state["payout"]["black"] == 15
    assert "сбросили" in state["winner_hand"]


def test_leave_table_gives_the_pot_to_the_other_seat() -> None:
    from app.cards.poker import leave, replay

    state = deal()
    left = leave(state, "white")
    assert left["result"] == "black_win"
    assert left["reason"] == "left"
    assert left["payout"]["black"] == state["pot"]
    restored = replay(deal_text(state), [{"leave": True, "seat": "white"}])
    assert restored["result"] == "black_win"


def deal_text(state: dict) -> str:
    from app.cards.poker import dumps

    return dumps(state)


def test_uno_hand_is_sorted_by_color() -> None:
    from app.cards.uno import view

    state = deal_uno()
    state["hands"]["white"] = ["W", "B5", "R9", "G0", "Y3", "RS", "W", "BD"]
    shown = view(state, "white")
    assert shown["hand"] == ["R9", "RS", "Y3", "G0", "B5", "BD", "W", "W"]


def test_uno_leave_ends_the_hand() -> None:
    from app.cards.uno import dumps, leave, replay

    state = deal_uno()
    left = leave(state, "white")
    assert left["phase"] == "done"
    assert left["result"] == "black_win"
    assert replay(dumps(state), [{"leave": True, "seat": "white"}])["result"] == "black_win"


def test_uno_master_keeps_a_matching_number() -> None:
    from app.cards.uno import suggest

    state = {
        "kind": "uno",
        "phase": "play",
        "hands": {"white": ["R5", "W", "B2"], "black": ["G1"]},
        "deck": ["Y3"],
        "discard": ["R1"],
        "color": "R",
        "to_move": "white",
        "result": None,
        "reason": None,
    }
    assert suggest(state, 5) == ["play", "R5"]
    assert suggest(state, 1)[0] == "play"


def test_holdem_opens_the_board_and_names_the_winner() -> None:
    from app.cards.poker import legal

    state = deal()
    assert len(state["hands"]["white"]) == 2
    assert state["board"] == []
    assert ["act", "raise"] in [item["path"] for item in legal(state)]
    state, charges = play_poker(state, ["act", "call"])
    assert charges == [("white", 5)]
    state, _charges = play_poker(state, ["act", "check"])
    assert state["phase"] == "flop"
    assert len(state["board"]) == 3

    state["hands"] = {"white": ["AH", "KH"], "black": ["2C", "7D"]}
    state["board"] = ["QH", "JH", "TH", "3C", "9D"]
    state["phase"] = "river"
    state["deck"] = []
    state["committed"] = {"white": 0, "black": 0}
    state["stake"] = 0
    state["bets"] = 0
    state["acted"] = []
    state["to_move"] = "black"
    state, _charges = play_poker(state, ["act", "check"])
    state, _charges = play_poker(state, ["act", "check"])
    assert state["result"] == "white_win"
    assert state["winner_hand"] == "Белые выиграли: Роял-флеш."
    assert len(state["board"]) == 5


def test_poker_master_bets_two_pair_and_folds_air() -> None:
    from app.cards.poker import suggest

    state = deal()
    state["phase"] = "river"
    state["board"] = ["AH", "AD", "7C", "2S", "9D"]
    state["hands"]["white"] = ["KC", "KH"]
    state["committed"] = {"white": 0, "black": 0}
    state["stake"] = 0
    state["bets"] = 0
    state["acted"] = []
    state["to_move"] = "white"
    assert suggest(state, 5) == ["act", "bet"]

    weak = deal()
    weak["hands"]["white"] = ["2C", "7D"]
    weak["street_bet"] = None
    assert suggest(weak, 5) == ["act", "fold"]


def test_uno_red_matches_a_wild_played_as_red() -> None:
    state = deal_uno()
    state["discard"] = ["WR"]
    state["color"] = "R"
    state["hands"]["white"] = ["R3", "B6", "GS"]
    state["to_move"] = "white"
    paths = [list(item["path"]) for item in legal_uno(state)]
    assert ["play", "R3"] in paths
    assert ["play", "B6"] not in paths
    assert ["play", "GS"] not in paths


def test_stronger_poker_bluffs_more() -> None:
    from app.cards.poker import suggest

    holes = [
        ["7C", "5H"],
        ["8C", "6H"],
        ["3C", "8S"],
        ["4H", "9C"],
        ["5D", "8H"],
        ["3H", "7D"],
        ["4C", "8D"],
        ["5H", "9S"],
    ]
    novice = master = 0
    for hole in holes:
        state = deal()
        state["phase"] = "river"
        state["board"] = ["AH", "KD", "9C", "2S", "6D"]
        state["hands"]["white"] = hole
        state["committed"] = {"white": 0, "black": 0}
        state["stake"] = 0
        state["bets"] = 0
        state["acted"] = []
        state["to_move"] = "white"
        if suggest(state, 2) == ["act", "bet"]:
            novice += 1
        if suggest(state, 5) == ["act", "bet"]:
            master += 1
    assert master > novice
    assert master >= 2


def test_three_handed_poker_stays_open_after_one_fold() -> None:
    from app.cards.poker import deal_table

    state = deal_table(["p0", "p1", "p2"])
    assert state["to_move"] == "p0"
    assert state["pot"] == 15
    assert len(state["hands"]) == 3
    state, _charges = play_poker(state, ["act", "fold"])
    assert state["phase"] == "preflop"
    assert state["result"] is None
    assert "p0" in state["folded"]
    assert state["to_move"] == "p1"


def test_chronicle_names_the_last_action_and_the_winner() -> None:
    from app.cards.poker import chronicle, deal_table, dumps

    state = deal_table(["p0", "p1", "p2"])
    initial = dumps(state)
    opened = chronicle(initial, [{"path": ["act", "fold"]}])
    assert opened["done"] is False
    assert opened["last"]["p0"] == "fold"
    assert opened["counts"]["fold"] == 1
    finished = chronicle(initial, [{"path": ["act", "fold"]}, {"path": ["act", "fold"]}])
    assert finished["done"] is True
    assert finished["winner"] == "p2"
    assert finished["last"]["p1"] == "fold"
    assert "Место 3" in finished["winner_label"]


def test_uno_skip_passes_the_next_of_three() -> None:
    state = deal_uno()
    state["order"] = ["p0", "p1", "p2"]
    state["direction"] = 1
    state["hands"] = {"p0": ["RS"], "p1": ["B1"], "p2": ["G2"]}
    state["discard"] = ["R2"]
    state["color"] = "R"
    state["to_move"] = "p0"
    state["deck"] = ["Y3", "B4"]
    played = play_uno(state, ["play", "RS"])
    assert played["to_move"] == "p2"
    assert played["hands"]["p1"] == ["B1"]


def test_nolimit_slider_accepts_a_chosen_raise_and_an_all_in() -> None:
    from app.cards.poker import legal

    state = deal()
    raised = next(item for item in legal(state) if item["path"] == ["act", "raise"])
    assert raised["min"] == 20
    assert raised["max"] == 1000
    state, charges = play_poker(state, ["act", "raise", "100"])
    assert charges == [("white", 95)]
    assert state["stake"] == 100
    assert state["stacks"]["white"] == 900
    state, charges = play_poker(state, ["act", "raise", "1000"])
    assert charges == [("black", 990)]
    assert state["stacks"]["black"] == 0
    assert state["pot"] == 1100
    assert state["phase"] == "preflop"

    limited = deal()
    del limited["stacks"]
    del limited["invested"]
    limited.pop("last_size", None)
    limited, charges = play_poker(limited, ["act", "raise"])
    assert charges == [("white", 15)]
    assert limited["stake"] == 20


def test_a_matched_street_checks_through_instead_of_betting_the_same_size() -> None:
    from app.cards.poker import apply, deal_table, legal

    state = deal_table(["p0", "p1", "p2", "p3", "p4", "p5"])
    for key in ("stacks", "invested", "last_size"):
        state.pop(key, None)
    state["to_move"] = "p2"
    state["stake"] = 10
    state["bets"] = 1
    state["committed"] = {"p0": 0, "p1": 5, "p2": 10, "p3": 0, "p4": 10, "p5": 0}
    state["folded"] = ["p5", "p0", "p3", "p1"]
    state["acted"] = ["p4"]
    paths = [item["path"] for item in legal(state)]
    assert ["act", "bet"] not in paths
    assert ["act", "check"] in paths
    after, _charges = apply(state, ["act", "check"])
    assert after["phase"] == "flop"
    recorded, _charges = apply(state, ["act", "bet"])
    assert recorded["pot"] == state["pot"] + 10


def test_saved_fold_order_still_matches() -> None:
    from app.cards.poker import deal_table, dumps, matches

    state = deal_table(["p0", "p1", "p2"])
    state["folded"] = ["p5", "p3", "p0"]
    other = dumps({**state, "folded": ["p0", "p3", "p5"]})
    assert matches(state, other)


def test_computer_stacks_differ_around_the_median() -> None:
    from app.cards.poker import spread_purses

    purses = spread_purses(["p1", "p2", "p3", "p4"], 700, seed=3)
    assert len(set(purses.values())) == 4
    assert all(400 <= amount <= 840 for amount in purses.values())


def test_computer_stops_before_the_stack_is_gone() -> None:
    from app.cards.poker import suggest

    state = deal(200)
    state["phase"] = "flop"
    state["board"] = ["9H", "2C", "7D"]
    state["hands"]["white"] = ["9C", "9S"]
    state["stake"] = 120
    state["committed"] = {"white": 0, "black": 120}
    state["stacks"] = {"white": 80, "black": 40}
    state["invested"] = {"white": 20, "black": 160}
    state["bets"] = 3
    state["last_size"] = 60
    state["to_move"] = "white"
    path = suggest(state, 5)
    assert path is not None
    assert path[1] != "raise"


def test_uno_can_draw_instead_of_playing() -> None:
    state = deal_uno()
    state["hands"]["white"] = ["R5", "B2"]
    state["hands"]["black"] = ["G1"]
    state["discard"] = ["R1"]
    state["color"] = "R"
    state["deck"] = ["Y9", "B4"]
    state["to_move"] = "white"
    paths = [item["path"] for item in legal_uno(state)]
    assert ["play", "R5"] in paths
    assert ["draw", "1"] in paths
    drawn = play_uno(state, ["draw", "1"])
    assert drawn["hands"]["white"] == ["R5", "B2", "B4"]
    assert drawn["discard"] == ["R1"]
    assert drawn["to_move"] == "black"
    assert drawn["acts"]["white"] == "draw"


def test_uno_play_or_draw() -> None:
    state = deal_uno()
    actions = legal_uno(state)
    assert actions
    path = list(actions[0]["path"])
    after = play_uno(state, path)
    assert after["to_move"] in {"white", "black"}
    assert after["discard"]


def test_uno_wild_offers_each_color_once() -> None:
    state = deal_uno()
    state["hands"]["white"] = ["W", "W"]
    state["discard"] = ["R1"]
    state["color"] = "R"
    state["to_move"] = "white"
    paths = [
        tuple(item["path"])
        for item in legal_uno(state)
        if tuple(item["path"])[-1] != "uno" or len(item["path"]) == 1
    ]
    assert paths.count(("play", "W", "R")) == 1
    assert paths.count(("play", "W", "B")) == 1
    assert len([item for item in paths if item[:2] == ("play", "W")]) == 4


def test_recycled_wild_makes_the_computer_name_a_color() -> None:
    from app.cards.uno import suggest

    state = deal_uno()
    state["hands"]["black"] = ["WY", "G4", "B2"]
    state["discard"] = ["R8", "WB", "WG", "WY"]
    state["color"] = "W"
    state["deck"] = []
    state["to_move"] = "black"
    paths = [tuple(item["path"]) for item in legal_uno(state)]
    assert ("play", "G4") not in paths
    assert ("play", "WY") not in paths
    assert paths.count(("play", "W", "Y")) == 1
    choice = suggest(state, 5)
    assert choice is not None
    assert choice[:2] == ["play", "W"]
    assert choice[2] in "RYGB"
    played = play_uno(state, ["play", "W", "B"])
    assert played["color"] == "B"
    assert played["discard"][-1] == "WB"
    assert "WY" not in played["hands"]["black"]
    drawn = play_uno(state, ["draw", "1"])
    recycled = [*drawn["hands"]["black"], *drawn["deck"]]
    assert "WB" not in recycled and "WG" not in recycled and "WY" not in recycled
    assert "W" in recycled


def test_uno_call_keeps_the_last_card() -> None:
    from app.cards.uno import suggest

    state = deal_uno()
    state["hands"]["white"] = ["R5", "B2"]
    state["hands"]["black"] = ["G1"]
    state["discard"] = ["R1"]
    state["color"] = "R"
    state["deck"] = ["Y3", "B4", "G5"]
    state["to_move"] = "white"
    assert ["uno"] in [item["path"] for item in legal_uno(state)]
    assert suggest(state, 5) == ["uno"]
    called = play_uno(state, ["uno"])
    assert called["to_move"] == "white"
    played = play_uno(called, ["play", "R5"])
    assert played["hands"]["white"] == ["B2"]
    assert played["said"] == ["white"]


def test_uno_call_rides_with_the_card() -> None:
    state = deal_uno()
    state["hands"]["white"] = ["R5", "B2"]
    state["discard"] = ["R1"]
    state["color"] = "R"
    state["deck"] = ["Y3", "B4", "G5"]
    state["to_move"] = "white"
    played = play_uno(state, ["play", "R5", "uno"])
    assert played["hands"]["white"] == ["B2"]
    assert played["said"] == ["white"]
    assert played["acts"]["white"] == "play"


def test_uno_chronicle_names_the_winner() -> None:
    from app.cards.uno import chronicle, dumps

    state = deal_uno()
    state["hands"]["white"] = ["R3"]
    state["discard"] = ["R7"]
    state["color"] = "R"
    state["to_move"] = "white"
    initial = dumps(state)
    report = chronicle(initial, [{"path": ["play", "R3"]}])
    assert report["done"] is True
    assert report["winner"] == "white"
    assert report["reason"] == "empty_hand"
    assert report["counts"]["play"] == 1
    assert report["line"] == "Карты закончились."


def test_preferans_pass_and_miser_are_not_named_as_a_card() -> None:
    from app.cards import blackjack, durak, preferans
    from app.games.service import _move_title
    from app.nardy import rules as nardy

    state = preferans.deal()
    passed, _charges = preferans.apply(state, ["bid", "pass"])
    miser, _charges = preferans.apply(preferans.deal(), ["bid", "miser"])
    assert passed["bidding"][state["to_move"]] == "passed"
    assert miser["contract"] == {"miser": True}
    assert _move_title(preferans, state, passed, ["bid", "pass"]) == ""
    assert _move_title(preferans, state, miser, ["bid", "miser"]) == ""
    assert _move_title(durak, {}, {}, ["play", "7S"]) == ""
    assert _move_title(blackjack, {}, {}, ["hit"]) == ""
    assert _move_title(nardy, {}, {"dice": [6, 6], "motion": {}}, ["dice", "roll"]) == "Дубль 6"


def _uno_two_cards() -> dict:
    state = deal_uno()
    state["hands"]["white"] = ["R5", "B2"]
    state["hands"]["black"] = ["R9"]
    state["discard"] = ["R1"]
    state["color"] = "R"
    state["deck"] = ["Y3", "B4", "G5"]
    state["to_move"] = "white"
    return state


def test_uno_without_a_call_waits_for_someone_else() -> None:
    from app.cards.uno import suggest

    played = play_uno(_uno_two_cards(), ["play", "R5"])
    assert played["hands"]["white"] == ["B2"]
    assert played["exposed"] == "white"
    assert played["acts"]["white"] == "play"
    assert played["said"] == []
    assert suggest(played, 5) == ["catch"]
    caught = play_uno(played, ["catch"])
    assert caught["hands"]["white"] == ["B2", "G5", "B4"]
    assert caught["acts"]["white"] == "miss"
    assert caught["to_move"] == "black"
    assert not caught.get("exposed")


def test_uno_neighbor_marks_two_cards_before_the_play() -> None:
    from app.cards.uno import chronicle, dumps, replay

    state = _uno_two_cards()
    marked = play_uno(state, ["catch", "black"])
    assert marked["called_out"] == "white"
    assert marked["hands"]["white"] == ["R5", "B2"]
    played = play_uno(marked, ["play", "R5"])
    assert played["hands"]["white"] == ["B2", "G5", "B4"]
    assert played["acts"]["white"] == "miss"
    restored = replay(dumps(state), [{"path": ["catch", "black"]}, {"path": ["play", "R5"]}])
    assert restored["hands"]["white"] == ["B2", "G5", "B4"]
    report = chronicle(dumps(state), [{"path": ["play", "R5"]}, {"path": ["catch"]}])
    assert report["counts"]["play"] == 1
    assert report["counts"]["miss"] == 1


def test_uno_own_button_cancels_the_neighbors_mark() -> None:
    marked = play_uno(_uno_two_cards(), ["catch"])
    safe = play_uno(marked, ["uno"])
    assert not safe.get("called_out")
    played = play_uno(safe, ["play", "R5"])
    assert played["hands"]["white"] == ["B2"]
    assert played["said"] == ["white"]
    assert not played.get("exposed")


def test_uno_next_move_closes_the_window() -> None:
    played = play_uno(_uno_two_cards(), ["play", "R5"])
    escaped = play_uno(played, ["play", "R9"])
    assert escaped["hands"]["white"] == ["B2"]
    assert not escaped.get("exposed")


def test_uno_view_keeps_ten_discards_and_offers_the_catch() -> None:
    from app.cards.uno import view

    state = _uno_two_cards()
    colors = ["R", "Y", "G", "B"]
    state["discard"] = [colors[index % 4] + str(index % 10) for index in range(12)]
    state["color"] = "B"
    seen = view(state, "black")
    assert len(seen["pile"]) == 10
    assert seen["pile"][0] == {"card": "G2", "n": 2}
    assert seen["pile"][-1]["n"] == 11
    assert seen["top"] == seen["pile"][-1]["card"]
    assert seen["actions"] == [{"path": ["catch"], "notation": "УНО", "promotion": None}]
    assert "Можно сказать Уно." in seen["message"]
    own = view(state, "white")
    assert ["catch"] not in [item["path"] for item in own["actions"]]
    assert ["uno"] in [item["path"] for item in own["actions"]]
