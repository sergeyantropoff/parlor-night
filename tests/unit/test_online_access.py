from __future__ import annotations

import uuid

import chess
from app.checkers.serialization import INITIAL_RCP
from app.db.repositories.users import User
from app.games.access import can_hint, undo_count, user_may_move, user_may_request_engine
from app.games.present import project


def test_live_table_uses_the_people_who_sat() -> None:
    from app.web.routes import _table_players

    filled = {
        "mode": "online",
        "creator_name": "Pavel",
        "opponent_name": None,
        "human_names": "Pavel\x1fСережа",
    }
    assert _table_players(filled, vacancies=0, waiting=False, cpu_label="") == "Pavel — Сережа"
    waiting = {
        "mode": "online",
        "creator_name": "Pavel",
        "opponent_name": None,
        "human_names": "Pavel",
    }
    assert _table_players(waiting, vacancies=1, waiting=True, cpu_label="") == "Pavel"
    paired = {
        "mode": "online",
        "creator_name": "Pavel",
        "opponent_name": "Сережа",
        "human_names": "",
    }
    assert _table_players(paired, vacancies=0, waiting=False, cpu_label="") == "Pavel — Сережа"
    named = {
        "mode": "online",
        "creator_full": "\x1fСережа\x1f",
        "creator_login": "admin",
        "creator_name": "Сережа",
        "opponent_name": None,
        "human_roster": "\x1fСережа\x1f\x1eadmin\x1d\x1fИван\x1fИванович\x1euser",
    }
    assert _table_players(named, vacancies=0, waiting=False, cpu_label="") == "Сережа — Иван"


def test_checkers_hint_uses_the_board_letters() -> None:
    from app.games.service import _checkers_hint_notation

    assert _checkers_hint_notation({"notation": "11-16", "path": ["11", "16"]}) == "f6-g5"
    assert _checkers_hint_notation({"notation": "21:14:7", "path": [21, 14, 7]}) == "a3:c5:e7"


def test_hints_are_admin_only() -> None:
    assert can_hint("admin") is True
    assert can_hint("user") is False


def test_durak_step_aside_needs_two_computers() -> None:
    from app.games.access import durak_can_step_aside

    me = "user-1"
    mine = {"user_id": me, "kind": "human"}
    cpu = {"user_id": None, "kind": "computer"}
    assert durak_can_step_aside([mine, cpu, cpu], me) is True
    assert durak_can_step_aside([mine, cpu], me) is False
    assert durak_can_step_aside(
        [mine, cpu, cpu, {"user_id": "user-2", "kind": "human"}],
        me,
    ) is False
    assert durak_can_step_aside([mine, cpu, {"user_id": None, "kind": "human"}], me) is False
    assert durak_can_step_aside([{**mine, "kind": "computer"}, cpu, cpu], me) is False


def test_gallery_may_ask_the_engine_on_its_own_seat() -> None:
    assert user_may_request_engine("vs_computer", "active", "white", "white", computer_turn=True) is True
    assert user_may_request_engine("vs_computer", "active", "white", "white") is False


def test_online_permissions() -> None:
    assert user_may_move("online", "active", "white", "white") is True
    assert user_may_move("online", "active", "white", "black") is False
    assert user_may_move("online", "waiting", "white", "white") is False
    assert user_may_request_engine("online", "active", "black", "white") is False
    assert user_may_request_engine("vs_computer", "active", "black", "white") is True
    assert undo_count("online", "active", 1, "black", "white") == 1
    assert undo_count("online", "active", 2, "white", "white") == 0
    assert undo_count("vs_computer", "active", 2, "white", "white") == 2


