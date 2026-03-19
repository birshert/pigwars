from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from app.db.models import PigEffect, PigItem
from app.db.repositories.effect_repo import PigEffectRepository
from app.db.repositories.item_repo import PigItemRepository
from app.db.repositories.world_event_repo import WorldEventRepository
from app.domain.feature_catalog import (
    clamp_mood_score,
    EFFECT_WET_NEWSPAPER_CURSE,
    get_effect_definition,
    get_item_definition,
    get_loyalty_label,
    get_mood_label,
    get_raid_destination,
    get_trait_definition,
    get_world_event_definition,
    hours_since,
)
from app.domain.models.pig import PigTrait
from app.domain.rules.pig_state import latest_activity_at
from app.schemas.pig import ActiveEffectView, InventoryItemView


COMBAT_MODIFIER_CAP = Decimal("0.20")
COMBAT_MODIFIER_FLOOR = Decimal("-0.20")
FEED_MODIFIER_CAP = Decimal("0.35")
FEED_MODIFIER_FLOOR = Decimal("-0.50")
RAID_MODIFIER_CAP = Decimal("0.25")
RAID_MODIFIER_FLOOR = Decimal("-0.25")
SABOTAGE_CHANCE_MIN = Decimal("0.15")
SABOTAGE_CHANCE_MAX = Decimal("0.90")


@dataclass(slots=True)
class ResolvedProfileState:
    trait_title: str
    trait_summary: str
    mood_score: int
    mood_label: str
    loyalty_label: str
    equipped_item: InventoryItemView | None
    active_effects: list[ActiveEffectView]
    world_event_title: str | None
    world_event_description: str | None


@dataclass(slots=True)
class ResolvedFeedState:
    modifier: Decimal
    one_shot_effects: list[PigEffect]


@dataclass(slots=True)
class ResolvedCombatState:
    modifier: Decimal
    reward_modifier: Decimal
    active_effects: list[PigEffect]
    one_shot_effects: list[PigEffect]
    equipped_item: PigItem | None


@dataclass(slots=True)
class ResolvedRaidState:
    modifier: Decimal
    reward_multiplier: Decimal
    item_modifier: Decimal
    bad_outcome_modifier: Decimal
    active_effects: list[PigEffect]
    one_shot_effects: list[PigEffect]
    guard_effect: PigEffect | None
    equipped_item: PigItem | None
    world_event_title: str | None


@dataclass(slots=True)
class ResolvedSabotageState:
    success_chance: float
    world_event_title: str | None


@dataclass(slots=True)
class _ResolvedPigContext:
    trait_title: str
    trait_summary: str
    effective_mood_score: int
    loyalty_label: str
    active_effects: list[PigEffect]
    equipped_item: PigItem | None
    world_event_code: str | None


