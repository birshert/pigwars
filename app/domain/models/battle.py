from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from app.domain.models.pig import WeightTier


class MatchupClass(StrEnum):
    FAIR = "fair"
    FAVORED = "favored"
    STOMP = "stomp"


@dataclass(slots=True)
class CombatRoll:
    pig_id: UUID
    pig_name: str
    weight_kg: Decimal
    tier: WeightTier
    base_power: Decimal
    power_bonus: Decimal
    agility_bonus: int
    underdog_bonus: int
    random_roll: int
    agility_roll: int
    combat_score: Decimal


@dataclass(slots=True)
class WeightTransfer:
    matchup_class: MatchupClass
    weight_ratio: Decimal
    winner_was_underdog: bool
    loser_loss_multiplier: Decimal
    winner_gain_multiplier: Decimal
    transfer_multiplier: Decimal
    winner_gain: Decimal
    loser_loss: Decimal


@dataclass(slots=True)
class BattleResolution:
    winner: CombatRoll
    loser: CombatRoll
    weight_transfer: WeightTransfer
    happened_at: datetime

    @property
    def matchup_class(self) -> MatchupClass:
        return self.weight_transfer.matchup_class

    @property
    def weight_ratio(self) -> Decimal:
        return self.weight_transfer.weight_ratio

    @property
    def winner_was_underdog(self) -> bool:
        return self.weight_transfer.winner_was_underdog

    @property
    def loser_loss_multiplier(self) -> Decimal:
        return self.weight_transfer.loser_loss_multiplier

    @property
    def winner_gain_multiplier(self) -> Decimal:
        return self.weight_transfer.winner_gain_multiplier

    @property
    def transfer_multiplier(self) -> Decimal:
        return self.weight_transfer.transfer_multiplier

    @property
    def winner_gain(self) -> Decimal:
        return self.weight_transfer.winner_gain

    @property
    def loser_loss(self) -> Decimal:
        return self.weight_transfer.loser_loss
