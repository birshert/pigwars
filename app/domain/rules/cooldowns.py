from __future__ import annotations

from datetime import datetime, timedelta, timezone


def ensure_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def get_remaining_cooldown(
    last_action_at: datetime | None,
    cooldown: timedelta,
    now: datetime,
) -> timedelta:
    if last_action_at is None:
        return timedelta(0)

    normalized_last_action_at = ensure_utc(last_action_at)
    normalized_now = ensure_utc(now) or now
    remaining = cooldown - (normalized_now - normalized_last_action_at)
    if remaining.total_seconds() <= 0:
        return timedelta(0)
    return remaining


def is_cooldown_ready(last_action_at: datetime | None, cooldown: timedelta, now: datetime) -> bool:
    return get_remaining_cooldown(last_action_at, cooldown, now) == timedelta(0)


def format_timedelta(value: timedelta) -> str:
    total_seconds = max(int(value.total_seconds()), 0)
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)

    if hours:
        return f"{hours} ч {minutes} мин"
    if minutes:
        return f"{minutes} мин"
    return f"{seconds} сек"
