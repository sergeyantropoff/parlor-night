"""Правила го, подсчёт, SGF и повтор команд."""

from __future__ import annotations

import uuid

import pytest

from app.db.repositories.users import User
from app.errors import AppError
from app.games.present import project
from app.games.service import GameService
from app.go.engine import computer_pending, eye_count, plan, suggested_dead
from app.go.match import apply_action, dump_state, load_state, new_match, replay, same_bones
from app.go.rules import (
    BLACK,
    EMPTY,
    WHITE,
    GoRuleError,
    area,
    empty_board,
    format_half,
    group,
    play_stone,
)
from app.go.sgf import export_sgf


def _put(size: int, stones: dict[tuple[int, int], str]) -> str:
    chars = list(empty_board(size))
    for (col, row), color in stones.items():
        chars[row * size + col] = color
    return "".join(chars)


def test_sizes_and_occupied_point() -> None:
    for size in (9, 13, 19):
        board = empty_board(size)
        assert len(board) == size * size
        placed, taken = play_stone(board, size, {board}, BLACK, 0, 0)
        assert taken == 0
        assert placed[0] == BLACK
        with pytest.raises(GoRuleError, match="занято"):
            play_stone(placed, size, {board, placed}, WHITE, 0, 0)
    with pytest.raises(GoRuleError, match="вне доски"):
        play_stone(empty_board(9), 9, set(), BLACK, 9, 0)
    with pytest.raises(GoRuleError, match="Размер"):
        empty_board(8)


def test_wrong_turn_and_side() -> None:
    state = new_match(9)
    with pytest.raises(GoRuleError, match="другой стороны"):
        apply_action(state, "move", "white", col=0, row=0)
    with pytest.raises(GoRuleError, match="Наблюдатель"):
        apply_action(state, "pass", None)
    with pytest.raises(GoRuleError, match="Неизвестная сторона"):
        play_stone(empty_board(9), 9, set(), "3", 0, 0)


def test_group_liberties_ignore_diagonal() -> None:
    board = _put(9, {(0, 0): BLACK, (1, 1): BLACK, (0, 1): WHITE})
    stones, liberties = group(board, 9, 0, 0)
    assert stones == {(0, 0)}
    assert (1, 1) not in stones
    assert liberties == {(1, 0)}
    connected = _put(9, {(0, 0): BLACK, (1, 0): BLACK, (0, 1): BLACK})
    stones, liberties = group(connected, 9, 0, 0)
    assert stones == {(0, 0), (1, 0), (0, 1)}
    assert len(liberties) == len(set(liberties))
    assert (2, 0) in liberties
    assert (1, 1) in liberties


def test_captures_one_group_many_groups_and_liberty_after() -> None:
    board = _put(9, {(0, 0): WHITE, (1, 0): BLACK})
    placed, taken = play_stone(board, 9, {board}, BLACK, 0, 1)
    assert taken == 1
    assert placed[0] == EMPTY

    surrounded = _put(
        9,
        {
            (1, 0): WHITE,
            (0, 0): BLACK,
            (2, 0): BLACK,
            (0, 1): WHITE,
            (0, 2): BLACK,
            (1, 2): WHITE,
            (1, 3): BLACK,
            (2, 2): BLACK,
            (2, 1): WHITE,
            (3, 1): BLACK,
        },
    )
    placed, taken = play_stone(surrounded, 9, {surrounded}, BLACK, 1, 1)
    assert taken == 4
    assert placed[1 * 9 + 1] == BLACK

    chain = _put(
        9,
        {
            (0, 0): WHITE,
            (1, 0): WHITE,
            (2, 0): WHITE,
            (0, 1): BLACK,
            (1, 1): BLACK,
            (3, 0): BLACK,
        },
    )
    placed, taken = play_stone(chain, 9, {chain}, BLACK, 2, 1)
    assert taken == 3
    assert placed[0] == EMPTY


def test_suicide_forbidden_but_capture_allowed() -> None:
    blocked = _put(9, {(1, 0): WHITE, (0, 1): WHITE})
    with pytest.raises(GoRuleError, match="собственные"):
        play_stone(blocked, 9, {blocked}, BLACK, 0, 0)
    capturing = _put(9, {(0, 0): WHITE, (1, 0): BLACK})
    placed, taken = play_stone(capturing, 9, {capturing}, BLACK, 0, 1)
    assert taken == 1
    assert placed[0] == EMPTY
    assert placed[1 * 9 + 0] == BLACK


