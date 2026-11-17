"""Проверка «Я не робот»: та же схема, что у ALTCHA на devops.org.ru.

Сервер выдаёт соль и подпись. Браузер подбирает число, чей SHA-256 от соли
совпадает с заданием. Без этого числа нельзя войти и создать учётную запись.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Any

WINDOW_SECONDS = 600
MAX_NUMBER = 100_000


def issue(secret: str) -> dict[str, object]:
    expires = int(time.time()) + WINDOW_SECONDS
    salt = f"{secrets.token_hex(12)}?expires={expires}"
    number = secrets.randbelow(MAX_NUMBER + 1)
    challenge = _digest(salt, number)
    return {
        "algorithm": "SHA-256",
        "challenge": challenge,
        "maxnumber": MAX_NUMBER,
        "salt": salt,
        "signature": _sign(secret, challenge),
    }


def proof(secret: str, payload: str) -> str | None:
    """Подпись решённого задания или None, если ответ поддельный или просрочен."""
    try:
        raw = base64.b64decode(payload.strip(), validate=True)
        body = json.loads(raw.decode())
    except (ValueError, UnicodeError, json.JSONDecodeError):
        return None
    if not isinstance(body, dict):
        return None
    challenge = str(body.get("challenge") or "")
    salt = str(body.get("salt") or "")
    signature = str(body.get("signature") or "")
    number = body.get("number")
    if body.get("algorithm") != "SHA-256":
        return None
    if not challenge or not salt or not signature or isinstance(number, bool):
        return None
    try:
        solved = int(number)
    except (TypeError, ValueError):
        return None
    if solved < 0 or solved > MAX_NUMBER:
        return None
    if not hmac.compare_digest(signature, _sign(secret, challenge)):
        return None
    if _digest(salt, solved) != challenge or not _fresh(salt):
        return None
    return signature


def _digest(salt: str, number: int) -> str:
    return hashlib.sha256(f"{salt}{number}".encode()).hexdigest()


def _sign(secret: str, challenge: str) -> str:
    return hmac.new(secret.encode(), challenge.encode(), hashlib.sha256).hexdigest()


def _fresh(salt: str) -> bool:
    marker = "?expires="
    if marker not in salt:
        return False
    try:
        expires = int(salt.rsplit(marker, 1)[1])
    except ValueError:
        return False
    now = int(time.time())
    return now - 30 <= expires <= now + WINDOW_SECONDS + 30


def solve(challenge: dict[str, Any]) -> int:
    """Подбор числа для тестов. Браузер делает то же самое."""
    salt = str(challenge["salt"])
    wanted = str(challenge["challenge"])
    ceiling = int(challenge["maxnumber"])
    for number in range(ceiling + 1):
        if _digest(salt, number) == wanted:
            return number
    raise ValueError("Задание проверки не решается.")