def test_online_state_hides_hint_and_opponent_moves() -> None:
    creator = User(id=uuid.uuid4(), username="ann", role="user")
    admin = User(id=uuid.uuid4(), username="root", role="admin")
    fen = chess.Board().fen()
    game = {
        "id": uuid.uuid4(),
        "user_id": creator.id,
        "opponent_id": admin.id,
        "join_code": None,
        "game_type": "chess",
        "variant": "standard",
        "mode": "online",
        "player_side": "white",
        "status": "active",
        "initial_position": fen,
        "current_position": fen,
        "result": None,
        "result_reason": None,
        "engine_level": 3,
        "engine_time_ms": 1000,
        "position_version": 3,
        "creator_flipped": False,
        "opponent_flipped": False,
        "creator_name": "ann",
        "opponent_name": "root",
    }
    white = project(game, creator, [])
    black = project(game, admin, [])
    assert white["can_hint"] is False
    assert black["can_hint"] is True
    assert white["your_turn"] is True
    assert black["your_turn"] is False
    assert black["legal_moves"] == []
    assert white["legal_moves"]
    assert white["black_at_bottom"] is False
    assert black["black_at_bottom"] is True
    assert white["can_engine"] is False
    assert white["can_stop"] is True
    assert black["can_stop"] is False
    assert white["in_call"] is True
    assert white["audience"] == "closed"
    guest = User(id=uuid.uuid4(), username="guest", role="user")
    watching = project({**game, "audience": "open"}, guest, [])
    assert watching["watching"] is True
    assert watching["can_stop"] is False
    assert watching["in_call"] is False
    assert watching["live"] is True
    assert watching["audience"] == "open"
    computer_game = {
        **game,
        "mode": "vs_computer",
        "opponent_id": None,
        "opponent_name": None,
        "audience": "open",
    }
    computer = project(computer_game, guest, [])
    assert computer["watching"] is True
    assert computer["live"] is True
    assert computer["in_call"] is False
    assert computer["can_move"] is False
    assert computer["can_engine"] is False
    owner = project({**game, "mode": "vs_computer", "audience": "open"}, creator, [])
    assert owner["white_name"] == "ann"
    assert owner["black_name"] != "Компьютер"
    assert owner["computer_side"] == "black"
    assert owner["engine_title"] == "Опытный"
    assert owner["watching"] is False
    assert owner["live"] is False
    assert owner["can_move"] is True
    assert "best_move" not in white
    assert "best_move" not in black


def test_call_roster_counts_only_people_who_sat() -> None:
    creator = User(id=uuid.uuid4(), username="admin", role="user", full_name="Сережа")
    pavel = uuid.uuid4()
    fen = chess.Board().fen()
    game = {
        "id": uuid.uuid4(),
        "user_id": creator.id,
        "opponent_id": None,
        "join_code": "qw43wgjr",
        "game_type": "chess",
        "variant": "standard",
        "mode": "online",
        "player_side": "white",
        "status": "active",
        "initial_position": fen,
        "current_position": fen,
        "result": None,
        "result_reason": None,
        "engine_level": 3,
        "engine_time_ms": 1000,
        "position_version": 4,
        "creator_flipped": False,
        "opponent_flipped": False,
        "creator_name": "Сережа",
        "creator_login": "admin",
        "creator_avatar": "",
        "opponent_name": None,
        "opponent_login": None,
        "opponent_avatar": None,
        "audience": "closed",
        "table_seats": [
            {
                "seat_key": "white",
                "kind": "human",
                "user_id": creator.id,
                "username": "Сережа",
                "login": "admin",
                "avatar": "",
            },
            {
                "seat_key": "east",
                "kind": "human",
                "user_id": pavel,
                "username": "Pavel",
                "login": "pavel",
                "avatar": "",
            },
            {
                "seat_key": "north",
                "kind": "human",
                "user_id": None,
                "username": None,
                "login": None,
                "avatar": None,
            },
            {
                "seat_key": "black",
                "kind": "computer",
                "user_id": None,
                "username": None,
                "login": None,
                "avatar": None,
            },
        ],
    }
    roster = project(game, creator, [])["call_roster"]
    assert [item["name"] for item in roster] == ["Сережа", "Pavel"]
    assert {item["id"] for item in roster} == {str(creator.id), str(pavel)}


def test_finished_checkers_uses_a_short_badge() -> None:
    user = User(id=uuid.uuid4(), username="ann", role="user")
    game = {
        "id": uuid.uuid4(),
        "user_id": user.id,
        "opponent_id": None,
        "join_code": None,
        "game_type": "checkers",
        "variant": "russian",
        "mode": "vs_computer",
        "player_side": "white",
        "status": "finished",
        "initial_position": INITIAL_RCP,
        "current_position": INITIAL_RCP,
        "result": "white_win",
        "result_reason": "no_moves",
        "engine_level": 1,
        "engine_time_ms": 200,
        "position_version": 1,
        "creator_flipped": False,
        "opponent_flipped": False,
        "creator_name": "ann",
        "opponent_name": None,
    }
    state = project(game, user, [])
    assert state["status_line"] == "Победа белых"
    assert state["result_tone"] == "win"
    game["result"] = "black_win"
    lost = project(game, user, [])
    assert lost["status_line"] == "Победа чёрных"
    assert lost["result_tone"] == "loss"


def test_stopped_game_has_no_winner() -> None:
    user = User(id=uuid.uuid4(), username="ann", role="user")
    game = {
        "id": uuid.uuid4(),
        "user_id": user.id,
        "opponent_id": None,
        "join_code": None,
        "game_type": "chess",
        "variant": "standard",
        "mode": "online",
        "player_side": "white",
        "status": "finished",
        "initial_position": chess.Board().fen(),
        "current_position": chess.Board().fen(),
        "result": None,
        "result_reason": "stopped",
        "engine_level": 1,
        "engine_time_ms": 200,
        "position_version": 1,
        "creator_flipped": False,
        "opponent_flipped": False,
        "creator_name": "ann",
        "opponent_name": None,
    }
    state = project(game, user, [])
    assert state["status_line"] == "Партия остановлена."
    assert state["result_tone"] == "stop"
    assert state["result"] is None


