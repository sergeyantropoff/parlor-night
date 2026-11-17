from __future__ import annotations

import base64
import hashlib
import hmac

from app.config import Settings
from app.turn import ice_servers, mint_turn_password


def _settings(**extra: object) -> Settings:
    return Settings(
        secret_key="x" * 32,
        database_url="postgresql://boardmentor:boardmentor@127.0.0.1/boardmentor",
        env="test",
        **extra,
    )


def test_turn_password_matches_the_coturn_rest_hmac() -> None:
    secret = "table-secret"
    username = "1700003600:pavel"
    expected = base64.b64encode(hmac.new(secret.encode(), username.encode(), hashlib.sha1).digest()).decode()
    assert mint_turn_password(secret, username) == expected


def test_ice_without_a_relay_is_only_a_public_stun() -> None:
    assert ice_servers(_settings(), "pavel", now=1_700_000_000) == [{"urls": "stun:stun.l.google.com:19302"}]


def test_ice_offers_direct_turn_and_tls() -> None:
    servers = ice_servers(
        _settings(turn_secret="table-secret", turn_host="pn.antropoff.ru"),
        "pavel",
        now=1_700_000_000,
    )
    assert servers[0]["urls"] == "stun:pn.antropoff.ru:3478"
    assert servers[1]["username"] == "1700003600:pavel"
    assert servers[1]["credential"] == mint_turn_password("table-secret", "1700003600:pavel")
    assert servers[1]["urls"] == [
        "turn:pn.antropoff.ru:3478?transport=udp",
        "turn:pn.antropoff.ru:3478?transport=tcp",
    ]
    assert servers[2]["urls"] == "turns:pn.antropoff.ru:5349?transport=tcp"
