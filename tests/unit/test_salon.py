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
from app.cards.preferans import stack_for as preferans_stack
from app.cards.preferans import suggest as suggest_preferans
from app.cards.preferans import view as view_preferans
from app.games.present import _preferans_marks


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
    assert opening["contract_need"] is None
    assert opening["declarer"] == ""
    assert opening["tricks"] == {"p0": 0, "p1": 0, "p2": 0}
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
    assert shown["held"] is True
    assert shown["board"] == list(state["last_trick"])
    assert len(shown["board"]) == 3
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


def test_preferans_names_who_took_the_trick_and_what_was_written() -> None:
    state = deal_preferans(["p0", "p1", "p2"], "pool-12")
    state["phase"] = "play"
    state["contract"] = {"level": 6, "suit": "S"}
    state["declarer"] = "p0"
    state["trump"] = "S"
    state["hands"] = {"p0": [], "p1": [], "p2": ["9H"]}
    state["trick"] = ["7H", "8H"]
    state["trick_seats"] = ["p0", "p1"]
    state["tricks"] = {"p0": 6, "p1": 0, "p2": 0}
    state["to_move"] = "p2"
    state["whist"] = {"p1": "yes", "p2": "no"}
    state, _charges = play_preferans(state, ["play", "9H"])
    assert state["last_trick_winner"] == "p2"
    assert state["last_trick_seats"] == ["p0", "p1", "p2"]
    assert state["last_write"]["p0"] == "bullet"
    shown = view_preferans(state, "p0")
    assert shown["writes"]["p0"] == "bullet"
    assert shown["held"] is True
    assert shown["board"] == ["7H", "8H", "9H"]
    assert shown["trick_winner"] == "p2"
    assert shown["previous"]["winner"] == "p2"
    state, _charges = play_preferans(state, ["bid", "pass"])
    assert view_preferans(state, "p0")["writes"] == {}
    assert view_preferans(state, "p0")["previous"] == {}


def test_preferans_keeps_the_previous_trick_while_the_next_one_starts() -> None:
    state = deal_preferans(["p0", "p1", "p2"], "pool-12")
    state["phase"] = "play"
    state["contract"] = {"level": 6, "suit": "S"}
    state["declarer"] = "p0"
    state["trump"] = "S"
    state["hands"] = {"p0": ["AS"], "p1": ["KS"], "p2": ["9H", "QS"]}
    state["trick"] = ["7H", "8H"]
    state["trick_seats"] = ["p0", "p1"]
    state["tricks"] = {"p0": 0, "p1": 0, "p2": 0}
    state["to_move"] = "p2"
    state, _charges = play_preferans(state, ["play", "9H"])
    state["trick"] = ["7S"]
    state["trick_seats"] = ["p0"]
    shown = view_preferans(state, "p1")
    assert shown["held"] is False
    assert shown["board"] == ["7S"]
    assert shown["previous"]["winner"] == "p2"
    assert shown["previous"]["cards"] == ["7H", "8H", "9H"]


def _durak_taking(variant: str = "podkidnoy") -> dict:
    state = deal_durak(["p0", "p1", "p2"], variant)
    state["trump"] = "H"
    state["trump_card"] = "AH"
    state["deck"] = ["KH"]
    state["hands"] = {"p0": ["8D", "8C", "9C"], "p1": ["6C"], "p2": ["8S", "QD", "7D"]}
    state["table"] = [{"attack": "8H", "defense": ""}]
    state["attacker"] = "p0"
    state["opener"] = "p0"
    state["defender"] = "p1"
    state["to_move"] = "p1"
    state["phase"] = "defend"
    state["passed"] = []
    state["taking"] = False
    state["out"] = []
    state["result"] = None
    return state


def test_durak_old_games_take_without_extra_cards() -> None:
    state = _durak_taking()
    state["add_after_take"] = False
    state = play_durak(state, ["act", "take"])
    assert state["phase"] == "attack"
    assert state["taking"] is False
    assert "8H" in state["hands"]["p1"]


def test_durak_lets_players_add_cards_after_a_take() -> None:
    state = play_durak(_durak_taking(), ["act", "take"])
    assert state["phase"] == "throw"
    assert state["taking"] is True
    assert state["to_move"] == "p0"
    assert state["table"] == [{"attack": "8H", "defense": ""}]
    assert "8H" not in state["hands"]["p1"]
    paths = [item["path"] for item in legal_durak(state)]
    assert ["play", "8D"] in paths
    assert ["play", "9C"] not in paths
    assert ["act", "pass"] in paths
    assert legal_durak(state)[-1]["notation"] == "Хватит"
    state = play_durak(state, ["play", "8D"])
    assert state["to_move"] == "p0"
    assert state["taking"] is True
    state = play_durak(state, ["play", "8C"])
    assert state["to_move"] == "p2"
    state = play_durak(state, ["play", "8S"])
    assert state["phase"] == "attack"
    assert state["taking"] is False
    assert state["last_bout"] == {"kind": "take", "seat": "p1"}
    assert state["hands"]["p1"] == ["6C", "8H", "8D", "8C", "8S"]
    assert "KH" in state["hands"]["p0"]


