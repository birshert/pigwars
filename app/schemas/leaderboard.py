from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(slots=True)
class LeaderboardEntry:
    place: int
    pig_name: str
    owner_label: str
    weight_kg: Decimal
    wins: int
    losses: int
