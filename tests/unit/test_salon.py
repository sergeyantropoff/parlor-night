"""Партии дурака, блэкджека и преферанса доигрываются до результата."""

from app.cards.blackjack import apply as play_blackjack
from app.cards.blackjack import deal as deal_blackjack
from app.cards.blackjack import legal as legal_blackjack
from app.cards.blackjack import suggest as suggest_blackjack
from app.cards.durak import apply as play_durak
from app.cards.durak import deal as deal_durak
from app.cards.durak import legal as legal_durak
from app.cards.preferans import _finish as finish_preferans
from app.cards.preferans import apply as play_preferans
from app.cards.preferans import deal as deal_preferans
from app.cards.preferans import legal as legal_preferans
from app.cards.preferans import suggest as suggest_preferans
from app.cards.preferans import view as view_preferans


def _until_done(state: dict, legal, suggest, apply, limit: int = 240) -> dict:
    for _ in range(limit):
        if state.get("result"):
            return state
        path = suggest(state, 4)
        assert path, state.get("phase")
        assert list(path) in [list(item["path"]) for item in legal(state)]
        played = apply(state, path)
        state = played[0] if isinstance(played, tuple) else played
    raise AssertionError(state.get("phase"))


def test_durak_names_the_fool_when_several_players_get_out() -> None:
    from app.cards.durak import _finish

    state = deal_durak(["p0", "p1", "p2"], "podkidnoy")
    state["deck"] = []
    state["hands"] = {"p0": [], "p1": ["6H", "7D"], "p2": []}
    state["out"] = ["p0", "p2"]
    state["result"] = None
    state["phase"] = "discard"
    _finish(state)
    assert state["reason"] == "durak"
    assert state["loser"] == "p1"
    assert state["result"] == "draw"


def test_durak_variants_finish() -> None:
    for variant in ("podkidnoy", "perevodnoy"):
        for seats in (["white", "black"], ["p0", "p1", "p2"]):
            state = deal_durak(seats, variant)
            assert state["trump"]
            assert sum(len(cards) for cards in state["hands"].values()) == min(36, 6 * len(seats))
            finished = _until_done(state, legal_durak, __import__("app.cards.durak", fromlist=["suggest"]).suggest, play_durak)
            assert finished["result"] in {"white_win", "black_win", "draw", "p0_win", "p1_win", "p2_win"}


def test_perevodnoy_can_offer_a_transfer() -> None:
    state = deal_durak(["white", "black"], "perevodnoy")
    state["hands"]["white"] = ["7S", "8S", "9S", "TH"]
    state["hands"]["black"] = ["7H", "KH", "9C", "6C", "5C", "QC"]
    state["trump"] = "D"
    state["table"] = []
    state["phase"] = "attack"
    state["attacker"] = "white"
    state["defender"] = "black"
    state["to_move"] = "white"
    state["deck"] = ["6D"]
    state, = (play_durak(state, ["play", "7S"]),)
    paths = [item["path"] for item in legal_durak(state)]
    assert ["play", "7H"] in paths
    transferred = play_durak(state, ["play", "7H"])
    assert transferred["defender"] == "white"
    assert len(transferred["table"]) == 2


def test_podkidnoy_does_not_transfer() -> None:
    state = deal_durak(["white", "black"], "podkidnoy")
    state["hands"]["white"] = ["7S"]
    state["hands"]["black"] = ["7H", "KH"]
    state["trump"] = "D"
    state["table"] = [{"attack": "7S", "defense": ""}]
    state["phase"] = "defend"
    state["attacker"] = "white"
    state["defender"] = "black"
    state["to_move"] = "black"
    state["deck"] = ["6D"]
    paths = [item["path"] for item in legal_durak(state)]
    assert ["play", "7H"] not in paths
    assert ["act", "take"] in paths


def test_blackjack_deals_and_pays() -> None:
    state = deal_blackjack(["white"], purses={"white": 100})
    assert state["phase"] == "bet"
    state, charges = play_blackjack(state, ["bet", "25"])
    assert charges == [("white", 25)]
    assert len(state["hands"]["white"]) == 2
    assert len(state["dealer"]) == 2
    finished = _until_done(state, legal_blackjack, suggest_blackjack, play_blackjack)
    assert finished["phase"] == "done"
    assert finished["result"] in {"white_win", "black_win", "draw"}
    assert "white" in finished["payout"]


def test_blackjack_novice_dealer_stands_on_fifteen() -> None:
    state = deal_blackjack(["white"], purses={"white": 100})
    state["level"] = 1
    state["phase"] = "play"
    state["to_move"] = "white"
    state["hands"]["white"] = ["TH", "9C"]
    state["dealer"] = ["9S", "6D"]
    state["deck"] = ["2C", "KS"]
    state["committed"] = {"white": 25}
    state["stacks"]["white"] = 75
    finished, _charges = play_blackjack(state, ["act", "stand"])
    assert finished["dealer"] == ["9S", "6D"]


