from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from uuid import UUID

from app.domain.models.pig import PigStatus


@dataclass(slots=True)
class PigProfile:
    pig_id: UUID
    name: str
    weight_kg: Decimal
    status: PigStatus
    wins: int
    losses: int
    next_feed_in: timedelta
    next_battle_in: timedelta
    battle_ready_until: datetime | None


@dataclass(slots=True)
class FeedResult:
    pig_name: str
    weight_gain: Decimal
    current_weight: Decimal
    next_feed_in: timedelta


@dataclass(slots=True)
class BattleEntryResult:
    pig_name: str
    ready_until: datetime
    next_battle_in: timedelta
