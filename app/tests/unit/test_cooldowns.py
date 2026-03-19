from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.domain.rules.cooldowns import format_timedelta, get_remaining_cooldown


def test_remaining_cooldown_is_zero_when_never_used() -> None:
    now = datetime.now(timezone.utc)
    assert get_remaining_cooldown(None, timedelta(hours=1), now) == timedelta(0)


def test_remaining_cooldown_is_positive_when_still_waiting() -> None:
    now = datetime(2026, 3, 19, 12, 0, tzinfo=timezone.utc)
    last_action_at = now - timedelta(minutes=20)

    remaining = get_remaining_cooldown(last_action_at, timedelta(hours=1), now)

    assert remaining == timedelta(minutes=40)


def test_format_timedelta_prefers_hours_when_present() -> None:
    assert format_timedelta(timedelta(hours=2, minutes=15)) == "2 ч 15 мин"
