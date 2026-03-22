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
    interval_minutes: int,
    day_start_hour_msk: int,
    day_end_hour_msk: int,
) -> DiseaseSlot | None:
    local_now = to_msk(now)
    if interval_minutes <= 0:
        return None
    if local_now.minute % interval_minutes != 0:
        return None

    current_hour = local_now.hour
    is_day_slot = day_start_hour_msk <= current_hour < day_end_hour_msk
    slot_kind = "day" if is_day_slot else "night"
    label = "дневной слот" if is_day_slot else "ночной слот"
    return _build_slot(local_now, slot_kind=slot_kind, label=label)

def _build_slot(local_now: datetime, *, slot_kind: str, label: str) -> DiseaseSlot:
    scheduled_local = local_now.replace(second=0, microsecond=0, tzinfo=MSK_TIMEZONE)
    return DiseaseSlot(
        scheduled_for=scheduled_local.astimezone(timezone.utc),
        slot_kind=slot_kind,
        label=label,
    )
