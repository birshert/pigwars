from __future__ import annotations

from datetime import datetime

from app.domain.feature_catalog import clamp_loyalty, clamp_mood_score, get_trait_definition
from app.domain.models.pig import PigTrait
from app.domain.rules.cooldowns import ensure_utc


def adjust_mood_delta(*, trait: PigTrait, delta: int) -> int:
    if delta >= 0:
        return delta

    definition = get_trait_definition(trait)
    return int(round(delta * float(definition.negative_event_modifier)))


def adjust_loyalty_delta(*, trait: PigTrait, delta: int) -> int:
    if delta >= 0:
        return delta

    definition = get_trait_definition(trait)
    return int(round(delta * float(definition.loyalty_loss_multiplier)))


def apply_mood_change(pig, *, delta: int) -> int:
    adjusted = adjust_mood_delta(trait=pig.trait, delta=delta)
    before = pig.mood_score
    pig.mood_score = clamp_mood_score(pig.mood_score + adjusted)
    return pig.mood_score - before


def apply_loyalty_change(pig, *, delta: int) -> int:
    adjusted = adjust_loyalty_delta(trait=pig.trait, delta=delta)
    before = pig.loyalty
    pig.loyalty = clamp_loyalty(pig.loyalty + adjusted)
    return pig.loyalty - before


def latest_activity_at(pig) -> datetime:
    moments = [
        pig.last_feed_at,
        pig.last_battle_at,
        pig.last_sabotage_at,
        pig.last_raid_at,
        pig.created_at,
    ]
    normalized = [ensure_utc(moment) or moment for moment in moments if moment is not None]
    return max(normalized)
