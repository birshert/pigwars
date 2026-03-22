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
    ON_RAID = "on_raid"
    QUARANTINED = "quarantined"
    DEAD = "dead"


class PigTrait(StrEnum):
    AGGRESSIVE = "aggressive"
    GLUTTON = "glutton"
    CUNNING = "cunning"
    STUBBORN = "stubborn"
    LUCKY = "lucky"
    PHLEGMATIC = "phlegmatic"


class WeightTier(StrEnum):
    PIGLET = "piglet"
    BRUISER = "bruiser"
    BOAR = "boar"
    TANK = "tank"


class MoodTier(StrEnum):
    ECSTATIC = "ecstatic"
    HAPPY = "happy"
    NEUTRAL = "neutral"
    UPSET = "upset"
    FURIOUS = "furious"


class LoyaltyTier(StrEnum):
    DEVOTED = "devoted"
    STEADY = "steady"
    SHAKY = "shaky"
    MUTINOUS = "mutinous"


class PigItemType(StrEnum):
    EQUIPMENT = "equipment"
    CONSUMABLE = "consumable"


class RaidDestination(StrEnum):
    DUMP = "dump"
    MARKET = "market"
    WOODS = "woods"
    MILL = "mill"
    PIER = "pier"
    MANOR = "manor"


class PigRaidStatus(StrEnum):
    ACTIVE = "active"
    RESOLVED = "resolved"
    FAILED = "failed"


@dataclass(slots=True)
class PigSnapshot:
    id: UUID
    name: str
    weight_kg: Decimal
    status: PigStatus
    trait: PigTrait
    mood_score: int
    loyalty: int
    wins: int
    losses: int
    last_feed_at: datetime | None
    last_battle_at: datetime | None
    last_sabotage_at: datetime | None
    last_raid_at: datetime | None
    battle_ready_until: datetime | None
    raid_until: datetime | None
    quarantine_until: datetime | None


@dataclass(slots=True)
class PigCooldowns:
    next_feed_in: timedelta
    next_battle_in: timedelta
    next_sabotage_in: timedelta
    next_raid_in: timedelta
