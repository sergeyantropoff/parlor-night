"""Схемы JSON API."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: dict[str, object] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    error: ErrorDetail


class CreateGameBody(BaseModel):
    game_type: Literal["chess", "checkers", "go", "poker", "uno", "durak", "blackjack", "preferans"]
    board_size: int | None = Field(default=None, ge=9, le=19)
    durak_kind: Literal["podkidnoy", "perevodnoy"] | None = None
    pool: int | None = Field(default=None, ge=6, le=20)
    mode: Literal["vs_computer", "free", "analysis", "lesson", "online"]
    player_side: Literal["white", "black"]
    engine_level: int = Field(default=3, ge=1, le=5)
    engine_time_ms: int = Field(default=1000, ge=100, le=10000)
    audience: Literal["open", "closed"] = "closed"
    computers: int | None = Field(default=None, ge=0, le=5)
    open_seats: int | None = Field(default=None, ge=0, le=5)
    initial_fen: str | None = None
    pgn: str | None = None
    initial_position: str | None = None
    moves: list[str] | None = None


class MoveBody(BaseModel):
    version: int = Field(ge=1)
    path: list[str] = Field(min_length=2, max_length=13)
    promotion: Literal["q", "r", "b", "n"] | None = None


class VersionBody(BaseModel):
    version: int = Field(ge=1)


class GoCommandBody(BaseModel):
    command_id: str = Field(min_length=8, max_length=80)
    version: int = Field(ge=1)
    action: Literal["move", "pass", "resign", "mark", "agree", "resume"]
    col: int | None = Field(default=None, ge=0, le=18)
    row: int | None = Field(default=None, ge=0, le=18)


class JoinBody(BaseModel):
    code: str = Field(min_length=8, max_length=8)


class InviteBody(BaseModel):
    username: str = Field(min_length=1, max_length=32)


class SettingsBody(BaseModel):
    theme: Literal["system", "light", "dark"]
    board_style: Literal["classic", "contrast"]
    default_game: Literal["chess", "checkers", "go", "uno", "poker", "durak", "blackjack", "preferans"]
    default_side: Literal["white", "black"]
    chess_depth: int = Field(default=12, ge=1, le=30)
    chess_time_ms: int = Field(default=1000, ge=100, le=10000)
    chess_multipv: int = Field(default=3, ge=1, le=3)
    checkers_level: int = Field(default=3, ge=1, le=5)
    checkers_time_ms: int = Field(default=1000, ge=100, le=10000)


class ThemeBody(BaseModel):
    theme: Literal["system", "light", "dark"]


class UserBody(BaseModel):
    username: str
    password: str
    role: Literal["admin", "user"] = "user"


class RegisterBody(BaseModel):
    username: str = Field(min_length=1, max_length=32)
    password: str = Field(min_length=1, max_length=200)
    client_id: str = Field(min_length=2, max_length=63)
    born_day: str = Field(min_length=1, max_length=2)
    born_month: str = Field(min_length=1, max_length=2)
    born_year: str = Field(min_length=4, max_length=4)
    captcha: str = Field(min_length=20, max_length=4000)
    referral: str = Field(default="", max_length=12)


class ApiLoginBody(BaseModel):
    username: str = Field(min_length=1, max_length=32)
    password: str = Field(min_length=1, max_length=200)
    client_id: str = Field(min_length=2, max_length=63)


class RefreshBody(BaseModel):
    refresh_token: str = Field(min_length=20, max_length=200)


class AuthCodeBody(BaseModel):
    grant_type: Literal["authorization_code"]
    code: str = Field(min_length=20, max_length=200)
    client_id: str = Field(min_length=2, max_length=63)
    client_secret: str = Field(min_length=1, max_length=200)
    redirect_uri: str = Field(min_length=8, max_length=500)


class AccountBody(BaseModel):
    family: str | None = Field(default=None, max_length=80)
    given: str | None = Field(default=None, max_length=80)
    patronymic: str | None = Field(default=None, max_length=80)
    born_day: str | None = Field(default=None, max_length=2)
    born_month: str | None = Field(default=None, max_length=2)
    born_year: str | None = Field(default=None, max_length=4)
    confirm: bool = False


class PasswordBody(BaseModel):
    current_password: str = Field(min_length=1, max_length=200)
    new_password: str = Field(min_length=1, max_length=200)
    repeat_password: str = Field(min_length=1, max_length=200)


class UsernameBody(BaseModel):
    username: str = Field(min_length=1, max_length=32)


class ChallengeBody(BaseModel):
    game_type: str = Field(min_length=1, max_length=32)


class SeekBody(BaseModel):
    game_type: str = Field(min_length=1, max_length=32)
    seats: int | None = Field(default=None, ge=2, le=6)


class MessageBody(BaseModel):
    body: str = Field(min_length=1, max_length=1000)


class ChipGrantBody(BaseModel):
    amount: int = Field(ge=1, le=100_000)
