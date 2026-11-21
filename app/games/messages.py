"""Тексты результатов для интерфейса."""

from __future__ import annotations

_MESSAGES = {
    ("chess", "checkmate", "white_win"): "Мат. Победа белых.",
    ("chess", "checkmate", "black_win"): "Мат. Победа чёрных.",
    ("chess", "stalemate", "draw"): "Пат. Ничья.",
    ("chess", "insufficient_material", "draw"): "Ничья: недостаточно материала.",
    ("chess", "fifty_moves", "draw"): "Ничья: правило пятидесяти ходов.",
    ("chess", "seventyfive_moves", "draw"): "Ничья: правило семидесяти пяти ходов.",
    ("chess", "threefold_repetition", "draw"): "Ничья: троекратное повторение позиции.",
    ("chess", "fivefold_repetition", "draw"): "Ничья: пятикратное повторение позиции.",
    ("checkers", "no_moves", "white_win"): "У чёрных нет ходов. Победа белых.",
    ("checkers", "no_moves", "black_win"): "У белых нет ходов. Победа чёрных.",
    ("checkers", "repetition", "draw"): "Ничья: троекратное повторение позиции.",
    ("checkers", "nonprogress", "draw"): (
        "Ничья: 15 ходов каждой стороны без взятия и без хода простой шашки."
    ),
    ("checkers", "technical_limit", "draw"): "Ничья: достигнут технический предел партии.",
    ("go", "resign", "white_win"): "Чёрные сдались. Победа белых.",
    ("go", "resign", "black_win"): "Белые сдались. Победа чёрных.",
    ("go", "score", "white_win"): "Победа белых по очкам.",
    ("go", "score", "black_win"): "Победа чёрных по очкам.",
    ("chess", "resign", "white_win"): "Чёрные сдались. Победа белых.",
    ("chess", "resign", "black_win"): "Белые сдались. Победа чёрных.",
    ("checkers", "resign", "white_win"): "Чёрные сдались. Победа белых.",
    ("checkers", "resign", "black_win"): "Белые сдались. Победа чёрных.",
    ("uno", "left", "white_win"): "Чёрные вышли из-за стола. Победа белых.",
    ("uno", "left", "black_win"): "Белые вышли из-за стола. Победа чёрных.",
    ("poker", "left", "white_win"): "Чёрные вышли из-за стола. Банк у белых.",
    ("poker", "left", "black_win"): "Белые вышли из-за стола. Банк у чёрных.",
    ("poker", "fold", "white_win"): "Чёрные сбросили карты. Банк у белых.",
    ("poker", "fold", "black_win"): "Белые сбросили карты. Банк у чёрных.",
    ("durak", "durak", "white_win"): "Чёрные остались с картами. Победа белых.",
    ("durak", "durak", "black_win"): "Белые остались с картами. Победа чёрных.",
    ("durak", "clear", "draw"): "Карты кончились у всех. Ничья.",
    ("durak", "left", "white_win"): "Чёрные вышли из-за стола. Победа белых.",
    ("durak", "left", "black_win"): "Белые вышли из-за стола. Победа чёрных.",
    ("blackjack", "showdown", "white_win"): "Выигрыш у дилера.",
    ("blackjack", "showdown", "black_win"): "Дилер забирает ставку.",
    ("blackjack", "showdown", "draw"): "Ничья с дилером.",
    ("preferans", "score", "draw"): "Пуля закрыта. Расписка ничья.",
    ("preferans", "left", "white_win"): "Соперник вышел из-за стола.",
    ("preferans", "left", "black_win"): "Соперник вышел из-за стола.",
    ("domino", "empty", "white_win"): "Кости кончились. Победа белых.",
    ("domino", "empty", "black_win"): "Кости кончились. Победа чёрных.",
    ("domino", "blocked", "white_win"): "Рыба. У белых меньше очков.",
    ("domino", "blocked", "black_win"): "Рыба. У чёрных меньше очков.",
    ("domino", "blocked", "draw"): "Рыба. Одинаковая сумма очков.",
    ("domino", "left", "white_win"): "Чёрные вышли из-за стола. Победа белых.",
    ("domino", "left", "black_win"): "Белые вышли из-за стола. Победа чёрных.",
    ("domino", "left", "draw"): "Игрок вышел из-за стола. Ничья.",
    ("nardy", "single", "white_win"): "Все шашки сняты. Победа белых.",
    ("nardy", "single", "black_win"): "Все шашки сняты. Победа чёрных.",
    ("nardy", "oin", "white_win"): "Все шашки сняты. Победа белых.",
    ("nardy", "oin", "black_win"): "Все шашки сняты. Победа чёрных.",
    ("nardy", "gammon", "white_win"): "Гэммон. Победа белых.",
    ("nardy", "gammon", "black_win"): "Гэммон. Победа чёрных.",
    ("nardy", "backgammon", "white_win"): "Бэкгэммон. Победа белых.",
    ("nardy", "backgammon", "black_win"): "Бэкгэммон. Победа чёрных.",
    ("nardy", "mars", "white_win"): "Марс. Победа белых.",
    ("nardy", "mars", "black_win"): "Марс. Победа чёрных.",
    ("nardy", "cox", "white_win"): "Кокс. Победа белых.",
    ("nardy", "cox", "black_win"): "Кокс. Победа чёрных.",
    ("nardy", "drop", "white_win"): "Удвоение не принято. Победа белых.",
    ("nardy", "drop", "black_win"): "Удвоение не принято. Победа чёрных.",
    ("nardy", "resign", "white_win"): "Чёрные сдались. Победа белых.",
    ("nardy", "resign", "black_win"): "Белые сдались. Победа чёрных.",
    ("nardy", "left", "white_win"): "Чёрные вышли из-за стола. Победа белых.",
    ("nardy", "left", "black_win"): "Белые вышли из-за стола. Победа чёрных.",
}


def stopped_badge(status: str, result: str | None, reason: str | None) -> str | None:
    if status == "finished" and result is None and reason == "stopped":
        return "Партия остановлена."
    return None


def result_badge(result: str | None) -> str | None:
    return {"white_win": "Победа белых", "black_win": "Победа чёрных", "draw": "Ничья"}.get(result or "")


def result_tone(result: str | None, seat: str | None) -> str | None:
    if result == "draw":
        return "draw"
    winner = {"white_win": "white", "black_win": "black"}.get(result or "")
    if winner is None:
        return None
    if seat in {"white", "black"}:
        return "win" if seat == winner else "loss"
    return "win"


def result_message(game_type: str, result: str | None, reason: str | None) -> str | None:
    if result is None:
        return None
    found = _MESSAGES.get((game_type, reason or "", result))
    if found:
        return found
    if game_type == "domino":
        if result == "draw":
            return "Рыба. Одинаковая сумма очков." if reason == "blocked" else "Ничья."
        if reason == "empty":
            return "Кости кончились."
        if reason == "blocked":
            return "Рыба. Победа у того, у кого меньше очков."
        if reason == "left":
            return "Соперник вышел из-за стола."
    return "Партия завершена." if result == "draw" else "Партия завершена победой."