def test_durak_take_stops_at_six_foreign_cards_of_every_rank() -> None:
    state = _durak_taking()
    state["deck"] = []
    state["hands"] = {
        "p0": ["9C", "7C", "6D", "TS", "JC", "QC"],
        "p1": ["KH"],
        "p2": ["9D", "QD"],
    }
    state["table"] = [
        {"attack": "9S", "defense": "QH"},
        {"attack": "7S", "defense": ""},
    ]
    state = play_durak(state, ["act", "take"])
    assert state["to_move"] == "p0"
    offered = {item["path"][1] for item in legal_durak(state) if item["path"][0] == "play"}
    assert offered == {"9C", "7C", "QC"}
    state = play_durak(state, ["play", "9C"])
    state = play_durak(state, ["play", "7C"])
    state = play_durak(state, ["play", "QC"])
    assert state["to_move"] == "p2"
    assert len(state["table"]) == 5
    state = play_durak(state, ["play", "9D"])
    assert state["phase"] == "attack"
    assert state["taking"] is False
    assert len(state["last_table"]) == 6
    assert "QD" in state["hands"]["p2"]
    assert state["hands"]["p1"].count("QH") == 1
    assert sum(1 for card in state["hands"]["p1"] if card not in {"KH", "QH"}) == 6


def test_durak_take_asks_the_first_attacker_before_the_others() -> None:
    state = _durak_taking("perevodnoy")
    state["attacker"] = "p1"
    state["opener"] = "p0"
    state["defender"] = "p2"
    state["to_move"] = "p2"
    state["hands"] = {"p0": ["8D"], "p1": ["8C", "6D"], "p2": ["6C"]}
    state = play_durak(state, ["act", "take"])
    assert state["to_move"] == "p0"
    state = play_durak(state, ["act", "pass"])
    assert state["to_move"] == "p1"
    assert ["play", "8C"] in [item["path"] for item in legal_durak(state)]
    state = play_durak(state, ["act", "pass"])
    assert state["phase"] == "attack"
    assert state["hands"]["p2"] == ["6C", "8H"]


def test_perevodnoy_adds_only_the_attacker_until_someone_takes() -> None:
    state = _durak_taking("perevodnoy")
    state["hands"] = {"p0": ["8D", "8C"], "p1": ["9D", "6C"], "p2": ["8S"]}
    state["table"] = []
    state["phase"] = "attack"
    state["to_move"] = "p0"
    state["deck"] = []
    state = play_durak(state, ["play", "8D"])
    state = play_durak(state, ["play", "9D"])
    assert state["phase"] == "throw"
    assert state["taking"] is False
    assert state["to_move"] == "p0"
    state = play_durak(state, ["act", "pass"])
    assert state["phase"] == "attack"
    assert state["last_bout"]["kind"] == "bito"
    assert "8S" in state["hands"]["p2"]


def test_durak_shows_who_finished_the_bout() -> None:
    from app.cards.durak import view as view_durak

    state = deal_durak(["white", "black"], "podkidnoy")
    state["phase"] = "attack"
    state["table"] = []
    state["last_table"] = [{"attack": "7S", "defense": "8S"}]
    state["last_bout"] = {"kind": "bito", "seat": "black"}
    shown = view_durak(state, "white")
    assert shown["held"] is True
    assert shown["bout"] == {"kind": "bito", "seat": "black"}
    state["table"] = [{"attack": "9C", "defense": ""}]
    live = view_durak(state, "white")
    assert live["bout"] == {}
    assert live["previous"]["kind"] == "bito"
    assert live["previous"]["pairs"] == [{"attack": "7S", "defense": "8S"}]


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


def test_preferans_can_raise_the_contract_after_the_talon() -> None:
    state = deal_preferans(["p0", "p1", "p2"], "pool-12")
    state["phase"] = "discard"
    state["to_move"] = "p0"
    state["declarer"] = "p0"
    state["contract"] = {"level": 6, "suit": "S"}
    state["trump"] = "S"
    state["hands"]["p0"] = ["AS", "KS", "QS", "JS", "TS", "9S", "8S", "7S", "AH", "KH", "AD", "KD"]
    paths = [item["path"] for item in legal_preferans(state)]
    assert ["bid", "6", "D"] in paths
    assert ["bid", "7", "C"] in paths
    assert ["bid", "6", "S"] not in paths
    assert ["bid", "6", "C"] in paths
    assert ["bid", "pass"] not in paths
    raised, _charges = play_preferans(state, ["bid", "6", "D"])
    assert raised["phase"] == "discard"
    assert raised["contract"] == {"level": 6, "suit": "D"}
    assert raised["trump"] == "D"
    assert len(raised["hands"]["p0"]) == 12
    assert ["bid", "6", "S"] not in [item["path"] for item in legal_preferans(raised)]
    assert suggest_preferans(raised, 1)[0] == "discard"