def test_superko_passes_and_restart() -> None:
    state = new_match(9)
    first, _record = apply_action(state, "move", "black", col=2, row=2)
    assert empty_board(9) in first["seen"]
    again = load_state(dump_state(first))
    with pytest.raises(GoRuleError, match="уже была"):
        play_stone(empty_board(9), 9, set(again["seen"]), BLACK, 2, 2)

    passed, _record = apply_action(first, "pass", "white")
    assert passed["board"] == first["board"]
    passed_again, _record = apply_action(passed, "pass", "black")
    assert passed_again["phase"] == "score"
    assert passed_again["board"] == first["board"]
    restored = load_state(dump_state(passed_again))
    assert restored["seen"] == passed_again["seen"]
    assert restored["phase"] == "score"


def test_ko_returns_to_an_earlier_board() -> None:
    state = new_match(9)
    script = [
        ("black", "move", 1, 0),
        ("white", "move", 2, 0),
        ("black", "move", 0, 1),
        ("white", "move", 3, 1),
        ("black", "move", 1, 2),
        ("white", "move", 2, 2),
        ("black", "pass", None, None),
        ("white", "move", 1, 1),
        ("black", "move", 2, 1),
    ]
    for color, action, col, row in script:
        state, _record = apply_action(state, action, color, col=col, row=row)
    assert state["board"][1 * 9 + 1] == EMPTY
    assert state["board"][1 * 9 + 2] == BLACK
    with pytest.raises(GoRuleError, match="уже была"):
        apply_action(state, "move", "white", col=1, row=1)


def test_two_passes_marks_and_resume() -> None:
    state = new_match(9)
    state, _record = apply_action(state, "move", "black", col=0, row=0)
    state, _record = apply_action(state, "pass", "white")
    state, _record = apply_action(state, "pass", "black")
    assert state["phase"] == "score"
    assert state["resume_color"] == "white"
    agreed, record = apply_action(state, "agree", "black")
    assert record["result"] is None
    marked, _record = apply_action(agreed, "mark", "white", col=0, row=0)
    assert marked["agreed"] == {"black": None, "white": None}
    assert marked["score_version"] == state["score_version"] + 1
    marked, record = apply_action(marked, "agree", "black")
    marked, record = apply_action(marked, "agree", "white")
    assert record["result"] == "white_win"
    assert marked["captures"]["white"] == 0
    resumed = apply_action(state, "resume", "black")[0]
    assert resumed["phase"] == "play"
    assert resumed["board"][0] == BLACK
    assert resumed["to_play"] == "white"
    assert resumed["passes"] == 0
    assert resumed["captures"] == state["captures"]
    assert resumed["seen"] == state["seen"]
    replayed = replay(dump_state(new_match(9)), [
        {"kind": "move", "col": 0, "row": 0, "color": "black"},
        {"kind": "pass", "color": "white"},
        {"kind": "pass", "color": "black"},
    ])
    same_bones(replayed, resumed)


def test_area_territory_neutral_empty_and_prisoners() -> None:
    size = 9
    stones = {(col, 0): BLACK for col in range(3)}
    stones.update({(col, 2): BLACK for col in range(3)})
    stones.update({(0, 1): BLACK, (2, 1): BLACK, (8, 8): WHITE})
    board = _put(size, stones)
    scored = area(board, size, set())
    assert scored["black_territory"] == 1
    assert scored["white_territory"] == 0
    assert scored["neutral"] == size * size - 8 - 1 - 1
    assert scored["black_alive"] == 8
    assert scored["white_alive"] == 1
    eye = {(1, 1): WHITE}
    dead_board = _put(size, {**stones, **eye})
    removed = {(1, 1)}
    dead_score = area(dead_board, size, removed)
    assert dead_score["white_alive"] == 1
    assert dead_score["black_territory"] == 1
    assert dead_score["black_half"] == 2 * (dead_score["black_alive"] + dead_score["black_territory"])
    plain = area(empty_board(size), size, set())
    assert plain["neutral"] == size * size
    assert plain["black_text"] == "0"
    assert plain["white_text"] == "7,5"
    assert plain["winner"] == "white"
    setup = _put(9, {(1, 0): WHITE, (0, 1): WHITE, (2, 0): BLACK, (1, 1): BLACK, (0, 2): BLACK})
    after, taken = play_stone(setup, 9, {setup}, BLACK, 0, 0)
    assert taken == 2
    counted = area(after, 9, set())
    assert counted["black_half"] == 2 * (counted["black_alive"] + counted["black_territory"])
    covered = (
        counted["black_alive"]
        + counted["white_alive"]
        + counted["black_territory"]
        + counted["white_territory"]
        + counted["neutral"]
    )
    assert covered == 81


