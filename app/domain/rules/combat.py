from __future__ import annotations

import math
import random
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_FLOOR, ROUND_HALF_UP

from app.domain.models.battle import BattleResolution, CombatRoll, MatchupClass, WeightTransfer
from app.domain.models.pig import PigStatus
from app.domain.rules.cooldowns import ensure_utc
from app.domain.rules.weight_modifiers import get_tier_modifier


MIN_PIG_WEIGHT = Decimal("3.00")
STARTING_PIG_WEIGHT = Decimal("10.00")
FEED_GAIN_MIN = Decimal("0.40")
FEED_GAIN_MAX = Decimal("1.20")
MAX_BATTLE_WEIGHT_LOSS = Decimal("1.20")
MIN_BATTLE_WEIGHT_LOSS = Decimal("0.20")
WINNER_WEIGHT_SHARE = Decimal("0.80")
WEIGHT_TRANSFER_RATIO = Decimal("0.03")
PENNY = Decimal("0.01")
RATIO_QUANT = Decimal("0.01")
MULTIPLIER_QUANT = Decimal("0.0001")
FAIR_MATCHUP_MAX_RATIO = Decimal("1.15")
FAVORED_MATCHUP_MAX_RATIO = Decimal("1.50")
ONE = Decimal("1.00")
FIVE = Decimal("5.00")
MAX_UNDERDOG_BONUS = 6


def quantize_weight(value: Decimal) -> Decimal:
    return value.quantize(PENNY, rounding=ROUND_HALF_UP)


def quantize_ratio(value: Decimal) -> Decimal:
    return value.quantize(RATIO_QUANT, rounding=ROUND_HALF_UP)


def quantize_multiplier(value: Decimal) -> Decimal:
    return value.quantize(MULTIPLIER_QUANT, rounding=ROUND_HALF_UP)


def clamp_decimal(value: Decimal, minimum: Decimal, maximum: Decimal) -> Decimal:
    return max(minimum, min(value, maximum))


def roll_feed_gain(rng: random.Random) -> Decimal:
    scaled = rng.uniform(float(FEED_GAIN_MIN), float(FEED_GAIN_MAX))
    return quantize_weight(Decimal(str(scaled)))


def base_power(weight_kg: Decimal) -> Decimal:
    return quantize_weight(Decimal(str(math.sqrt(float(weight_kg)) * 6)))


def calculate_underdog_bonus(weight_kg: Decimal, opponent_weight_kg: Decimal) -> int:
    if weight_kg <= Decimal("0.00") or weight_kg >= opponent_weight_kg:
        return 0

    scaled_gap = ((opponent_weight_kg / weight_kg) - ONE) * FIVE
    floored_gap = scaled_gap.to_integral_value(rounding=ROUND_FLOOR)
    return min(MAX_UNDERDOG_BONUS, max(0, int(floored_gap)))


def calculate_weight_ratio(weight1_kg: Decimal, weight2_kg: Decimal) -> Decimal:
    raw_ratio = _calculate_raw_weight_ratio(weight1_kg, weight2_kg)
    return quantize_ratio(raw_ratio)


def _calculate_raw_weight_ratio(weight1_kg: Decimal, weight2_kg: Decimal) -> Decimal:
    lighter = min(weight1_kg, weight2_kg)
    heavier = max(weight1_kg, weight2_kg)
    if lighter <= Decimal("0.00"):
        return ONE
    return heavier / lighter


def classify_matchup(weight1_kg: Decimal, weight2_kg: Decimal) -> MatchupClass:
    ratio = _calculate_raw_weight_ratio(weight1_kg, weight2_kg)
    if ratio <= FAIR_MATCHUP_MAX_RATIO:
        return MatchupClass.FAIR
    if ratio <= FAVORED_MATCHUP_MAX_RATIO:
        return MatchupClass.FAVORED
    return MatchupClass.STOMP


