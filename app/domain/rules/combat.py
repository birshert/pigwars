from __future__ import annotations

import math
import random
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP

from app.domain.models.battle import BattleResolution, CombatRoll
from app.domain.models.pig import PigStatus
from app.domain.rules.cooldowns import ensure_utc
from app.domain.rules.weight_modifiers import get_tier_modifier


MIN_PIG_WEIGHT = Decimal("3.00")
STARTING_PIG_WEIGHT = Decimal("10.00")
FEED_GAIN_MIN = Decimal("0.40")
FEED_GAIN_MAX = Decimal("1.20")
MAX_BATTLE_WEIGHT_LOSS = Decimal("2.00")
MIN_BATTLE_WEIGHT_LOSS = Decimal("0.30")
WINNER_WEIGHT_SHARE = Decimal("0.80")
WEIGHT_TRANSFER_RATIO = Decimal("0.05")
PENNY = Decimal("0.01")


def quantize_weight(value: Decimal) -> Decimal:
    return value.quantize(PENNY, rounding=ROUND_HALF_UP)


def clamp_decimal(value: Decimal, minimum: Decimal, maximum: Decimal) -> Decimal:
    return max(minimum, min(value, maximum))


def roll_feed_gain(rng: random.Random) -> Decimal:
    scaled = rng.uniform(float(FEED_GAIN_MIN), float(FEED_GAIN_MAX))
    return quantize_weight(Decimal(str(scaled)))


def base_power(weight_kg: Decimal) -> Decimal:
    return quantize_weight(Decimal(str(math.sqrt(float(weight_kg)) * 10)))


def build_combat_roll(
    pig_id,
    pig_name: str,
    weight_kg: Decimal,
    *,
    opponent_weight_kg: Decimal,
    rng: random.Random,
) -> CombatRoll:
    modifier = get_tier_modifier(weight_kg)
    upset_bonus = 2 if weight_kg <= opponent_weight_kg * Decimal("0.80") else 0
    random_roll = rng.randint(1, 20)
    agility_roll = rng.randint(0, 6) + modifier.agility_bonus + upset_bonus
    power = base_power(weight_kg)
    combat_score = power + modifier.power_bonus + Decimal(random_roll + agility_roll)

    return CombatRoll(
        pig_id=pig_id,
        pig_name=pig_name,
        weight_kg=weight_kg,
        tier=modifier.tier,
        base_power=power,
        power_bonus=modifier.power_bonus,
        agility_bonus=modifier.agility_bonus,
        upset_bonus=upset_bonus,
        random_roll=random_roll,
        agility_roll=agility_roll,
        combat_score=quantize_weight(combat_score),
    )


def resolve_battle(
    pig1,
    pig2,
    *,
    rng: random.Random,
    now: datetime,
) -> BattleResolution:
    roll1 = build_combat_roll(
        pig1.id,
        pig1.name,
        pig1.weight_kg,
        opponent_weight_kg=pig2.weight_kg,
        rng=rng,
    )
    roll2 = build_combat_roll(
        pig2.id,
        pig2.name,
        pig2.weight_kg,
        opponent_weight_kg=pig1.weight_kg,
        rng=rng,
    )

    if roll1.combat_score > roll2.combat_score:
        winner, loser = roll1, roll2
    elif roll2.combat_score > roll1.combat_score:
        winner, loser = roll2, roll1
    elif roll1.random_roll > roll2.random_roll:
        winner, loser = roll1, roll2
    elif roll2.random_roll > roll1.random_roll:
        winner, loser = roll2, roll1
    elif roll1.agility_roll >= roll2.agility_roll:
        winner, loser = roll1, roll2
    else:
        winner, loser = roll2, roll1

    loser_loss = calculate_weight_loss(loser.weight_kg)
    winner_gain = quantize_weight(loser_loss * WINNER_WEIGHT_SHARE)

    return BattleResolution(
        winner=winner,
        loser=loser,
        winner_gain=winner_gain,
        loser_loss=loser_loss,
        happened_at=now,
    )


def calculate_weight_loss(loser_weight_kg: Decimal) -> Decimal:
    base_loss = loser_weight_kg * WEIGHT_TRANSFER_RATIO
    clamped = clamp_decimal(base_loss, MIN_BATTLE_WEIGHT_LOSS, MAX_BATTLE_WEIGHT_LOSS)
    safe_loss = min(clamped, loser_weight_kg - MIN_PIG_WEIGHT)
    return quantize_weight(max(safe_loss, Decimal("0.00")))


def pig_can_enter_battle(status: PigStatus, battle_ready_until: datetime | None, now: datetime) -> bool:
    normalized_ready_until = ensure_utc(battle_ready_until)
    normalized_now = ensure_utc(now) or now
    if status == PigStatus.IN_BATTLE:
        return False
    if status == PigStatus.BATTLE_READY and normalized_ready_until and normalized_ready_until > normalized_now:
        return False
    return True


def calculate_match_probability(
    wait_started_at: datetime,
    *,
    now: datetime,
    base_probability: float,
    wait_bonus_every: timedelta,
    wait_bonus: float,
    probability_cap: float,
) -> float:
    normalized_now = ensure_utc(now) or now
    normalized_wait_started_at = ensure_utc(wait_started_at) or wait_started_at
    waited_seconds = max((normalized_now - normalized_wait_started_at).total_seconds(), 0.0)
    increments = int(waited_seconds // wait_bonus_every.total_seconds())
    probability = base_probability + (increments * wait_bonus)
    return min(probability, probability_cap)