def test_black_player_board_starts_flipped() -> None:
    user = User(id=uuid.uuid4(), username="ann", role="user")
    game = {
        "id": uuid.uuid4(),
        "user_id": user.id,
        "opponent_id": None,
        "join_code": None,
        "game_type": "checkers",
        "variant": "russian",
        "mode": "vs_computer",
        "player_side": "black",
        "status": "active",
        "initial_position": INITIAL_RCP,
        "current_position": INITIAL_RCP,
        "result": None,
        "result_reason": None,
        "engine_level": 1,
        "engine_time_ms": 200,
        "position_version": 1,
        "creator_flipped": False,
        "opponent_flipped": False,
        "creator_name": "ann",
        "opponent_name": None,
    }
    state = project(game, user, [])
    assert state["black_at_bottom"] is True
    assert state["your_turn"] is False
    assert state["can_engine"] is True
    assert state["can_hint"] is False
    assert state["summary"] is None


def test_finished_board_games_carry_a_summary() -> None:
    creator = User(id=uuid.uuid4(), username="ann", role="user")
    fen = chess.Board().fen()
    chess_game = {
        "id": uuid.uuid4(),
        "user_id": creator.id,
        "opponent_id": None,
        "join_code": None,
        "game_type": "chess",
        "variant": "standard",
        "mode": "vs_computer",
        "player_side": "white",
        "status": "finished",
        "initial_position": fen,
        "current_position": fen,
        "result": "black_win",
        "result_reason": "resign",
        "engine_level": 3,
        "engine_time_ms": 1000,
        "position_version": 1,
        "creator_flipped": False,
        "opponent_flipped": False,
        "creator_name": "ann",
        "opponent_name": None,
    }
    chess_state = project(chess_game, creator, [])
    assert chess_state["summary"]["kind"] == "board"
    assert chess_state["summary"]["winner"] == "black"
    assert chess_state["summary"]["winner_name"] == chess_state["black_name"]
    assert chess_state["summary"]["winner_name"] != "Компьютер"
    assert chess_state["summary"]["counts"]["moves"] == 0
    assert chess_state["summary"]["counts"]["white"] == 16
    stopped = project({**chess_game, "result": None, "result_reason": "stopped"}, creator, [])
    assert stopped["summary"]["reason"] == "stopped"
    assert stopped["summary"]["winner"] == ""
    checkers = project(
        {
            **chess_game,
            "game_type": "checkers",
            "variant": "russian",
            "initial_position": INITIAL_RCP,
            "current_position": INITIAL_RCP,
            "result": "white_win",
            "result_reason": "no_moves",
        },
        creator,
        [],
    )
    assert checkers["summary"]["game"] == "checkers"
    assert checkers["summary"]["winner_name"] == "ann"
    assert checkers["summary"]["counts"]["white"] == 12
    assert checkers["summary"]["counts"]["captures"] == 0


def test_finished_uno_carries_a_summary() -> None:
    from app.cards.uno import apply, deal, dumps

    creator = User(id=uuid.uuid4(), username="ann", role="user")
    state = deal()
    state["hands"]["white"] = ["R3"]
    state["discard"] = ["R7"]
    state["color"] = "R"
    state["to_move"] = "white"
    initial = dumps(state)
    final = apply(state, ["play", "R3"])
    game = {
        "id": uuid.uuid4(),
        "user_id": creator.id,
        "opponent_id": uuid.uuid4(),
        "join_code": None,
        "game_type": "uno",
        "variant": "classic",
        "mode": "online",
        "player_side": "white",
        "status": "finished",
        "initial_position": initial,
        "current_position": dumps(final),
        "result": "white_win",
        "result_reason": "empty_hand",
        "engine_level": 1,
        "engine_time_ms": 200,
        "position_version": 2,
        "creator_flipped": False,
        "opponent_flipped": False,
        "creator_name": "ann",
        "opponent_name": "root",
        "audience": "closed",
    }
    viewed = project(
        game,
        creator,
        [{"ply": 1, "notation": "R3", "move_payload": {"path": ["play", "R3"]}}],
    )
    assert viewed["summary"]["kind"] == "uno"
    assert viewed["summary"]["winner"] == "white"
    assert viewed["summary"]["winner_name"] == "ann"
    assert viewed["summary"]["counts"]["play"] == 1
