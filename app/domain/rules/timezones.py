from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from app.domain.rules.cooldowns import ensure_utc


MSK_TIMEZONE = ZoneInfo("Europe/Moscow")


def to_msk(value: datetime) -> datetime:
    normalized = ensure_utc(value) or value
    return normalized.astimezone(MSK_TIMEZONE)


def format_time_msk(value: datetime) -> str:
    localized = to_msk(value)
    return localized.strftime("%H:%M МСК")


def format_datetime_msk(value: datetime) -> str:
    localized = to_msk(value)
    return localized.strftime("%d.%m %H:%M МСК")


def get_game_day(value: datetime) -> date:
    return to_msk(value).date()


def get_previous_game_day(value: datetime) -> date:
    return get_game_day(value) - timedelta(days=1)


def get_game_day_bounds(day: date) -> tuple[datetime, datetime]:
    start_local = datetime.combine(day, time.min, tzinfo=MSK_TIMEZONE)
    end_local = start_local + timedelta(days=1)
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


def end_of_game_day(value: datetime) -> datetime:
    localized = to_msk(value)
    next_midnight = datetime.combine(localized.date() + timedelta(days=1), time.min, tzinfo=MSK_TIMEZONE)
    return next_midnight.astimezone(timezone.utc)
