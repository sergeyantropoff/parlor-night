"""Картинки новостей: только JPEG, PNG и WebP, имя задаёт сервер."""

from __future__ import annotations

import re
import secrets
from pathlib import Path

IMAGE_NAME = re.compile(r"^[0-9a-f]{32}\.(jpg|png|webp)$")
PRESET_COVERS = frozenset({"light-theme", "uno-evening", "welcome", "card-games", "go", "beta", "domino", "nardy", "yahtzy"})
_MEDIA = {"jpg": "image/jpeg", "png": "image/png", "webp": "image/webp"}


def cover_kind(value: object) -> str:
    text = "" if value is None else str(value)
    if text in PRESET_COVERS:
        return "preset"
    if IMAGE_NAME.fullmatch(text):
        return "upload"
    return ""


def is_news_image(value: object) -> bool:
    return cover_kind(value) == "upload"


def media_type(name: str) -> str:
    return _MEDIA[name.rsplit(".", 1)[-1]]


def sniff_image(payload: bytes) -> str | None:
    if payload.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if payload.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if len(payload) >= 12 and payload[:4] == b"RIFF" and payload[8:12] == b"WEBP":
        return "webp"
    return None


def store_news_image(directory: Path, payload: bytes, *, limit: int) -> str:
    if not payload or len(payload) > limit:
        raise ValueError("size")
    kind = sniff_image(payload)
    if kind is None:
        raise ValueError("type")
    directory.mkdir(parents=True, exist_ok=True)
    name = f"{secrets.token_hex(16)}.{kind}"
    target = directory / name
    target.write_bytes(payload)
    return name


def image_file(directory: Path, name: str) -> Path | None:
    if not IMAGE_NAME.fullmatch(name):
        return None
    root = directory.resolve()
    path = (root / name).resolve()
    if path.parent != root or not path.is_file():
        return None
    return path
