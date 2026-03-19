from __future__ import annotations

from datetime import datetime
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