def test_blackjack_report_names_every_winner() -> None:
    from app.cards.blackjack import chronicle, dumps
    from app.games.present import _parlor_summary

    state = deal_blackjack(["white", "black", "p2"], purses={"white": 100, "black": 100, "p2": 100})
    state["phase"] = "done"
    state["reason"] = "showdown"
    state["result"] = "draw"
    state["committed"] = {"white": 25, "black": 50, "p2": 25}
    state["payout"] = {"white": 50, "black": 0, "p2": 62}
    state["hands"] = {"white": ["TH", "9C"], "black": ["KH", "6C", "7D"], "p2": ["AS", "KD"]}
    state["dealer"] = ["9S", "8D"]
    state["hole"] = False
    report = chronicle(dumps(state), [], state)
    assert report["winners"] == ["white", "p2"]
    assert report["notes"]["white"] == "выиграл · ставка 25"
    assert report["notes"]["black"] == "перебор · ставка 50"
    assert report["notes"]["p2"] == "блэкджек · ставка 25"
    assert report["detail"] == "Дилер: 17."
    seats = [
        {"key": "white", "name": "Сережа"},
        {"key": "black", "name": "Анна"},
        {"key": "p2", "name": "Павел"},
    ]
    summary = _parlor_summary("blackjack", report, seats, {})
    assert summary["headline"] == "Победители — Сережа и Павел."
    assert summary["detail"] == "Дилер: 17."
    assert summary["winners"] == ["white", "p2"]
    assert [seat["note"] for seat in summary["seats"]] == [
        "выиграл · ставка 25",
        "перебор · ставка 50",
        "блэкджек · ставка 25",
    ]

    state["payout"] = {"white": 0, "black": 0, "p2": 0}
    state["dealer"] = ["KS", "QD"]
    lost = chronicle(dumps(state), [], state)
    lost_summary = _parlor_summary("blackjack", lost, seats, {})
    assert lost_summary["headline"] == "Победитель — дилер."
    assert lost_summary["detail"] == "Дилер: 20."
    assert lost_summary["winners"] == []

    state["payout"] = {"white": 25, "black": 50, "p2": 25}
    state["hands"]["black"] = ["KH", "7C"]
    state["dealer"] = ["QS", "7D"]
    pushed = chronicle(dumps(state), [], state)
    assert _parlor_summary("blackjack", pushed, seats, {})["headline"] == "Ничья с дилером."


def test_preferans_reaches_a_score() -> None:
    state = deal_preferans(["p0", "p1", "p2"], "pool-6")
    assert state["pool"] == 6
    opening = view_preferans(state, "p0")
    assert opening["scored"] is False
    assert opening["note"] == ""
    assert opening["sheet"]["pool"] == 6
    assert opening["sheet"]["total"] == {"p0": 0, "p1": 0, "p2": 0}
    assert len(state["talon"]) == 2
    assert all(len(cards) == 10 for cards in state["hands"].values())
    for _ in range(160):
        if int(state.get("deals") or 1) >= 2 and state.get("phase") == "bid":
            break
        path = suggest_preferans(state, 4)
        assert path
        assert list(path) in [list(item["path"]) for item in legal_preferans(state)]
        state, _charges = play_preferans(state, path)
    assert int(state["deals"]) >= 2
    assert sum(state["bullet"].values()) + sum(state["mountain"].values()) > 0
    shown = view_preferans(state, "p0")
    assert shown["scored"] is True
    assert shown["note"]
    assert shown["sheet"]["bullet"] == state["bullet"]
    assert shown["sheet"]["mountain"] == state["mountain"]
    assert set(shown["sheet"]["total"]) == set(state["order"])
    assert shown["board"] == []
    for seat in state["order"]:
        state["bullet"][seat] = int(state["pool"])
    finish_preferans(state)
    assert state["phase"] == "done"
    assert state["sheet"]["closed"] is True
    assert all(int(state["sheet"]["bullet"][seat]) >= 6 for seat in state["sheet"]["seats"])
    assert sum(state["payout"].values()) > 0


def test_preferans_summary_names_who_won() -> None:
    from app.cards.preferans import chronicle, dumps

    state = deal_preferans(["p0", "p1", "p2"], "pool-6")
    state["bullet"] = {"p0": 6, "p1": 6, "p2": 2}
    state["mountain"] = {"p0": 0, "p1": 4, "p2": 0}
    finish_preferans(state)
    report = chronicle(dumps(state), [], state)
    assert report["sheet"]["closed"] is True
    assert report["sheet"]["bullet"]["p0"] == 6
    assert report["notes"]["p0"].startswith("выиграл")
    assert report["notes"]["p1"].startswith("проиграл")
    assert report["notes"]["p2"].startswith("проиграл")


