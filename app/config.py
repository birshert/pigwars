from __future__ import annotations

from datetime import timedelta
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    bot_token: str = Field(..., alias="BOT_TOKEN")
    openai_api_key: str | None = Field(None, alias="OPENAI_API_KEY")

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
    raid_cooldown_minutes: int = Field(480, alias="RAID_COOLDOWN_MINUTES")
    raid_duration_minutes: int = Field(10, alias="RAID_DURATION_MINUTES")
    sabotage_cooldown_minutes: int = Field(480, alias="SABOTAGE_COOLDOWN_MINUTES")
    world_event_duration_hours: int = Field(48, alias="WORLD_EVENT_DURATION_HOURS")
    matchmaking_interval_seconds: int = Field(30, alias="MATCHMAKING_INTERVAL_SECONDS")
    matchmaking_batch_size: int = Field(100, alias="MATCHMAKING_BATCH_SIZE")
    raid_resolution_batch_size: int = Field(100, alias="RAID_RESOLUTION_BATCH_SIZE")
    daily_digest_enabled: bool = Field(False, alias="DAILY_DIGEST_ENABLED")
    daily_digest_hour_msk: int = Field(9, alias="DAILY_DIGEST_HOUR_MSK")
    daily_digest_llm_timeout_seconds: float = Field(8.0, alias="DAILY_DIGEST_LLM_TIMEOUT_SECONDS")
    daily_digest_max_groups_per_tick: int = Field(20, alias="DAILY_DIGEST_MAX_GROUPS_PER_TICK")
    daily_digest_model: str | None = Field("gpt-5-nano", alias="DAILY_DIGEST_MODEL")
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

    @property
    def raid_cooldown(self) -> timedelta:
        return timedelta(minutes=self.raid_cooldown_minutes)

    @property
    def raid_duration(self) -> timedelta:
        return timedelta(minutes=self.raid_duration_minutes)

    @property
    def sabotage_cooldown(self) -> timedelta:
        return timedelta(minutes=self.sabotage_cooldown_minutes)

    @property
    def world_event_duration(self) -> timedelta:
        return timedelta(hours=self.world_event_duration_hours)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
