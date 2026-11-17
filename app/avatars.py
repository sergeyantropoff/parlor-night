"""Портреты гостей: JPEG, PNG и WebP в общем томе гостиной."""

from __future__ import annotations

import secrets
from pathlib import Path

from app.news_images import IMAGE_NAME, media_type, sniff_image

__all__ = ["IMAGE_NAME", "image_file", "media_type", "remove_avatar", "store_avatar"]


def store_avatar(directory: Path, payload: bytes, *, limit: int) -> str:
    if not payload or len(payload) > limit:
        raise ValueError("size")
    kind = sniff_image(payload)
    if kind is None:
        raise ValueError("type")
    directory.mkdir(parents=True, exist_ok=True)
    name = f"{secrets.token_hex(16)}.{kind}"
    target = directory / name
    temporary = directory / f".{name}.part"
    temporary.write_bytes(payload)
    temporary.replace(target)
    return name


def image_file(directory: Path, name: str) -> Path | None:
    if not IMAGE_NAME.fullmatch(name):
        return None
    root = directory.resolve()
    path = (root / name).resolve()
    if path.parent != root or not path.is_file():
        return None
    return path


def remove_avatar(directory: Path, name: str) -> None:
    path = image_file(directory, name)
    if path is not None:
        path.unlink(missing_ok=True)
