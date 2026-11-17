"""Правила шахмат через python-chess. Клиентская доска не является источником истины."""

from __future__ import annotations

import io
from dataclasses import dataclass

import chess.pgn

import chess
from app.errors import IllegalMove

STARTING_FEN = chess.STARTING_FEN

_PIECE_NAMES = {
    "P": ("белая пешка", "чёрная пешка"),
    "N": ("белый конь", "чёрный конь"),
    "B": ("белый слон", "чёрный слон"),
    "R": ("белая ладья", "чёрная ладья"),
    "Q": ("белый ферзь", "чёрный ферзь"),
    "K": ("белый король", "чёрный король"),
}

_TERMINATION = {
    chess.Termination.CHECKMATE: "checkmate",
    chess.Termination.STALEMATE: "stalemate",
    chess.Termination.INSUFFICIENT_MATERIAL: "insufficient_material",
    chess.Termination.SEVENTYFIVE_MOVES: "seventyfive_moves",
    chess.Termination.FIVEFOLD_REPETITION: "fivefold_repetition",
    chess.Termination.FIFTY_MOVES: "fifty_moves",
    chess.Termination.THREEFOLD_REPETITION: "threefold_repetition",
}


@dataclass(frozen=True, slots=True)
class ChessMove:
    uci: str
    san: str
    path: tuple[str, str]
    promotion: str | None


@dataclass(frozen=True, slots=True)
class ChessOutcome:
    result: str
    reason: str


def parse_board(fen: str) -> chess.Board:
    try:
        board = chess.Board(fen)
    except ValueError as exc:
        raise IllegalMove("Некорректная позиция FEN.") from exc
    if not board.is_valid():
        raise IllegalMove("Позиция FEN противоречит правилам.")
    return board


def side_to_move(fen: str) -> str:
    return "white" if parse_board(fen).turn == chess.WHITE else "black"


def check_square(board: chess.Board) -> str | None:
    if not board.is_check():
        return None
    king = board.king(board.turn)
    if king is None:
        return None
    return chess.square_name(king)


def outcome_of(board: chess.Board) -> ChessOutcome | None:
    if not board.is_game_over(claim_draw=True):
        return None
    result = board.outcome(claim_draw=True)
    if result is None:
        return None
    if result.winner is True:
        winner = "white_win"
    elif result.winner is False:
        winner = "black_win"
    else:
        winner = "draw"
    reason = _TERMINATION.get(result.termination, "finished")
    return ChessOutcome(winner, reason)


def legal_records(board: chess.Board) -> list[ChessMove]:
    records: list[ChessMove] = []
    for move in board.legal_moves:
        san = board.san(move)
        promotion = chess.piece_symbol(move.promotion) if move.promotion else None
        records.append(
            ChessMove(
                uci=move.uci(),
                san=san,
                path=(chess.square_name(move.from_square), chess.square_name(move.to_square)),
                promotion=promotion,
            )
        )
    return sorted(records, key=lambda item: item.uci)


def replay(initial_fen: str, ucis: list[str]) -> chess.Board:
    board = parse_board(initial_fen)
    for uci in ucis:
        try:
            move = chess.Move.from_uci(uci)
        except ValueError as exc:
            raise IllegalMove("В записи партии повреждён ход.") from exc
        if move not in board.legal_moves:
            raise IllegalMove("Запись партии расходится с правилами.")
        board.push(move)
    return board


def push_user_move(board: chess.Board, path: list[str], promotion: str | None) -> ChessMove:
    if len(path) != 2:
        raise IllegalMove("Шахматный ход задаётся двумя полями.")
    uci = path[0].lower() + path[1].lower() + (promotion or "")
    try:
        move = chess.Move.from_uci(uci)
    except ValueError as exc:
        raise IllegalMove("Некорректная запись хода.") from exc
    if move not in board.legal_moves:
        raise IllegalMove("Этот ход не допускается правилами.")
    san = board.san(move)
    promo = chess.piece_symbol(move.promotion) if move.promotion else None
    board.push(move)
    return ChessMove(
        uci=move.uci(),
        san=san,
        path=(path[0].lower(), path[1].lower()),
        promotion=promo,
    )


def import_pgn(text: str) -> tuple[str, list[ChessMove], chess.Board]:
    game = chess.pgn.read_game(io.StringIO(text))
    if game is None:
        raise IllegalMove("Не удалось прочитать PGN.")
    board = game.board()
    initial = board.fen()
    moves: list[ChessMove] = []
    for move in game.mainline_moves():
        if move not in board.legal_moves:
            raise IllegalMove("В PGN есть ход, который правила не допускают.")
        san = board.san(move)
        promotion = chess.piece_symbol(move.promotion) if move.promotion else None
        moves.append(
            ChessMove(
                uci=move.uci(),
                san=san,
                path=(chess.square_name(move.from_square), chess.square_name(move.to_square)),
                promotion=promotion,
            )
        )
        board.push(move)
    return initial, moves, board


def export_pgn(
    initial_fen: str,
    ucis: list[str],
    *,
    white_name: str,
    black_name: str,
    result: str | None,
) -> str:
    game = chess.pgn.Game()
    board = parse_board(initial_fen)
    game.setup(board)
    game.headers["Event"] = "Parlor Night"
    game.headers["White"] = white_name
    game.headers["Black"] = black_name
    node = game
    for uci in ucis:
        move = chess.Move.from_uci(uci)
        node = node.add_variation(move)
    mapped = {"white_win": "1-0", "black_win": "0-1", "draw": "1/2-1/2"}
    game.headers["Result"] = mapped.get(result or "", "*")
    exporter = chess.pgn.StringExporter(headers=True, variations=False, comments=False)
    return str(game.accept(exporter))


def piece_label(piece: chess.Piece) -> str:
    white, black = _PIECE_NAMES[piece.symbol().upper()]
    return white if piece.color == chess.WHITE else black


def cells(board: chess.Board) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for rank in range(8):
        for file in range(8):
            square = chess.square(file, rank)
            piece = board.piece_at(square)
            name = chess.square_name(square)
            label = f"{name}, пусто" if piece is None else f"{name}, {piece_label(piece)}"
            result.append(
                {
                    "square": name,
                    "file": file,
                    "rank": rank,
                    "dark": (file + rank) % 2 == 0,
                    "number": None,
                    "piece": None if piece is None else piece.symbol().upper(),
                    "color": None if piece is None else ("white" if piece.color else "black"),
                    "aria": label,
                }
            )
    return result
