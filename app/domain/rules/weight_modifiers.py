from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.domain.models.pig import WeightTier


THREE = Decimal("3.00")
TEN = Decimal("10.00")


@dataclass(frozen=True, slots=True)
class TierModifier:
    tier: WeightTier
    label: str
    power_bonus: Decimal
    agility_bonus: int


PIGLET_MODIFIER = TierModifier(
    tier=WeightTier.PIGLET,
    label="Поросёнок",
    power_bonus=Decimal("-1.00"),
    agility_bonus=2,
)
BRUISER_MODIFIER = TierModifier(
    tier=WeightTier.BRUISER,
    label="Крепыш",
    power_bonus=Decimal("0.00"),
    agility_bonus=0,
)
BOAR_MODIFIER = TierModifier(
    tier=WeightTier.BOAR,
    label="Кабан",
    power_bonus=Decimal("3.00"),
    agility_bonus=-1,
)
TANK_MODIFIER = TierModifier(
    tier=WeightTier.TANK,
    label="Танк",
    power_bonus=Decimal("5.00"),
    agility_bonus=-2,
)


def get_weight_tier(weight_kg: Decimal) -> WeightTier:
    if weight_kg < Decimal("15.00"):
        return WeightTier.PIGLET
    if weight_kg < Decimal("30.00"):
        return WeightTier.BRUISER
    if weight_kg < Decimal("60.00"):
        return WeightTier.BOAR
    return WeightTier.TANK


def get_tier_modifier(weight_kg: Decimal) -> TierModifier:
    tier = get_weight_tier(weight_kg)
    if tier == WeightTier.PIGLET:
        return PIGLET_MODIFIER
    if tier == WeightTier.BRUISER:
        return BRUISER_MODIFIER
    if tier == WeightTier.BOAR:
        return BOAR_MODIFIER
    return TANK_MODIFIER
