from pathlib import Path

from app.news_images import image_file, sniff_image, store_news_image


def test_sniff_rejects_a_document() -> None:
    assert sniff_image(b"<html></html>") is None
    assert sniff_image(b"\xff\xd8\xff\x00") == "jpg"


def test_store_writes_a_server_name(tmp_path: Path) -> None:
    name = store_news_image(tmp_path, b"\x89PNG\r\n\x1a\nrest", limit=100)
    assert (tmp_path / name).read_bytes().startswith(b"\x89PNG")
    assert image_file(tmp_path, name) == (tmp_path / name).resolve()
    assert image_file(tmp_path, "../secret.png") is None


def test_store_rejects_oversized_payload(tmp_path: Path) -> None:
    try:
        store_news_image(tmp_path, b"\xff\xd8\xfftoo-big", limit=4)
    except ValueError:
        return
    raise AssertionError("oversized image was stored")
