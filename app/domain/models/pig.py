from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from uuid import UUID


class PigStatus(StrEnum):
    IDLE = "idle"
    BATTLE_READY = "battle_ready"
    IN_BATTLE = "in_battle"


class WeightTier(StrEnum):
    PIGLET = "piglet"
    BRUISER = "bruiser"
    BOAR = "boar"
    TANK = "tank"


@dataclass(slots=True)
class PigSnapshot:
    id: UUID
    name: str
    weight_kg: Decimal
    status: PigStatus
    wins: int
    losses: int
    last_feed_at: datetime | None
    last_battle_at: datetime | None
    battle_ready_until: datetime | None


@dataclass(slots=True)
class PigCooldowns:
    next_feed_in: timedelta
    next_battle_in: timedelta
