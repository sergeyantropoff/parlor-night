"""Подпись CSRF-токенов. Сравнение с постоянным временем."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
import uuid


def sign(secret: str, token: str) -> str:
    return hmac.new(secret.encode(), token.encode(), hashlib.sha256).hexdigest()


def issue_login_csrf(secret: str) -> tuple[str, str]:
    token = secrets.token_urlsafe(32)
    return token, f"{token}.{sign(secret, token)}"


def verify_login_csrf(secret: str, raw: str, signed: str) -> bool:
    if not raw or not signed or "." not in signed:
        return False
    token, signature = signed.rsplit(".", 1)
    expected = sign(secret, token)
    if len(signature) != len(expected):
        return False
    return hmac.compare_digest(token, raw) and hmac.compare_digest(signature, expected)


def new_session_secrets() -> tuple[str, str, str]:
    token = secrets.token_urlsafe(32)
    csrf = secrets.token_urlsafe(32)
    digest = hashlib.sha256(token.encode()).hexdigest()
    return token, digest, csrf


def issue_welcome(secret: str, user_id: str, ttl: int = 900) -> str:
    expires = int(time.time()) + ttl
    body = f"{user_id}.{expires}"
    return f"{body}.{sign(secret, body)}"


def read_welcome(secret: str, value: str) -> str | None:
    user_id, dot, rest = value.partition(".")
    expires, dot2, signature = rest.partition(".")
    if not dot or not dot2 or not user_id or not expires or not signature:
        return None
    body = f"{user_id}.{expires}"
    expected = sign(secret, body)
    if len(signature) != len(expected) or not hmac.compare_digest(signature, expected):
        return None
    try:
        if int(expires) < int(time.time()):
            return None
        uuid.UUID(user_id)
    except ValueError:
        return None
    return user_id


def tokens_match(left: str, right: str) -> bool:
    if not left or not right or len(left) != len(right):
        return False
    return hmac.compare_digest(left, right)
