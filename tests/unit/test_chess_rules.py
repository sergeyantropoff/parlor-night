from __future__ import annotations

import chess
from app.chess.rules import (
    export_pgn,
    import_pgn,
    legal_records,
    outcome_of,
    parse_board,
    push_user_move,
    replay,
)


def test_scholars_mate_and_illegal_move() -> None:
    board = parse_board(chess.STARTING_FEN)
    for uci in ("e2e4", "e7e5", "f1c4", "b8c6", "d1h5", "g8f6", "h5f7"):
        push_user_move(board, [uci[:2], uci[2:4]], None)
    outcome = outcome_of(board)
    assert outcome is not None
    assert outcome.result == "white_win"
    assert outcome.reason == "checkmate"
    start = parse_board(chess.STARTING_FEN)
    try:
        push_user_move(start, ["e2", "e5"], None)
        raised = False
    except Exception:
        raised = True
    assert raised


def test_castling_en_passant_and_promotion() -> None:
    castle = parse_board("r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1")
    assert any(move.uci == "e1g1" for move in legal_records(castle))
    push_user_move(castle, ["e1", "g1"], None)
    assert castle.piece_at(chess.G1).piece_type == chess.KING

    blocked = parse_board("4k3/8/8/8/4q3/8/8/R3K2R w KQ - 0 1")
    assert all(move.uci != "e1g1" for move in legal_records(blocked))

    board = parse_board(chess.STARTING_FEN)
    for uci in ("e2e4", "e7e6", "e4e5", "d7d5"):
        push_user_move(board, [uci[:2], uci[2:4]], None)
    assert any(move.uci == "e5d6" for move in legal_records(board))
    push_user_move(board, ["e5", "d6"], None)
    assert board.piece_at(chess.D6).piece_type == chess.PAWN

    promo = parse_board("8/4P3/8/4k3/8/8/8/4K3 w - - 0 1")
    push_user_move(promo, ["e7", "e8"], "q")
    assert promo.piece_at(chess.E8).piece_type == chess.QUEEN


def test_stalemate_fen_and_pgn_roundtrip() -> None:
    stale = parse_board("7k/5Q2/6K1/8/8/8/8/8 b - - 0 1")
    outcome = outcome_of(stale)
    assert outcome is not None
    assert outcome.reason == "stalemate"
    text = export_pgn(chess.STARTING_FEN, ["e2e4", "e7e5"], white_name="Белые", black_name="Чёрные", result=None)
    initial, moves, board = import_pgn(text)
    assert initial == chess.STARTING_FEN
    assert [move.uci for move in moves] == ["e2e4", "e7e5"]
    assert board.fen() == replay(chess.STARTING_FEN, ["e2e4", "e7e5"]).fen()


def test_novice_budget_is_shallow_and_can_miss_the_best_line() -> None:
    import random

    from app.chess.engine import EngineLine, choose_line, level_budget

    time_s, depth, _skill, multipv, slack = level_budget(1, 1000, 3000)
    assert depth == 1
    assert multipv > 1
    assert slack > 0
    assert time_s < 0.5
    _time, master_depth, _skill, master_pv, master_slack = level_budget(5, 1000, 3000)
    assert master_depth >= 12
    assert master_pv == 1
    assert master_slack == 0

    def line(uci: str, score: int) -> EngineLine:
        return EngineLine(uci, uci, (uci[:2], uci[2:4]), None, score, None, (uci,), 1, 1)

    lines = [line("e2e4", 40), line("a2a4", -80), line("d1h5", -900)]
    chosen = {choose_line(lines, white_to_move=True, slack_cp=280, rng=random.Random(seed)).uci for seed in range(30)}
    assert chosen <= {"e2e4", "a2a4"}
    assert "a2a4" in chosen
    assert choose_line(lines, white_to_move=True, slack_cp=0).uci == "e2e4"
