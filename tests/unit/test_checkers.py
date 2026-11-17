from __future__ import annotations

import time

import pytest

from app.checkers.draws import NONPROGRESS_PLIES, REGULATION, repetition_draw
from app.checkers.engine import search, search_level
from app.checkers.evaluation import DEFAULT_WEIGHTS, EvalWeights, evaluate_white
from app.checkers.model import BLACK, WHITE, WHITE_KING, algebraic
from app.checkers.notation import format_algebraic, format_numeric, parse_notation
from app.checkers.rules import apply_move, legal_moves, move_from_path, outcome
from app.checkers.serialization import INITIAL_RCP, dump_rcp, initial_position, parse_rcp
from app.errors import AnalysisIncomplete, IllegalMove


def test_square_samples() -> None:
    assert algebraic(29) == "a1"
    assert algebraic(32) == "g1"
    assert algebraic(21) == "a3"
    assert algebraic(22) == "c3"
    assert algebraic(18) == "d4"
    assert algebraic(1) == "b8"
    assert algebraic(12) == "h6"


def test_initial_moves_match_russian_notation() -> None:
    paths = {move.path for move in legal_moves(initial_position())}
    assert paths == {
        (21, 17),
        (22, 17),
        (22, 18),
        (23, 18),
        (23, 19),
        (24, 19),
        (24, 20),
    }
    assert format_algebraic((22, 18), False) == "c3-d4"
    assert format_numeric((22, 18), False) == "22-18"


def test_man_moves_only_forward() -> None:
    pos = parse_rcp("w|18|K1|0")
    assert {move.path for move in legal_moves(pos)} == {(18, 14), (18, 15)}


def test_backward_capture_is_mandatory() -> None:
    pos = parse_rcp("w|18,32|22|0")
    moves = legal_moves(pos)
    assert {move.path for move in moves} == {(18, 25)}
    assert moves[0].victims == (22,)
    with pytest.raises(IllegalMove):
        move_from_path(pos, (32, 28))


def test_player_may_choose_any_capture() -> None:
    pos = parse_rcp("w|18|14,15|0")
    assert {move.path for move in legal_moves(pos)} == {(18, 9), (18, 11)}


def test_no_maximum_capture_rule() -> None:
    pos = parse_rcp("w|21,32|17,10,27|0")
    paths = {move.path for move in legal_moves(pos)}
    assert (21, 14, 7) in paths
    assert (32, 23) in paths
    assert (21, 14) not in paths
    assert {len(move.victims) for move in legal_moves(pos)} == {1, 2}


def test_promotion_continues_as_king() -> None:
    pos = parse_rcp("w|9|6,11|0")
    moves = legal_moves(pos)
    paths = {move.path for move in moves}
    assert (9, 2, 16) in paths
    assert (9, 2, 20) in paths
    assert (9, 2) not in paths
    assert all(move.final_piece == WHITE_KING for move in moves)
    chosen = move_from_path(pos, (9, 2, 16))
    assert chosen.victims == (6, 11)
    result = apply_move(pos, chosen)
    assert result.board[16] == WHITE_KING
    assert result.board[6] == 0
    assert result.board[11] == 0
    assert result.board[9] == 0
    assert result.side == BLACK
    assert result.clock == 0


def test_king_takes_distant_pieces_in_one_line() -> None:
    pos = parse_rcp("w|K29|22,15|0")
    moves = legal_moves(pos)
    assert {move.path for move in moves} == {(29, 18, 11), (29, 18, 8), (29, 18, 4)}
    assert all(move.victims == (22, 15) for move in moves)
    landed = apply_move(pos, move_from_path(pos, (29, 18, 4)))
    assert landed.board[4] == WHITE_KING
    assert landed.board[22] == 0
    assert landed.board[15] == 0


def test_king_long_move_and_long_capture() -> None:
    quiet = parse_rcp("w|K29|K1|0")
    assert {move.path for move in legal_moves(quiet)} == {
        (29, 25),
        (29, 22),
        (29, 18),
        (29, 15),
        (29, 11),
        (29, 8),
        (29, 4),
    }
    capture = parse_rcp("w|K29|22|0")
    moves = legal_moves(capture)
    assert {move.path for move in moves} == {
        (29, 18),
        (29, 15),
        (29, 11),
        (29, 8),
        (29, 4),
    }
    assert all(move.victims == (22,) for move in moves)


def test_same_piece_is_not_captured_twice() -> None:
    positions = [
        initial_position(),
        parse_rcp("w|K18|7,10,14,15,22|0"),
        parse_rcp("w|9|6,11|0"),
        parse_rcp("b|K32,K29|K1,K4|3"),
    ]
    for pos in positions:
        for move in legal_moves(pos):
            assert len(move.victims) == len(set(move.victims))


def test_black_can_capture_backwards() -> None:
    pos = parse_rcp("b|10|14|0")
    assert {move.path for move in legal_moves(pos)} == {(14, 7)}


def test_no_moves_is_a_loss() -> None:
    pos = parse_rcp("b|21||0")
    result = outcome(pos, [pos.placement_key()], 0)
    assert result is not None
    assert result.result == "white_win"
    assert result.reason == "no_moves"


