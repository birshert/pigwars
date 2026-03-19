from __future__ import annotations

from datetime import timedelta
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    bot_token: str = Field(..., alias="BOT_TOKEN")

    postgres_host: str = Field("db", alias="POSTGRES_HOST")
    postgres_port: int = Field(5432, alias="POSTGRES_PORT")
    postgres_db: str = Field("pigwars", alias="POSTGRES_DB")
    postgres_user: str = Field("pigwars", alias="POSTGRES_USER")
    postgres_password: str = Field("pigwars", alias="POSTGRES_PASSWORD")
    database_echo: bool = Field(False, alias="DATABASE_ECHO")

    redis_url: str = Field("redis://redis:6379/0", alias="REDIS_URL")

    battle_ready_ttl_minutes: int = Field(15, alias="BATTLE_READY_TTL_MINUTES")
    feed_cooldown_minutes: int = Field(60, alias="FEED_COOLDOWN_MINUTES")
    battle_cooldown_minutes: int = Field(120, alias="BATTLE_COOLDOWN_MINUTES")
    matchmaking_interval_seconds: int = Field(30, alias="MATCHMAKING_INTERVAL_SECONDS")
    matchmaking_batch_size: int = Field(100, alias="MATCHMAKING_BATCH_SIZE")
    telegram_update_dedup_ttl_seconds: int = Field(
        300,
        alias="TELEGRAM_UPDATE_DEDUP_TTL_SECONDS",
    )

    match_base_probability: float = 0.35
    match_wait_bonus: float = 0.10
    match_wait_bonus_every_seconds: int = 120
    match_probability_cap: float = 0.85

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def postgres_dsn(self) -> str:
        return (
            "postgresql+asyncpg://"
            f"{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def feed_cooldown(self) -> timedelta:
        return timedelta(minutes=self.feed_cooldown_minutes)

    @property
    def battle_cooldown(self) -> timedelta:
        return timedelta(minutes=self.battle_cooldown_minutes)

    @property
    def battle_ready_ttl(self) -> timedelta:
        return timedelta(minutes=self.battle_ready_ttl_minutes)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
