from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from app.domain.rules.timezones import MSK_TIMEZONE, to_msk


@dataclass(frozen=True, slots=True)
class DiseaseSlot:
    scheduled_for: datetime
    slot_kind: str
    label: str


def get_current_disease_slot(
    now: datetime,
    *,
    interval_hours: int,
    day_start_hour_msk: int,
    day_end_hour_msk: int,
    night_hour_msk: int,
) -> DiseaseSlot | None:
    local_now = to_msk(now)
    current_hour = local_now.hour

    if current_hour == night_hour_msk:
        return _build_slot(local_now, slot_kind="night", label="ночной слот")

    day_hours = range(day_start_hour_msk, day_end_hour_msk, interval_hours)
    if current_hour in day_hours:
        return _build_slot(local_now, slot_kind="day", label="дневной слот")

    return None


def _build_slot(local_now: datetime, *, slot_kind: str, label: str) -> DiseaseSlot:
    scheduled_local = local_now.replace(minute=0, second=0, microsecond=0, tzinfo=MSK_TIMEZONE)
    return DiseaseSlot(
        scheduled_for=scheduled_local.astimezone(timezone.utc),
        slot_kind=slot_kind,
        label=label,
    )
