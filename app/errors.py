"""Ошибки приложения. Сообщения для пользователя — на русском."""

from __future__ import annotations


class AppError(Exception):
    def __init__(
        self,
        status: int,
        code: str,
        message: str,
        details: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.details = details or {}


class IllegalMove(AppError):
    def __init__(self, message: str = "Этот ход не допускается правилами.") -> None:
        super().__init__(422, "illegal_move", message)


class EngineError(AppError):
    def __init__(self, message: str, *, code: str = "engine_error", status: int = 503) -> None:
        super().__init__(status, code, message)


class EngineUnavailable(EngineError):
    def __init__(self, message: str) -> None:
        super().__init__(message, code="engine_unavailable", status=503)


class AnalysisIncomplete(EngineError):
    def __init__(self, message: str) -> None:
        super().__init__(message, code="analysis_incomplete", status=503)
