from pathlib import Path

import pytest

from app.avatars import image_file, remove_avatar, store_avatar

PNG = b"\x89PNG\r\n\x1a\n" + b"portrait"


def test_store_and_replace_avatar(tmp_path: Path) -> None:
    name = store_avatar(tmp_path, PNG, limit=100)
    assert image_file(tmp_path, name) == tmp_path / name
    assert image_file(tmp_path, "../" + name) is None
    remove_avatar(tmp_path, name)
    assert image_file(tmp_path, name) is None


def test_rejects_unknown_bytes(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        store_avatar(tmp_path, b"not-an-image", limit=100)