def test_resign_is_final_and_commands_do_not_repeat() -> None:
    state = new_match(9)
    resigned, record = apply_action(state, "resign", "black")
    assert record["result"] == "white_win"
    with pytest.raises(GoRuleError, match="завершена"):
        apply_action(resigned, "move", "white", col=0, row=0)

    store = {"version": 1, "status": "active", "state": new_match(9), "moves": [], "paid": 0}

    def commit(action: str, seat: str, version: int, command_id: str, **point: int) -> None:
        if command_id in store["state"]["acks"]:
            return
        if store["status"] == "finished":
            raise GoRuleError("Партия уже завершена.")
        if store["version"] != version:
            raise GoRuleError("Позиция уже изменилась. Обновите партию.")
        nxt, done = apply_action(store["state"], action, seat, col=point.get("col"), row=point.get("row"))
        nxt["acks"] = [*list(nxt["acks"]), command_id][-128:]
        store["state"] = nxt
        store["version"] += 1
        if done["payload"]:
            store["moves"].append(done["payload"])
        if done["result"]:
            store["status"] = "finished"
            store["paid"] += 1

    commit("move", "black", 1, "cmd-1", col=0, row=0)
    commit("move", "black", 1, "cmd-1", col=0, row=0)
    assert len(store["moves"]) == 1
    assert store["version"] == 2
    with pytest.raises(GoRuleError, match="изменилась"):
        commit("move", "white", 1, "cmd-2", col=1, row=0)
    commit("resign", "white", 2, "cmd-3")
    assert store["paid"] == 1
    commit("resign", "white", 3, "cmd-3")
    assert store["paid"] == 1
    assert store["status"] == "finished"


def test_sgf_size_moves_pass_escape_and_result() -> None:
    text = export_sgf(
        size=13,
        moves=[
            {"kind": "move", "col": 3, "row": 3, "color": "black"},
            {"kind": "pass", "color": "white"},
        ],
        black_name="Игрок]",
        white_name="A\\B",
        played_on="2026-11-16",
        result="black_win",
        reason="score",
        margin_half=15,
    )
    assert "SZ[13]" in text
    assert "KM[7.5]" in text
    assert "RU[parlor-area-psk-v1]" in text
    assert ";B[dd]" in text
    assert ";W[]" in text
    assert "PB[Игрок\\]]" in text
    assert "PW[A\\\\B]" in text
    assert "RE[B+7.5]" in text
    assert "Пас" not in text
    resigned = export_sgf(
        size=9,
        moves=[],
        black_name="Чёрные",
        white_name="Белые",
        played_on="2026-11-16",
        result="white_win",
        reason="resign",
        margin_half=None,
    )
    assert "RE[W+R]" in resigned
    assert format_half(15) == "7,5"


def test_projection_hides_controls_from_watcher() -> None:
    creator = User(id=uuid.uuid4(), username="ann", role="user")
    guest = User(id=uuid.uuid4(), username="guest", role="user")
    initial = dump_state(new_match(19))
    game = {
        "id": uuid.uuid4(),
        "user_id": creator.id,
        "opponent_id": None,
        "join_code": "abcd2345",
        "game_type": "go",
        "variant": "19",
        "mode": "online",
        "player_side": "black",
        "status": "waiting",
        "initial_position": initial,
        "current_position": initial,
        "result": None,
        "result_reason": None,
        "engine_level": 3,
        "engine_time_ms": 1000,
        "position_version": 1,
        "creator_flipped": False,
        "opponent_flipped": False,
        "audience": "open",
        "creator_name": "Анна",
        "opponent_name": None,
        "creator_login": "ann",
        "opponent_login": None,
        "creator_avatar": "",
        "opponent_avatar": "",
        "created_at": None,
    }
    host = project(game, creator, [])
    watching = project(game, guest, [])
    assert host["table"] == "go"
    assert host["join_code"] == "abcd2345"
    assert host["your_turn"] is False
    assert host["can_engine"] is False
    assert host["can_undo"] is False
    assert watching["watching"] is True
    assert watching["join_code"] is None
    assert watching["your_turn"] is False
    assert watching["can_resign"] is False
    assert watching["in_call"] is False
    assert watching["legal"] == []


def _service() -> GameService:
    return GameService.__new__(GameService)


def test_go_accepts_computer_and_rejects_analysis() -> None:
    service = _service()
    data = {
        "game_type": "go",
        "mode": "vs_computer",
        "player_side": "white",
        "engine_level": 4,
        "engine_time_ms": 1000,
        "audience": "closed",
        "board_size": 13,
    }
    service._validate_create(data)
    assert data["board_size"] == 13
    assert data["mode"] == "vs_computer"
    with pytest.raises(AppError, match="компьютером"):
        service._validate_create({**data, "mode": "analysis"})