def test_draw_rules_are_explicit() -> None:
    assert NONPROGRESS_PLIES == 30
    assert "30" in REGULATION
    assert "троекратн" in REGULATION.lower()
    stalled = parse_rcp("w|K32|K1|30")
    result = outcome(stalled, [stalled.placement_key()], 8)
    assert result is not None
    assert result.result == "draw"
    assert result.reason == "nonprogress"
    fresh = parse_rcp("w|K32|K1|29")
    assert outcome(fresh, [fresh.placement_key()], 8) is None


def test_threefold_repetition() -> None:
    pos = parse_rcp("w|K32|K1|0")
    history = [pos.placement_key()]
    sequence = [(32, 28), (1, 5), (28, 32), (5, 1)]
    seen = None
    for _ in range(2):
        for path in sequence:
            move = move_from_path(pos, path)
            pos = apply_move(pos, move)
            history.append(pos.placement_key())
            seen = outcome(pos, history, len(history) - 1)
            if seen is not None:
                break
        if seen is not None:
            break
    assert seen is not None
    assert seen.reason == "repetition"
    assert repetition_draw(history)


def test_clock_tracks_man_moves_and_king_moves() -> None:
    kings = parse_rcp("w|K32|K1|4")
    after_king = apply_move(kings, move_from_path(kings, (32, 28)))
    assert after_king.clock == 5
    men = parse_rcp("w|21|K1|4")
    after_man = apply_move(men, move_from_path(men, (21, 17)))
    assert after_man.clock == 0


def test_rcp_roundtrip_and_rejection_of_fen() -> None:
    pos = parse_rcp("w|32,K21|K2,3|4")
    assert dump_rcp(pos) == "w|K21,32|K2,3|4"
    assert dump_rcp(parse_rcp(INITIAL_RCP)) == INITIAL_RCP
    with pytest.raises(ValueError):
        parse_rcp("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1")
    with pytest.raises(ValueError):
        parse_rcp("w|21,21|1|0")


def test_notation_parser() -> None:
    assert parse_notation("22-18") == (22, 18)
    assert parse_notation("21:14:7") == (21, 14, 7)
    assert parse_notation("21x14x7") == (21, 14, 7)


def test_material_and_weights() -> None:
    rich = parse_rcp("w|21,22|1|0")
    poor = parse_rcp("w|21|1,2|0")
    assert evaluate_white(rich) > evaluate_white(poor)
    heavy = EvalWeights(man=500)
    light = EvalWeights(man=10)
    assert evaluate_white(rich, heavy) != evaluate_white(rich, light)


def test_engine_finds_obvious_capture_and_stays_legal() -> None:
    pos = parse_rcp("w|21,32|17|0")
    result = search(pos, max_depth=2, time_ms=3000, weights=DEFAULT_WEIGHTS)
    legal = {move.path for move in legal_moves(pos)}
    assert result.move.path in legal
    assert result.move.is_capture
    assert result.move.path[0] == 21


def test_engine_is_deterministic_without_variety() -> None:
    pos = initial_position()
    first = search(pos, max_depth=3, time_ms=5000, variety=False)
    second = search(pos, max_depth=3, time_ms=5000, variety=False)
    assert first.move == second.move
    assert first.nodes == second.nodes
    assert first.score_white == second.score_white
    assert first.depth == second.depth


def test_engine_respects_time_and_depth() -> None:
    pos = initial_position()
    started = time.perf_counter()
    result = search(pos, max_depth=30, time_ms=80)
    elapsed = time.perf_counter() - started
    assert elapsed < 2
    assert 1 <= result.depth < 30
    assert result.move.path in {move.path for move in legal_moves(pos)}
    with pytest.raises(AnalysisIncomplete):
        search(pos, max_depth=3, time_ms=0)


def test_slack_does_not_leave_the_best_window() -> None:
    from app.checkers.engine import _slack_move
    from app.checkers.evaluation import DEFAULT_WEIGHTS, evaluate
    from app.checkers.rules import apply_move

    pos = initial_position()
    scores = [-evaluate(apply_move(pos, move), DEFAULT_WEIGHTS) for move in legal_moves(pos)]
    top = max(scores)
    for _ in range(20):
        chosen = _slack_move(pos, DEFAULT_WEIGHTS, 15)
        after = -evaluate(apply_move(pos, chosen), DEFAULT_WEIGHTS)
        assert top - after <= 15


def test_weak_levels_return_legal_moves() -> None:
    pos = initial_position()
    legal = {move.path for move in legal_moves(pos)}
    for level in (1, 2):
        result = search_level(pos, level, variety=False)
        assert result.move.path in legal
        assert result.depth <= {1: 1, 2: 2}[level]


def test_variety_stays_inside_legal_moves() -> None:
    pos = parse_rcp("w|21,32|17|0")
    legal = {move.path for move in legal_moves(pos)}
    result = search(pos, max_depth=2, time_ms=2000, variety=True)
    assert result.move.path in legal


def test_side_constants_cover_both_players() -> None:
    assert WHITE == 0
    assert BLACK == 1
