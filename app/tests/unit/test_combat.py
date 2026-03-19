from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from app.domain.models.pig import WeightTier
from app.domain.rules.combat import calculate_weight_loss, resolve_battle
from app.domain.rules.weight_modifiers import get_weight_tier


@dataclass
class StubPig:
    id: object
    name: str
    weight_kg: Decimal


def test_weight_tier_boundaries() -> None:
    assert get_weight_tier(Decimal("14.99")) == WeightTier.PIGLET
    assert get_weight_tier(Decimal("15.00")) == WeightTier.BRUISER
    assert get_weight_tier(Decimal("30.00")) == WeightTier.BOAR
    assert get_weight_tier(Decimal("60.00")) == WeightTier.TANK


def test_weight_loss_respects_floor() -> None:
    assert calculate_weight_loss(Decimal("3.10")) == Decimal("0.10")
    assert calculate_weight_loss(Decimal("50.00")) == Decimal("2.00")


def test_resolve_battle_returns_winner_and_weight_changes() -> None:
    pig1 = StubPig(id=uuid4(), name="Alpha", weight_kg=Decimal("20.00"))
    pig2 = StubPig(id=uuid4(), name="Beta", weight_kg=Decimal("18.00"))

    result = resolve_battle(
        pig1,
        pig2,
        rng=random.Random(4),
        now=datetime(2026, 3, 19, tzinfo=timezone.utc),
    )

    assert result.winner.pig_id in {pig1.id, pig2.id}
    assert result.loser.pig_id in {pig1.id, pig2.id}
    assert result.winner_gain > Decimal("0.00")
    assert result.loser_loss > Decimal("0.00")