def get_weight_transfer_multipliers(
    matchup_class: MatchupClass,
    *,
    winner_was_underdog: bool,
) -> tuple[Decimal, Decimal]:
    if matchup_class == MatchupClass.FAIR:
        return Decimal("0.75"), Decimal("0.70")
    if matchup_class == MatchupClass.FAVORED:
        if winner_was_underdog:
            return ONE, Decimal("1.10")
        return Decimal("0.75"), Decimal("0.55")
    if winner_was_underdog:
        return Decimal("1.15"), Decimal("1.35")
    return Decimal("0.60"), Decimal("0.25")


def calculate_weight_transfer(
    *,
    winner_weight_kg: Decimal,
    loser_weight_kg: Decimal,
    winner_reward_modifier: Decimal = Decimal("0.00"),
) -> WeightTransfer:
    weight_ratio = calculate_weight_ratio(winner_weight_kg, loser_weight_kg)
    matchup_class = classify_matchup(winner_weight_kg, loser_weight_kg)
    winner_was_underdog = winner_weight_kg < loser_weight_kg
    loser_loss_multiplier, winner_gain_multiplier = get_weight_transfer_multipliers(
        matchup_class,
        winner_was_underdog=winner_was_underdog,
    )

    base_loser_loss = calculate_weight_loss(loser_weight_kg)
    max_available_loss = max(loser_weight_kg - MIN_PIG_WEIGHT, Decimal("0.00"))
    adjusted_loser_loss = quantize_weight(min(base_loser_loss * loser_loss_multiplier, max_available_loss))
    winner_gain = quantize_weight(
        adjusted_loser_loss
        * WINNER_WEIGHT_SHARE
        * winner_gain_multiplier
        * (ONE + winner_reward_modifier)
    )

    return WeightTransfer(
        matchup_class=matchup_class,
        weight_ratio=weight_ratio,
        winner_was_underdog=winner_was_underdog,
        loser_loss_multiplier=loser_loss_multiplier,
        winner_gain_multiplier=winner_gain_multiplier,
        transfer_multiplier=quantize_multiplier(loser_loss_multiplier * winner_gain_multiplier),
        winner_gain=winner_gain,
        loser_loss=adjusted_loser_loss,
    )


def build_combat_roll(
    pig_id,
    pig_name: str,
    weight_kg: Decimal,
    *,
    opponent_weight_kg: Decimal,
    rng: random.Random,
    external_modifier: Decimal = Decimal("0.00"),
) -> CombatRoll:
    modifier = get_tier_modifier(weight_kg)
    underdog_bonus = calculate_underdog_bonus(weight_kg, opponent_weight_kg)
    random_roll = rng.randint(1, 20)
    agility_roll = rng.randint(0, 6) + modifier.agility_bonus + underdog_bonus
    power = base_power(weight_kg)
    combat_score = power + modifier.power_bonus + Decimal(random_roll + agility_roll)
    combat_score = quantize_weight(combat_score * (ONE + external_modifier))

    return CombatRoll(
        pig_id=pig_id,
        pig_name=pig_name,
        weight_kg=weight_kg,
        tier=modifier.tier,
        base_power=power,
        power_bonus=modifier.power_bonus,
        agility_bonus=modifier.agility_bonus,
        underdog_bonus=underdog_bonus,
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
    pig1_modifier: Decimal = Decimal("0.00"),
    pig2_modifier: Decimal = Decimal("0.00"),
    winner_reward_modifier: Decimal = Decimal("0.00"),
) -> BattleResolution:
    roll1 = build_combat_roll(
        pig1.id,
        pig1.name,
        pig1.weight_kg,
        opponent_weight_kg=pig2.weight_kg,
        rng=rng,
        external_modifier=pig1_modifier,
    )
    roll2 = build_combat_roll(
        pig2.id,
        pig2.name,
        pig2.weight_kg,
        opponent_weight_kg=pig1.weight_kg,
        rng=rng,
        external_modifier=pig2_modifier,
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

    weight_transfer = calculate_weight_transfer(
        winner_weight_kg=winner.weight_kg,
        loser_weight_kg=loser.weight_kg,
        winner_reward_modifier=winner_reward_modifier,
    )

    return BattleResolution(
        winner=winner,
        loser=loser,
        weight_transfer=weight_transfer,
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
    if status in {PigStatus.IN_BATTLE, PigStatus.ON_RAID, PigStatus.QUARANTINED}:
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
