"""Настройки. Обязательные параметры проверяются при старте."""

from __future__ import annotations

from functools import lru_cache

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_SECRET = "replace-this-local-dev-key-with-32chars-min"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    env: str = "local"
    secret_key: str
    database_url: str
    cookie_secure: bool = False
    session_ttl_hours: int = 336
    trust_proxy: bool = False
    forwarded_allow_ips: str = "127.0.0.1"
    trusted_hosts: str = "localhost,127.0.0.1,web"
    chess_engine_path: str = "stockfish"
    chess_engine_pool_size: int = 2
    chess_engine_hash_mb: int = 16
    chess_engine_threads: int = 1
    checkers_workers: int = 2
    engine_max_concurrent: int = 2
    engine_max_time_ms: int = 10_000
    login_max_failures: int = 5
    login_window_seconds: int = 900
    engine_rate_per_minute: int = 300
    valkey_url: str = ""
    engine_mode: str = "local"
    turn_secret: str = ""
    turn_host: str = ""
    turn_port: int = 3478
    turn_tls_port: int = 5349
    request_limit: int = 240
    request_window_seconds: int = 10
    max_body_bytes: int = 65_536
    news_image_dir: str = "/var/lib/parlor/news"
    news_image_bytes: int = 4_194_304
    avatar_dir: str = "/var/lib/parlor/news/avatars"
    avatar_bytes: int = 10_485_760
    allow_registration: bool = False
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_tls: bool = True
    smtp_ssl: bool = False
    log_level: str = "INFO"
    argon_time_cost: int = 2
    argon_memory_cost: int = 32_768
    argon_parallelism: int = 1
    asset_version: str = "3"

    @field_validator("engine_mode")
    @classmethod
    def engine_mode_known(cls, value: str) -> str:
        if value not in {"local", "remote"}:
            raise ValueError("ENGINE_MODE должен быть local или remote")
        return value

    @field_validator("secret_key")
    @classmethod
    def secret_is_long_enough(cls, value: str) -> str:
        if len(value) < 32:
            raise ValueError("SECRET_KEY должен быть не короче 32 символов")
        return value

    @field_validator("argon_memory_cost")
    @classmethod
    def argon_memory_floor(cls, value: int) -> int:
        if value < 8192:
            raise ValueError("ARGON_MEMORY_COST слишком мал для Argon2id")
        return value

    @field_validator("argon_time_cost")
    @classmethod
    def argon_time_floor(cls, value: int) -> int:
        if value < 1:
            raise ValueError("ARGON_TIME_COST должен быть не меньше 1")
        return value

    @model_validator(mode="after")
    def production_secret(self) -> Settings:
        if self.env == "production" and self.secret_key == DEV_SECRET:
            raise ValueError("В production нужен собственный SECRET_KEY, не пример из .env.example")
        return self

    @property
    def trusted_host_list(self) -> list[str]:
        hosts = [item.strip() for item in self.trusted_hosts.split(",") if item.strip()]
        if self.env == "test" and "testserver" not in hosts:
            hosts.append("testserver")
        return hosts

    @property
    def session_ttl_seconds(self) -> int:
        return self.session_ttl_hours * 3600


@lru_cache
def get_settings() -> Settings:
    return Settings()


def load_settings() -> Settings:
    get_settings.cache_clear()
    return get_settings()
