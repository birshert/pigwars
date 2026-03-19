from __future__ import annotations

from datetime import datetime, timezone

from app.domain.rules.timezones import format_datetime_msk, format_time_msk


def test_format_time_msk_converts_from_utc() -> None:
    moment = datetime(2026, 3, 19, 12, 15, tzinfo=timezone.utc)

    assert format_time_msk(moment) == "15:15 МСК"


def test_format_datetime_msk_converts_from_utc() -> None:
    moment = datetime(2026, 3, 19, 21, 5, tzinfo=timezone.utc)

    assert format_datetime_msk(moment) == "20.03 00:05 МСК"
