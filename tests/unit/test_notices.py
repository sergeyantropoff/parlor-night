from app.social.notices import clip_notice


def test_clip_notice_keeps_a_short_line() -> None:
    assert clip_notice("  Привет,\nсыграем  ") == "Привет, сыграем"


def test_clip_notice_cuts_a_long_line() -> None:
    text = "а" * 180
    clipped = clip_notice(text)
    assert clipped.endswith("…")
    assert len(clipped) == 160
