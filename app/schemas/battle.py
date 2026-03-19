from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(slots=True)
class BattleMessagePayload:
    telegram_group_id: int
    pig1_name: str
    pig1_weight: Decimal
    pig2_name: str
    pig2_weight: Decimal
    winner_name: str
    loser_name: str
    winner_gain: Decimal
    loser_loss: Decimal
    winner_trait_title: str
    loser_trait_title: str
    winner_loot_title: str | None
    broken_item_title: str | None
    flavor_text: str | None