class PigModifierResolver:
    def __init__(self, session) -> None:
        self._items = PigItemRepository(session)
        self._effects = PigEffectRepository(session)
        self._world_events = WorldEventRepository(session)

    async def resolve_profile_state(self, pig, *, now: datetime) -> ResolvedProfileState:
        context = await self._build_context(pig, now=now)
        world_event = await self._world_events.get_active(now=now)
        return ResolvedProfileState(
            trait_title=context.trait_title,
            trait_summary=context.trait_summary,
            mood_score=context.effective_mood_score,
            mood_label=get_mood_label(context.effective_mood_score),
            loyalty_label=context.loyalty_label,
            equipped_item=self._to_item_view(context.equipped_item),
            active_effects=[self._to_effect_view(effect) for effect in context.active_effects],
            world_event_title=world_event.title if world_event is not None else None,
            world_event_description=world_event.description if world_event is not None else None,
        )

    async def resolve_feed_state(self, pig, *, now: datetime) -> ResolvedFeedState:
        context = await self._build_context(pig, now=now)
        modifier = get_trait_definition(pig.trait).feed_modifier
        for effect in context.active_effects:
            modifier += get_effect_definition(effect.effect_type).feed_modifier
        world_event = self._get_world_event_definition(context.world_event_code)
        if world_event is not None:
            modifier += world_event.feed_modifier
        return ResolvedFeedState(
            modifier=self._cap_modifier(modifier, minimum=FEED_MODIFIER_FLOOR, maximum=FEED_MODIFIER_CAP),
            one_shot_effects=self._one_shot_effects(context.active_effects, action="feed"),
        )

    async def resolve_combat_state(self, pig, *, now: datetime) -> ResolvedCombatState:
        context = await self._build_context(pig, now=now)
        trait = get_trait_definition(pig.trait)
        modifier = trait.combat_modifier
        modifier += self._mood_modifier(context.effective_mood_score, trait_code=pig.trait)

        if context.equipped_item is not None:
            item_definition = get_item_definition(context.equipped_item.item_code)
            modifier += item_definition.combat_modifier * trait.equipment_modifier

        for effect in context.active_effects:
            modifier += get_effect_definition(effect.effect_type).combat_modifier

        reward_modifier = Decimal("0")
        world_event = self._get_world_event_definition(context.world_event_code)
        if world_event is not None:
            modifier += world_event.battle_modifier
            reward_modifier += world_event.battle_reward_modifier

        return ResolvedCombatState(
            modifier=self._cap_modifier(modifier, minimum=COMBAT_MODIFIER_FLOOR, maximum=COMBAT_MODIFIER_CAP),
            reward_modifier=reward_modifier,
            active_effects=context.active_effects,
            one_shot_effects=self._one_shot_effects(context.active_effects, action="battle"),
            equipped_item=context.equipped_item,
        )

    async def resolve_raid_state(self, pig, *, destination, now: datetime) -> ResolvedRaidState:
        context = await self._build_context(pig, now=now)
        trait = get_trait_definition(pig.trait)
        destination_definition = get_raid_destination(destination)
        modifier = trait.raid_modifier
        modifier += self._mood_modifier(context.effective_mood_score, trait_code=pig.trait)
        modifier += self._raid_loyalty_modifier(pig.loyalty)

        if context.equipped_item is not None:
            item_definition = get_item_definition(context.equipped_item.item_code)
            modifier += item_definition.raid_modifier * trait.equipment_modifier

        one_shot_effects = self._one_shot_effects(context.active_effects, action="raid")
        for effect in one_shot_effects:
            modifier += get_effect_definition(effect.effect_type).raid_modifier

        item_modifier = destination_definition.item_chance_modifier
        bad_outcome_modifier = destination_definition.bad_outcome_modifier
        world_event = self._get_world_event_definition(context.world_event_code)
        world_event_title = None
        if world_event is not None:
            modifier += world_event.raid_modifier
            item_modifier += world_event.raid_item_modifier
            bad_outcome_modifier += world_event.raid_bad_outcome_modifier
            if world_event.destination_raid_modifiers is not None:
                modifier += world_event.destination_raid_modifiers.get(destination, Decimal("0"))
            world_event_title = world_event.title

        guard_effect = next(
            (effect for effect in context.active_effects if get_effect_definition(effect.effect_type).blocks_bad_raid),
            None,
        )
        return ResolvedRaidState(
            modifier=self._cap_modifier(modifier, minimum=RAID_MODIFIER_FLOOR, maximum=RAID_MODIFIER_CAP),
            reward_multiplier=destination_definition.weight_reward_modifier * trait.raid_reward_modifier,
            item_modifier=item_modifier,
            bad_outcome_modifier=bad_outcome_modifier,
            active_effects=context.active_effects,
            one_shot_effects=one_shot_effects,
            guard_effect=guard_effect,
            equipped_item=context.equipped_item,
            world_event_title=world_event_title,
        )

    async def resolve_sabotage_modifiers(self, attacker, target, *, now: datetime) -> ResolvedSabotageState:
        attacker_context = await self._build_context(attacker, now=now)
        target_context = await self._build_context(target, now=now)

        chance = Decimal("0.55")
        chance += get_trait_definition(attacker.trait).sabotage_modifier
        chance += self._mood_modifier(attacker_context.effective_mood_score, trait_code=attacker.trait) / Decimal("2")
        chance += self._action_loyalty_modifier(attacker.loyalty)

        target_defense = Decimal("0")
        if target_context.equipped_item is not None:
            item_definition = get_item_definition(target_context.equipped_item.item_code)
            target_defense += item_definition.sabotage_defense_modifier * get_trait_definition(target.trait).equipment_modifier
        for effect in target_context.active_effects:
            target_defense += get_effect_definition(effect.effect_type).sabotage_defense_modifier
        target_defense += self._resistance_loyalty_modifier(target.loyalty)
        chance -= target_defense

        world_event = self._get_world_event_definition(attacker_context.world_event_code)
        world_event_title = None
        if world_event is not None:
            chance += world_event.sabotage_modifier
            world_event_title = world_event.title

        capped = self._cap_modifier(chance, minimum=SABOTAGE_CHANCE_MIN, maximum=SABOTAGE_CHANCE_MAX)
        return ResolvedSabotageState(success_chance=float(capped), world_event_title=world_event_title)

    async def get_equipped_item(self, *, pig_id, now: datetime) -> PigItem | None:
        return await self._items.get_equipped_item(pig_id=pig_id, now=now)

    async def list_active_effects(self, *, pig_id, now: datetime) -> list[PigEffect]:
        return await self._effects.list_active_for_pig(pig_id=pig_id, now=now)

    async def _build_context(self, pig, *, now: datetime) -> _ResolvedPigContext:
        trait = get_trait_definition(pig.trait)
        active_effects = await self._effects.list_active_for_pig(pig_id=pig.id, now=now)
        equipped_item = await self._items.get_equipped_item(pig_id=pig.id, now=now)
        world_event = await self._world_events.get_active(now=now)

        effective_mood = pig.mood_score
        for effect in active_effects:
            effective_mood += get_effect_definition(effect.effect_type).mood_modifier

        inactivity_hours = hours_since(latest_activity_at(pig), now=now)
        if inactivity_hours > 24:
            effective_mood -= min(((inactivity_hours - 24) // 24 + 1) * 5, 15)

        if pig.trait == PigTrait.GLUTTON and pig.last_feed_at is not None:
            hunger_hours = hours_since(pig.last_feed_at, now=now)
            if hunger_hours > trait.hunger_penalty_step_hours > 0:
                steps = hunger_hours // trait.hunger_penalty_step_hours
                effective_mood -= min(steps * trait.hunger_penalty_per_step, 20)

        return _ResolvedPigContext(
            trait_title=trait.title,
            trait_summary=trait.summary,
            effective_mood_score=clamp_mood_score(effective_mood),
            loyalty_label=get_loyalty_label(pig.loyalty),
            active_effects=active_effects,
            equipped_item=equipped_item,
            world_event_code=world_event.event_code if world_event is not None else None,
        )

    def _mood_modifier(self, mood_score: int, *, trait_code: PigTrait) -> Decimal:
        trait = get_trait_definition(trait_code)
        modifier = Decimal(mood_score) / Decimal("100") * Decimal("0.08")
        if modifier > 0:
            modifier *= trait.positive_mood_effect_modifier
        elif modifier < 0:
            modifier *= trait.negative_mood_effect_modifier
        return modifier

    def _raid_loyalty_modifier(self, loyalty: int) -> Decimal:
        if loyalty >= 80:
            return Decimal("0.04")
        if loyalty >= 40:
            return Decimal("0")
        if loyalty >= 20:
            return Decimal("-0.05")
        return Decimal("-0.12")

    def _action_loyalty_modifier(self, loyalty: int) -> Decimal:
        if loyalty >= 80:
            return Decimal("0.03")
        if loyalty >= 40:
            return Decimal("0")
        if loyalty >= 20:
            return Decimal("-0.04")
        return Decimal("-0.08")

    def _resistance_loyalty_modifier(self, loyalty: int) -> Decimal:
        if loyalty >= 80:
            return Decimal("0.04")
        if loyalty >= 40:
            return Decimal("0")
        if loyalty >= 20:
            return Decimal("-0.01")
        return Decimal("-0.04")

    def _one_shot_effects(self, effects: list[PigEffect], *, action: str) -> list[PigEffect]:
        return [
            effect
            for effect in effects
            if get_effect_definition(effect.effect_type).consume_on_action == action
        ]

    def _to_item_view(self, item: PigItem | None) -> InventoryItemView | None:
        if item is None:
            return None
        definition = get_item_definition(item.item_code)
        return InventoryItemView(
            item_id=item.id,
            code=item.item_code,
            title=definition.title,
            summary=definition.summary,
            item_type=item.item_type,
            is_equipped=item.is_equipped,
            durability=item.durability,
            expires_at=item.expires_at,
        )

    def _to_effect_view(self, effect: PigEffect) -> ActiveEffectView:
        definition = get_effect_definition(effect.effect_type)
        summary = definition.summary
        if effect.effect_type == EFFECT_WET_NEWSPAPER_CURSE:
            remaining = int((effect.payload or {}).get("remaining_battles", 3))
            summary = f"{summary} Осталось боёв: {remaining}."
        return ActiveEffectView(
            title=definition.title,
            summary=summary,
            expires_at=effect.expires_at,
        )

    def _get_world_event_definition(self, event_code: str | None):
        if event_code is None:
            return None
        return get_world_event_definition(event_code)

    def _cap_modifier(self, value: Decimal, *, minimum: Decimal, maximum: Decimal) -> Decimal:
        return max(minimum, min(value, maximum))