def _preferans_bank(stake: int = 2, bank: int = 50) -> dict:
    state = deal_preferans(["p0", "p1", "p2"], "pool-12", {"p0": bank, "p1": bank, "p2": bank})
    state["stake"] = stake
    state["bullet"] = {"p0": 0, "p1": 0, "p2": 0}
    state["mountain"] = {"p0": 0, "p1": 0, "p2": 0}
    state["whists"] = {
        seat: {other: 0 for other in state["order"] if other != seat} for seat in state["order"]
    }
    return state


def test_preferans_stack_follows_the_point_price() -> None:
    assert [preferans_stack(price) for price in (1, 2, 5, 10)] == [100, 200, 500, 1000]
    assert preferans_stack("нет") == 100


def test_preferans_keeps_the_players_own_chips() -> None:
    state = deal_preferans(["p0", "p1", "p2"], "pool-12", {"p0": 80})
    assert state["stake"] == 1
    assert state["stacks"] == {"p0": 80, "p1": 1000, "p2": 1000}
    assert state["committed"] == {"p0": 0, "p1": 0, "p2": 0}
    shown = view_preferans(state, "p0")
    assert shown["stacks"] == state["stacks"]
    assert shown["sheet"]["stake"] == 1
    assert shown["sheet"]["stacks"] == state["stacks"]
    before = dict(state["stacks"])
    path = suggest_preferans(state, 1)
    state, charges = play_preferans(state, path)
    assert charges == []
    assert state["stacks"] == before


def test_preferans_sheet_settles_to_zero_and_names_a_short_stack() -> None:
    from app.cards.preferans import _redeal

    even = _preferans_bank()
    for seat in even["order"]:
        even["bullet"][seat] = 12
    finish_preferans(even)
    assert even["chips"] == {"p0": 0, "p1": 0, "p2": 0}
    assert even["stacks"] == {"p0": 50, "p1": 50, "p2": 50}
    assert even["payout"] == even["stacks"]
    assert even["unpaid"] == {"p0": 0, "p1": 0, "p2": 0}

    played = _preferans_bank(2, 50)
    played["bullet"] = {"p0": 12, "p1": 12, "p2": 12}
    played["mountain"]["p2"] = 10
    finish_preferans(played)
    assert played["chips"] == {"p0": 7, "p1": 7, "p2": -14}
    assert played["stacks"] == {"p0": 57, "p1": 57, "p2": 36}
    assert sum(played["stacks"].values()) == 150
    assert played["unpaid"] == {"p0": 0, "p1": 0, "p2": 0}

    short = _preferans_bank(2, 50)
    short["stacks"] = {"p0": 50, "p1": 50, "p2": 5}
    short["bullet"] = {"p0": 12, "p1": 12, "p2": 12}
    short["mountain"]["p2"] = 10
    finish_preferans(short)
    assert short["stacks"] == {"p0": 53, "p1": 52, "p2": 0}
    assert sum(short["stacks"].values()) == 105
    assert short["unpaid"] == {"p0": 4, "p1": 5, "p2": 9}
    assert "не хватило" in short["line"]
    assert short["sheet"]["chips"]["p2"] == short["chips"]["p2"]

    kept = _preferans_bank(5, 40)
    before = dict(kept["stacks"])
    _redeal(kept)
    assert kept["stacks"] == before
    assert kept["stake"] == 5


def test_preferans_without_a_stake_keeps_the_old_payout() -> None:
    state = deal_preferans(["p0", "p1", "p2"], "pool-12")
    state.pop("stake")
    state.pop("stacks")
    for seat in state["order"]:
        state["bullet"][seat] = 12
    finish_preferans(state)
    assert state["payout"] == {"p0": 10, "p1": 10, "p2": 10}


def test_preferans_view_shows_pass_and_whist() -> None:
    state = deal_preferans(["p0", "p1", "p2"], "pool-12")
    state["phase"] = "play"
    state["bidding"] = {"p0": "bid", "p1": "passed", "p2": "passed"}
    state["whist"] = {"p1": "yes", "p2": "half"}
    shown = view_preferans(state, "p0")
    assert shown["bidding"]["p0"] == "bid"
    assert shown["whist"] == {"p1": "yes", "p2": "half"}
    assert _preferans_marks(shown) == {"p1": "whist", "p2": "half"}
    state["whist"] = {"p1": "no"}
    answered = view_preferans(state, "p2")
    assert _preferans_marks(answered) == {"p1": "pass-whist", "p2": "pass"}
