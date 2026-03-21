from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from app.domain.models.battle import MatchupClass
from app.domain.models.pig import WeightTier
from app.domain.rules.combat import (
    calculate_underdog_bonus,
    calculate_weight_loss,
    calculate_weight_ratio,
    calculate_weight_transfer,
    classify_matchup,
    get_weight_transfer_multipliers,
    resolve_battle,
)
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


def test_calculate_underdog_bonus_scales_with_weight_ratio() -> None:
    assert calculate_underdog_bonus(Decimal("15.00"), Decimal("30.00")) == 5
    assert calculate_underdog_bonus(Decimal("20.00"), Decimal("40.00")) == 5
    assert calculate_underdog_bonus(Decimal("22.86"), Decimal("57.72")) == 6
    assert calculate_underdog_bonus(Decimal("30.00"), Decimal("15.00")) == 0


def test_matchup_classification_uses_weight_ratio_boundaries() -> None:
    assert calculate_weight_ratio(Decimal("10.00"), Decimal("11.50")) == Decimal("1.15")
    assert classify_matchup(Decimal("10.00"), Decimal("11.50")) == MatchupClass.FAIR
    assert classify_matchup(Decimal("10.00"), Decimal("15.00")) == MatchupClass.FAVORED
    assert classify_matchup(Decimal("10.00"), Decimal("15.01")) == MatchupClass.STOMP


def test_weight_transfer_multipliers_depend_on_matchup_and_winner() -> None:
    assert get_weight_transfer_multipliers(MatchupClass.FAIR, winner_was_underdog=False) == (
        Decimal("1.00"),
        Decimal("1.00"),
    )
    assert get_weight_transfer_multipliers(MatchupClass.FAVORED, winner_was_underdog=False) == (
        Decimal("0.90"),
        Decimal("0.65"),
    )
    assert get_weight_transfer_multipliers(MatchupClass.FAVORED, winner_was_underdog=True) == (
        Decimal("1.00"),
        Decimal("1.10"),
    )
    assert get_weight_transfer_multipliers(MatchupClass.STOMP, winner_was_underdog=True) == (
        Decimal("1.15"),
        Decimal("1.35"),
    )


def test_weight_transfer_softens_stomp_when_favorite_wins() -> None:
    transfer = calculate_weight_transfer(
        winner_weight_kg=Decimal("57.72"),
        loser_weight_kg=Decimal("22.86"),
    )

    assert transfer.matchup_class == MatchupClass.STOMP
    assert transfer.weight_ratio == Decimal("2.52")
    assert transfer.winner_was_underdog is False
    assert transfer.loser_loss == Decimal("0.86")
    assert transfer.winner_gain == Decimal("0.24")
    assert transfer.transfer_multiplier == Decimal("0.2625")


def test_weight_transfer_rewards_stomp_upset() -> None:
    transfer = calculate_weight_transfer(
        winner_weight_kg=Decimal("10.00"),
        loser_weight_kg=Decimal("20.00"),
    )

    assert transfer.matchup_class == MatchupClass.STOMP
    assert transfer.weight_ratio == Decimal("2.00")
    assert transfer.winner_was_underdog is True
    assert transfer.loser_loss == Decimal("1.15")
    assert transfer.winner_gain == Decimal("1.24")
    assert transfer.transfer_multiplier == Decimal("1.5525")


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
    assert result.matchup_class in {MatchupClass.FAIR, MatchupClass.FAVORED, MatchupClass.STOMP}
    assert result.weight_ratio >= Decimal("1.00")
