"""Короткий пропуск на coturn. Секрет общий с сервером релея и в браузер не попадает."""

from __future__ import annotations

import base64
import hashlib
import hmac
import time

from app.config import Settings


def mint_turn_password(secret: str, username: str) -> str:
    digest = hmac.new(secret.encode(), username.encode(), hashlib.sha1).digest()
    return base64.b64encode(digest).decode()


def ice_servers(settings: Settings, user_id: str, *, now: int | None = None) -> list[dict[str, object]]:
    host = settings.turn_host.strip()
    if not settings.turn_secret or not host:
        return [{"urls": "stun:stun.l.google.com:19302"}]
    expiry = (int(time.time()) if now is None else now) + 3600
    username = f"{expiry}:{user_id}"
    credential = mint_turn_password(settings.turn_secret, username)
    stun = f"stun:{host}:{settings.turn_port}"
    turn_udp = f"turn:{host}:{settings.turn_port}?transport=udp"
    turn_tcp = f"turn:{host}:{settings.turn_port}?transport=tcp"
    turns = f"turns:{host}:{settings.turn_tls_port}?transport=tcp"
    shared = {"username": username, "credential": credential}
    return [
        {"urls": stun},
        {"urls": [turn_udp, turn_tcp], **shared},
        {"urls": turns, **shared},
    ]
