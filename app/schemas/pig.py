from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from uuid import UUID

from app.domain.models.pig import PigItemType, PigStatus


@dataclass(slots=True)
class ActiveEffectView:
    title: str
    summary: str
    expires_at: datetime | None


@dataclass(slots=True)
class InventoryItemView:
    item_id: int
    code: str
    title: str
    summary: str
    item_type: PigItemType
    is_equipped: bool
    durability: int | None
    expires_at: datetime | None


@dataclass(slots=True)
class PigProfile:
    pig_id: UUID
    name: str
    weight_kg: Decimal
    status: PigStatus
    trait_title: str
    trait_summary: str
    mood_score: int
    mood_label: str
    loyalty: int
    loyalty_label: str
    wins: int
    losses: int
    next_feed_in: timedelta
    next_battle_in: timedelta
    next_sabotage_in: timedelta
    next_raid_in: timedelta
    battle_ready_until: datetime | None
    raid_until: datetime | None
    equipped_item: InventoryItemView | None
    active_effects: list[ActiveEffectView]


@dataclass(slots=True)
class FeedResult:
    pig_name: str
    weight_gain: Decimal
    current_weight: Decimal
    next_feed_in: timedelta
    mood_label: str
    loyalty_label: str


@dataclass(slots=True)
class BattleEntryResult:
    pig_name: str
    ready_until: datetime
    next_battle_in: timedelta


@dataclass(slots=True)
class InventoryView:
    pig_name: str
    items: list[InventoryItemView]


@dataclass(slots=True)
class EquipResult:
    pig_name: str
    item_title: str


@dataclass(slots=True)
class UseItemResult:
    pig_name: str
    item_title: str
    outcome_text: str


@dataclass(slots=True)
class RaidStartResult:
    pig_name: str
    destination_title: str
    resolve_at: datetime
    next_raid_in: timedelta


@dataclass(slots=True)
class RaidResolutionResult:
    telegram_group_id: int
    pig_name: str
    destination_title: str
    outcome_title: str
    narrative: str
    weight_change: Decimal
    mood_label: str
    loyalty_label: str
    found_item_title: str | None
    granted_effect_title: str | None


@dataclass(slots=True)
class SabotageResult:
    attacker_name: str
    target_name: str
    success: bool
    effect_title: str | None
    narrative: str


@dataclass(slots=True)
class WorldEventView:
    title: str
    description: str
    ends_at: datetime
    effects: list[str]
