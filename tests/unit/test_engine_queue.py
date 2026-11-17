from app.chess.engine import EngineLine
from app.workers.remote import pack_line, unpack_line


def test_engine_line_survives_the_queue() -> None:
    line = EngineLine(
        uci="e2e4",
        san="e4",
        path=("e2", "e4"),
        promotion=None,
        score_white=12,
        mate=None,
        pv=("e2e4", "e7e5"),
        depth=8,
        nodes=40,
    )
    assert unpack_line(pack_line(line)) == line
