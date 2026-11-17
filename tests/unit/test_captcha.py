import base64
import json

from app.auth.captcha import issue, proof, solve


def _payload(task: dict[str, object], number: int, **overrides: object) -> str:
    body = {
        "algorithm": task["algorithm"],
        "challenge": task["challenge"],
        "number": number,
        "salt": task["salt"],
        "signature": task["signature"],
    }
    body.update(overrides)
    return base64.b64encode(json.dumps(body).encode()).decode()


def test_solved_checkbox_is_accepted() -> None:
    task = issue("parlor-secret")
    number = solve(task)
    signature = proof("parlor-secret", _payload(task, number))
    assert signature == task["signature"]
    assert proof("other-secret", _payload(task, number)) is None
    assert proof("parlor-secret", _payload(task, number, signature="0" * 64)) is None
    assert proof("parlor-secret", "") is None


def test_expired_challenge_is_rejected(monkeypatch) -> None:
    monkeypatch.setattr("app.auth.captcha.time.time", lambda: 1_700_000_000)
    task = issue("parlor-secret")
    payload = _payload(task, solve(task))
    monkeypatch.setattr("app.auth.captcha.time.time", lambda: 1_700_000_700)
    assert proof("parlor-secret", payload) is None
