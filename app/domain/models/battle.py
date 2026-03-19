from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from app.domain.models.pig import WeightTier


@dataclass(slots=True)
class CombatRoll:
    pig_id: UUID
    pig_name: str
    weight_kg: Decimal
    tier: WeightTier
    base_power: Decimal
    power_bonus: Decimal
    agility_bonus: int
    upset_bonus: int
    random_roll: int
    agility_roll: int
    combat_score: Decimal


@dataclass(slots=True)
class BattleResolution:
    winner: CombatRoll
    loser: CombatRoll
    winner_gain: Decimal
    loser_loss: Decimal
    happened_at: datetime