def test_preferans_previous_deal_is_marked() -> None:
    state = deal_preferans(["p0", "p1", "p2"], "pool-12")
    state["deals"] = 2
    state["line"] = "6 пики не взята: 5 из 6."
    missed = view_preferans(state, "p0")
    assert missed["note"] == "6 пики не взята: 5 из 6."
    assert missed["note_tone"] == "miss"
    state["line"] = "6 пики взята: 6 из 6."
    assert view_preferans(state, "p0")["note_tone"] == "made"
    state["line"] = "Распасы записаны в гору."
    assert view_preferans(state, "p0")["note_tone"] == "draw"


def test_preferans_hand_is_sorted_by_suit() -> None:
    state = deal_preferans(["p0", "p1", "p2"], "pool-12")
    state["hands"]["p0"] = ["7H", "AS", "9C", "KH", "TS", "8D", "QC", "JD", "7S", "AH"]
    shown = view_preferans(state, "p0")
    assert shown["hand"] == ["AS", "TS", "7S", "QC", "9C", "JD", "8D", "AH", "KH", "7H"]
    state["hands"]["p0"].extend(["KC", "9H"])
    with_talon = view_preferans(state, "p0")
    assert with_talon["hand"] == ["AS", "TS", "7S", "KC", "QC", "9C", "JD", "8D", "AH", "KH", "9H", "7H"]


def test_preferans_half_whist_plays_the_hand_and_writes_half() -> None:
    from app.cards.preferans import _award_whists, _whist_points

    state = deal_preferans(["p0", "p1", "p2"], "pool-12")
    state["phase"] = "whist"
    state["to_move"] = "p1"
    state["declarer"] = "p0"
    state["contract"] = {"level": 6, "suit": "S"}
    state["trump"] = "S"
    state["hands"]["p1"] = ["AD", "7D", "8D", "9D", "7C", "8C", "9C", "7H", "8H", "9H"]
    kept = list(state["hands"]["p0"])
    assert suggest_preferans(state, 1) == ["whist", "half"]
    assert ["whist", "half"] in [item["path"] for item in legal_preferans(state)]
    state, _charges = play_preferans(state, ["whist", "half"])
    state, _charges = play_preferans(state, ["whist", "no"])
    assert state["phase"] == "play"
    assert int(state["deals"]) == 1
    assert state["hands"]["p0"] == kept
    assert _whist_points("half", 1) == 1
    assert _whist_points("half", 3) == 2
    state["tricks"] = {"p0": 6, "p1": 3, "p2": 2}
    _award_whists(state, "p0")
    assert state["whists"]["p1"]["p0"] == 2
    assert state["whists"]["p2"]["p0"] == 0


def test_preferans_discard_keeps_the_hand_when_a_defender_can_whist() -> None:
    state = deal_preferans(["p0", "p1", "p2"], "pool-12")
    state["phase"] = "whist"
    state["to_move"] = "p1"
    state["declarer"] = "p0"
    state["contract"] = {"level": 6, "suit": "S"}
    state["trump"] = "S"
    state["bidding"] = {"p0": "bid", "p1": "passed", "p2": "passed"}
    state["hands"] = {
        "p0": ["AS", "QH", "7H", "KH", "JS", "AC", "7D", "AH", "AD", "QC"],
        "p1": ["8S", "8D", "8H", "QD", "TC", "9S", "KD", "KS", "JC", "QS"],
        "p2": ["7C", "KC", "7S", "9C", "9H", "JH", "TS", "TH", "TD", "JD"],
    }
    kept = list(state["hands"]["p0"])
    assert suggest_preferans(state, 1) == ["whist", "yes"]
    state, _charges = play_preferans(state, ["whist", "yes"])
    assert state["phase"] == "whist"
    assert int(state["deals"]) == 1
    assert state["hands"]["p0"] == kept
    state, _charges = play_preferans(state, suggest_preferans(state, 1) or [])
    assert state["phase"] == "play"
    assert state["hands"]["p0"] == kept


def test_preferans_blank_hands_pass_and_say_why() -> None:
    state = deal_preferans(["p0", "p1", "p2"], "pool-12")
    state["phase"] = "whist"
    state["to_move"] = "p1"
    state["declarer"] = "p0"
    state["contract"] = {"level": 6, "suit": "S"}
    state["trump"] = "S"
    state["hands"]["p1"] = ["7D", "8D", "9D", "TD", "7C", "8C", "9C", "7H", "8H", "9H"]
    state["hands"]["p2"] = ["JD", "QD", "JC", "QC", "JH", "QH", "TC", "TH", "TD", "JS"]
    assert suggest_preferans(state, 1) == ["whist", "no"]
    state, _charges = play_preferans(state, ["whist", "no"])
    state, _charges = play_preferans(state, ["whist", "no"])
    assert state["phase"] == "bid"
    assert int(state["deals"]) == 2
    assert "без розыгрыша" in state["line"]
