from __future__ import annotations

from typing import Annotated
from datetime import timedelta
from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


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
    raid_cooldown_minutes: int = Field(480, alias="RAID_COOLDOWN_MINUTES")
    raid_duration_minutes: int = Field(10, alias="RAID_DURATION_MINUTES")
    sabotage_cooldown_minutes: int = Field(480, alias="SABOTAGE_COOLDOWN_MINUTES")
    world_event_duration_hours: int = Field(48, alias="WORLD_EVENT_DURATION_HOURS")
    matchmaking_interval_seconds: int = Field(30, alias="MATCHMAKING_INTERVAL_SECONDS")
    matchmaking_batch_size: int = Field(100, alias="MATCHMAKING_BATCH_SIZE")
    raid_resolution_batch_size: int = Field(100, alias="RAID_RESOLUTION_BATCH_SIZE")
    disease_enabled: bool = Field(True, alias="DISEASE_ENABLED")
    disease_interval_minutes: int = Field(15, alias="DISEASE_INTERVAL_MINUTES")
    disease_day_start_hour_msk: int = Field(9, alias="DISEASE_DAY_START_HOUR_MSK")
    disease_day_end_hour_msk: int = Field(23, alias="DISEASE_DAY_END_HOUR_MSK")
    disease_day_chance: float = Field(0.50, alias="DISEASE_DAY_CHANCE")
    disease_night_chance: float = Field(0.50, alias="DISEASE_NIGHT_CHANCE")
    disease_repeat_cooldown_hours: int = Field(18, alias="DISEASE_REPEAT_COOLDOWN_HOURS")
    disease_weight_loss_min_percent: int = Field(5, alias="DISEASE_WEIGHT_LOSS_MIN_PERCENT")
    disease_weight_loss_max_percent: int = Field(50, alias="DISEASE_WEIGHT_LOSS_MAX_PERCENT")
    disease_resolution_batch_size: int = Field(100, alias="DISEASE_RESOLUTION_BATCH_SIZE")
    daily_digest_enabled: bool = Field(False, alias="DAILY_DIGEST_ENABLED")
    daily_digest_hour_msk: int = Field(9, alias="DAILY_DIGEST_HOUR_MSK")
    daily_digest_max_groups_per_tick: int = Field(20, alias="DAILY_DIGEST_MAX_GROUPS_PER_TICK")
    daily_digest_group_allowlist: Annotated[tuple[int, ...], NoDecode] = Field(
        default_factory=tuple,
        alias="DAILY_DIGEST_GROUP_ALLOWLIST",
    )
    telegram_update_dedup_ttl_seconds: int = Field(
        300,
        alias="TELEGRAM_UPDATE_DEDUP_TTL_SECONDS",
    )
    mini_app_url: str | None = Field(None, alias="MINI_APP_URL")
    player_mini_app_url: str | None = Field(None, alias="PLAYER_MINI_APP_URL")
    admin_telegram_user_ids: tuple[int, ...] = Field(default_factory=tuple, alias="ADMIN_TELEGRAM_USER_IDS")
    web_host: str = Field("0.0.0.0", alias="WEB_HOST")
    web_port: int = Field(8080, alias="WEB_PORT")
    ngrok_api_url: str | None = Field(None, alias="NGROK_API_URL")
    telegram_webapp_auth_max_age_seconds: int = Field(
        86400,
        alias="TELEGRAM_WEBAPP_AUTH_MAX_AGE_SECONDS",
    )

    match_base_probability: float = 0.35
    match_wait_bonus: float = 0.10
    match_wait_bonus_every_seconds: int = 120
    match_probability_cap: float = 0.85

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    @field_validator("admin_telegram_user_ids", mode="before")
    @classmethod
    def _parse_admin_telegram_user_ids(cls, value: object) -> tuple[int, ...]:
        return cls._parse_int_tuple(value, env_name="ADMIN_TELEGRAM_USER_IDS")

    @field_validator("daily_digest_group_allowlist", mode="before")
    @classmethod
    def _parse_daily_digest_group_allowlist(cls, value: object) -> tuple[int, ...]:
        return cls._parse_int_tuple(value, env_name="DAILY_DIGEST_GROUP_ALLOWLIST")

    @classmethod
    def _parse_int_tuple(cls, value: object, *, env_name: str) -> tuple[int, ...]:
        if value in (None, "", ()):
            return ()
        if isinstance(value, str):
            return tuple(
                int(chunk.strip())
                for chunk in value.split(",")
                if chunk.strip()
            )
        if isinstance(value, int):
            return (value,)
        if isinstance(value, (list, tuple, set)):
            return tuple(int(item) for item in value)
        raise TypeError(f"{env_name} must be a comma-separated string or a sequence of integers")

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
    def disease_repeat_cooldown(self) -> timedelta:
        return timedelta(hours=self.disease_repeat_cooldown_hours)

    @property
    def world_event_duration(self) -> timedelta:
        return timedelta(hours=self.world_event_duration_hours)

    def is_admin_telegram_user(self, telegram_user_id: int) -> bool:
        return telegram_user_id in self.admin_telegram_user_ids

    def is_daily_digest_allowed_for_group(self, telegram_group_id: int) -> bool:
        if not self.daily_digest_group_allowlist:
            return True
        return telegram_group_id in self.daily_digest_group_allowlist


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