def test_computer_opens_near_the_center_and_captures() -> None:
    state = new_match(9)
    opening = plan(state, "black", 3, 400)["actions"][0]
    assert opening["action"] == "move"
    assert abs(int(opening["col"]) - 4) <= 2
    assert abs(int(opening["row"]) - 4) <= 2
    novice = plan(state, "black", 1, 200)["actions"][0]
    assert novice["action"] == "move"
    play_stone(state["board"], 9, set(state["seen"]), BLACK, int(novice["col"]), int(novice["row"]))

    board = _put(9, {(0, 1): BLACK, (1, 0): BLACK, (1, 2): BLACK, (1, 1): WHITE})
    attack = new_match(9)
    attack["board"] = board
    attack["seen"] = [board]
    attack["to_play"] = "black"
    taken = plan(attack, "black", 3, 500)["actions"][0]
    assert taken == {"action": "move", "col": 2, "row": 1}


def test_computer_scoring_waits_accepts_and_resumes() -> None:
    state = new_match(9)
    state["phase"] = "score"
    state["passes"] = 2
    state["score_version"] = 1
    state["agreed"] = {"black": None, "white": None}
    assert computer_pending(state, "white") is False
    state["agreed"] = {"black": 1, "white": None}
    assert computer_pending(state, "white") is True
    assert plan(state, "white", 1, 100)["actions"] == [{"action": "agree"}]

    board = _put(9, {(4, 4): WHITE, (3, 4): BLACK, (5, 4): BLACK, (4, 3): BLACK})
    trapped = new_match(9)
    trapped["board"] = board
    trapped["seen"] = [board]
    trapped["phase"] = "score"
    trapped["passes"] = 2
    trapped["score_version"] = 1
    trapped["agreed"] = {"black": None, "white": None}
    assert suggested_dead(trapped) == {(4, 4)}
    assert computer_pending(trapped, "white") is True
    assert plan(trapped, "white", 1, 100)["actions"] == [{"action": "mark", "col": 4, "row": 4}]

    eyes = {
        (1, 1): BLACK,
        (3, 1): BLACK,
        (2, 1): BLACK,
        (1, 2): BLACK,
        (1, 3): BLACK,
        (1, 4): BLACK,
        (3, 2): BLACK,
        (3, 3): BLACK,
        (3, 4): BLACK,
        (2, 3): BLACK,
        (1, 5): BLACK,
        (3, 5): BLACK,
        (2, 5): BLACK,
    }
    living = new_match(9)
    living["board"] = _put(9, eyes)
    living["phase"] = "score"
    living["score_version"] = 1
    living["dead"] = [[2, 1]]
    living["agreed"] = {"black": 1, "white": None}
    stones, _libs = group(living["board"], 9, 2, 1)
    assert eye_count(living["board"], 9, stones) >= 2
    assert plan(living, "white", 1, 100)["actions"] == [{"action": "resume"}]


def test_projection_asks_the_computer_to_move() -> None:
    creator = User(id=uuid.uuid4(), username="ann", role="user")
    guest = User(id=uuid.uuid4(), username="guest", role="user")
    initial = dump_state(new_match(9))
    game = {
        "id": uuid.uuid4(),
        "user_id": creator.id,
        "opponent_id": None,
        "join_code": None,
        "game_type": "go",
        "variant": "9",
        "mode": "vs_computer",
        "player_side": "white",
        "status": "active",
        "initial_position": initial,
        "current_position": initial,
        "result": None,
        "result_reason": None,
        "engine_level": 2,
        "engine_time_ms": 700,
        "position_version": 1,
        "creator_flipped": False,
        "opponent_flipped": False,
        "audience": "open",
        "creator_name": "Анна",
        "opponent_name": None,
        "creator_login": "ann",
        "opponent_login": None,
        "creator_avatar": "",
        "opponent_avatar": "",
        "created_at": None,
    }
    host = project(game, creator, [])
    watching = project(game, guest, [])
    assert host["can_engine"] is True
    assert host["your_side"] == "white"
    assert host["your_turn"] is False
    assert host["status_line"] == f"Ходит {host['black_name']}."
    assert host["black_name"] != "Компьютер"
    assert host["computer_side"] == "black"
    assert host["white_name"] == "Анна"
    assert host["engine_title"] == "Любитель"
    assert host["in_call"] is False
    assert watching["watching"] is True
    assert watching["can_engine"] is False
    assert watching["live"] is True
    seated = project({**game, "player_side": "black"}, creator, [])
    assert seated["can_engine"] is False
    assert seated["your_turn"] is True
