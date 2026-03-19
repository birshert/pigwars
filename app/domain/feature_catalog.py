from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from app.domain.models.pig import LoyaltyTier, MoodTier, PigItemType, PigTrait, RaidDestination
from app.domain.rules.cooldowns import ensure_utc


ZERO = Decimal("0")
ONE = Decimal("1")

ITEM_IRON_POT = "iron_pot"
ITEM_MUD_CLOAK = "mud_cloak"
ITEM_BOAR_HORSESHOES = "boar_horseshoes"
ITEM_SUSPICIOUS_FEED = "suspicious_feed"
ITEM_LUCKY_CHARM = "lucky_charm"
ITEM_STINKY_OINTMENT = "stinky_ointment"

EFFECT_FEED_SPOILED = "feed_spoiled"
EFFECT_ARENA_NERVES = "arena_nerves"
EFFECT_ROUTE_CONFUSED = "route_confused"
EFFECT_MUDDY_PANIC = "muddy_panic"
EFFECT_SABOTAGE_GUARD = "sabotage_guard"
EFFECT_RAID_BAD_LUCK_GUARD = "raid_bad_luck_guard"
EFFECT_BATTLE_FOCUS = "battle_focus"
EFFECT_GOOD_OMENS = "good_omens"

WORLD_EVENT_HEAT = "heat"
WORLD_EVENT_LARD_FEST = "lard_fest"
WORLD_EVENT_FEED_SHORTAGE = "feed_shortage"
WORLD_EVENT_RAT_NIGHT = "rat_night"
WORLD_EVENT_VET_RAID = "vet_raid"


@dataclass(frozen=True, slots=True)
class TraitDefinition:
    code: PigTrait
    title: str
    summary: str
    combat_modifier: Decimal = ZERO
    feed_modifier: Decimal = ZERO
    sabotage_modifier: Decimal = ZERO
    raid_modifier: Decimal = ZERO
    raid_reward_modifier: Decimal = ONE
    loyalty_loss_multiplier: Decimal = ONE
    equipment_modifier: Decimal = ONE
    positive_mood_effect_modifier: Decimal = ONE
    negative_mood_effect_modifier: Decimal = ONE
    negative_event_modifier: Decimal = ONE
    battle_loss_mood_delta: int = 0
    hunger_penalty_step_hours: int = 0
    hunger_penalty_per_step: int = 0


@dataclass(frozen=True, slots=True)
class ItemDefinition:
    code: str
    item_type: PigItemType
    title: str
    summary: str
    default_durability: int | None = None
    combat_modifier: Decimal = ZERO
    sabotage_defense_modifier: Decimal = ZERO
    raid_modifier: Decimal = ZERO


@dataclass(frozen=True, slots=True)
class EffectDefinition:
    code: str
    title: str
    summary: str
    combat_modifier: Decimal = ZERO
    feed_modifier: Decimal = ZERO
    raid_modifier: Decimal = ZERO
    sabotage_attack_modifier: Decimal = ZERO
    sabotage_defense_modifier: Decimal = ZERO
    mood_modifier: int = 0
    consume_on_action: str | None = None
    blocks_bad_raid: bool = False


@dataclass(frozen=True, slots=True)
class RaidDestinationDefinition:
    code: RaidDestination
    title: str
    summary: str
    good_outcome_modifier: Decimal
    bad_outcome_modifier: Decimal
    item_chance_modifier: Decimal
    weight_reward_modifier: Decimal


@dataclass(frozen=True, slots=True)
class WorldEventDefinition:
    code: str
    title: str
    description: str
    feed_modifier: Decimal = ZERO
    battle_modifier: Decimal = ZERO
    battle_reward_modifier: Decimal = ZERO
    sabotage_modifier: Decimal = ZERO
    raid_modifier: Decimal = ZERO
    raid_bad_outcome_modifier: Decimal = ZERO
    raid_item_modifier: Decimal = ZERO
    destination_raid_modifiers: dict[RaidDestination, Decimal] | None = None


TRAITS: dict[PigTrait, TraitDefinition] = {
    PigTrait.AGGRESSIVE: TraitDefinition(
        code=PigTrait.AGGRESSIVE,
        title="Агрессивная",
        summary="+10% к боевому score, но после поражения злее обычного.",
        combat_modifier=Decimal("0.10"),
        battle_loss_mood_delta=-10,
    ),
    PigTrait.GLUTTON: TraitDefinition(
        code=PigTrait.GLUTTON,
        title="Обжора",
        summary="+20% к кормлению, но без еды быстро начинает беситься.",
        feed_modifier=Decimal("0.20"),
        hunger_penalty_step_hours=6,
        hunger_penalty_per_step=4,
    ),
    PigTrait.CUNNING: TraitDefinition(
        code=PigTrait.CUNNING,
        title="Хитрая",
        summary="+15% к диверсиям, но в честной драке слегка слабее.",
        combat_modifier=Decimal("-0.05"),
        sabotage_modifier=Decimal("0.15"),
    ),
    PigTrait.STUBBORN: TraitDefinition(
        code=PigTrait.STUBBORN,
        title="Упрямая",
        summary="Медленнее теряет лояльность, но хуже выжимает награды из рейдов.",
        loyalty_loss_multiplier=Decimal("0.70"),
        raid_reward_modifier=Decimal("0.90"),
    ),
    PigTrait.LUCKY: TraitDefinition(
        code=PigTrait.LUCKY,
        title="Везучая",
        summary="Чаще вытягивает удачные рейды, но слабее раскрывает экипировку.",
        raid_modifier=Decimal("0.12"),
        equipment_modifier=Decimal("0.65"),
    ),
    PigTrait.PHLEGMATIC: TraitDefinition(
        code=PigTrait.PHLEGMATIC,
        title="Флегматичная",
        summary="Слабее реагирует на плохие события, но и от хорошего настроения ловит меньше пользы.",
        positive_mood_effect_modifier=Decimal("0.70"),
        negative_mood_effect_modifier=Decimal("0.60"),
        negative_event_modifier=Decimal("0.60"),
    ),
}

ITEMS: dict[str, ItemDefinition] = {
    ITEM_IRON_POT: ItemDefinition(
        code=ITEM_IRON_POT,
        item_type=PigItemType.EQUIPMENT,
        title="Кастрюля на голове",
        summary="Немного усиливает стойкость в бою.",
        default_durability=3,
        combat_modifier=Decimal("0.06"),
    ),
    ITEM_MUD_CLOAK: ItemDefinition(
        code=ITEM_MUD_CLOAK,
        item_type=PigItemType.EQUIPMENT,
        title="Грязевой плащ",
        summary="Часть диверсий просто соскальзывает по этой жиже.",
        default_durability=3,
        sabotage_defense_modifier=Decimal("0.18"),
    ),
    ITEM_BOAR_HORSESHOES: ItemDefinition(
        code=ITEM_BOAR_HORSESHOES,
        item_type=PigItemType.EQUIPMENT,
        title="Кабаньи подковы",
        summary="Помогают в рейдах, если свинья не врежется в канаву.",
        default_durability=3,
        raid_modifier=Decimal("0.12"),
    ),
    ITEM_SUSPICIOUS_FEED: ItemDefinition(
        code=ITEM_SUSPICIOUS_FEED,
        item_type=PigItemType.CONSUMABLE,
        title="Подозрительный комбикорм",
        summary="Даёт сильный привес, но может испортить настроение.",
    ),
    ITEM_LUCKY_CHARM: ItemDefinition(
        code=ITEM_LUCKY_CHARM,
        item_type=PigItemType.CONSUMABLE,
        title="Талисман удачи",
        summary="Один раз спасает рейд от совсем позорного исхода.",
    ),
    ITEM_STINKY_OINTMENT: ItemDefinition(
        code=ITEM_STINKY_OINTMENT,
        item_type=PigItemType.CONSUMABLE,
        title="Вонючая мазь",
        summary="На несколько часов снижает шанс чужих диверсий.",
    ),
}

EFFECTS: dict[str, EffectDefinition] = {
    EFFECT_FEED_SPOILED: EffectDefinition(
        code=EFFECT_FEED_SPOILED,
        title="Испорченный корм",
        summary="Следующее кормление проходит заметно хуже.",
        feed_modifier=Decimal("-0.35"),
        consume_on_action="feed",
    ),
    EFFECT_ARENA_NERVES: EffectDefinition(
        code=EFFECT_ARENA_NERVES,
        title="Нервы перед ареной",
        summary="Следующий бой начинается на дрожащих копытах.",
        combat_modifier=Decimal("-0.10"),
        consume_on_action="battle",
    ),
    EFFECT_ROUTE_CONFUSED: EffectDefinition(
        code=EFFECT_ROUTE_CONFUSED,
        title="Сбитый маршрут",
        summary="Следующий рейд проходит через особенно тупой крюк.",
        raid_modifier=Decimal("-0.12"),
        consume_on_action="raid",
    ),
    EFFECT_MUDDY_PANIC: EffectDefinition(
        code=EFFECT_MUDDY_PANIC,
        title="Грязная паника",
        summary="Свинья несколько часов шарахается от каждого шороха.",
        mood_modifier=-15,
    ),
    EFFECT_SABOTAGE_GUARD: EffectDefinition(
        code=EFFECT_SABOTAGE_GUARD,
        title="Вонючая защита",
        summary="Чужим диверсантам противно подходить слишком близко.",
        sabotage_defense_modifier=Decimal("0.25"),
    ),
    EFFECT_RAID_BAD_LUCK_GUARD: EffectDefinition(
        code=EFFECT_RAID_BAD_LUCK_GUARD,
        title="Талисман удачи",
        summary="Один раз вытаскивает рейд из совсем плохого исхода.",
        blocks_bad_raid=True,
    ),
    EFFECT_BATTLE_FOCUS: EffectDefinition(
        code=EFFECT_BATTLE_FOCUS,
        title="Боевой раж",
        summary="Следующий бой получает приятный бонус.",
        combat_modifier=Decimal("0.08"),
        consume_on_action="battle",
    ),
    EFFECT_GOOD_OMENS: EffectDefinition(
        code=EFFECT_GOOD_OMENS,
        title="Добрые приметы",
        summary="Следующий рейд проходит чуть удачнее.",
        raid_modifier=Decimal("0.08"),
        consume_on_action="raid",
    ),
}

RAID_DESTINATIONS: dict[RaidDestination, RaidDestinationDefinition] = {
    RaidDestination.DUMP: RaidDestinationDefinition(
        code=RaidDestination.DUMP,
        title="Свалка",
        summary="Много странного лута, много шансов вернуться недовольной.",
        good_outcome_modifier=Decimal("-0.04"),
        bad_outcome_modifier=Decimal("0.06"),
        item_chance_modifier=Decimal("0.18"),
        weight_reward_modifier=Decimal("0.90"),
    ),
    RaidDestination.MARKET: RaidDestinationDefinition(
        code=RaidDestination.MARKET,
        title="Рынок",
        summary="Самый ровный вариант: средний риск и стабильные плюшки.",
        good_outcome_modifier=ZERO,
        bad_outcome_modifier=ZERO,
        item_chance_modifier=Decimal("0.08"),
        weight_reward_modifier=Decimal("1.10"),
    ),
    RaidDestination.WOODS: RaidDestinationDefinition(
        code=RaidDestination.WOODS,
        title="Лесополоса",
        summary="Там либо находят редкую пользу, либо вляпываются красиво.",
        good_outcome_modifier=Decimal("0.05"),
        bad_outcome_modifier=Decimal("0.08"),
        item_chance_modifier=Decimal("0.04"),
        weight_reward_modifier=Decimal("1.00"),
    ),
}

WORLD_EVENTS: dict[str, WorldEventDefinition] = {
    WORLD_EVENT_HEAT: WorldEventDefinition(
        code=WORLD_EVENT_HEAT,
        title="Жара",
        description="Корм усыхает быстрее, зато в рейдах проще нарыть грязь и воду.",
        feed_modifier=Decimal("-0.15"),
        raid_modifier=Decimal("0.05"),
        destination_raid_modifiers={
            RaidDestination.DUMP: Decimal("0.05"),
            RaidDestination.MARKET: Decimal("0.03"),
            RaidDestination.WOODS: Decimal("0.03"),
        },
    ),
    WORLD_EVENT_LARD_FEST: WorldEventDefinition(
        code=WORLD_EVENT_LARD_FEST,
        title="Праздник сала",
        description="Арена взвинчена, победители жиреют быстрее, а диверсанты наглеют.",
        battle_reward_modifier=Decimal("0.15"),
        sabotage_modifier=Decimal("0.05"),
    ),
    WORLD_EVENT_FEED_SHORTAGE: WorldEventDefinition(
        code=WORLD_EVENT_FEED_SHORTAGE,
        title="Дефицит корма",
        description="Кормление просело, зато всё добытое в рейдах ценится заметно выше.",
        feed_modifier=Decimal("-0.20"),
        raid_item_modifier=Decimal("0.10"),
    ),
    WORLD_EVENT_RAT_NIGHT: WorldEventDefinition(
        code=WORLD_EVENT_RAT_NIGHT,
        title="Ночь крыс",
        description="На свалках полно странностей, а диверсии проходят подозрительно часто.",
        sabotage_modifier=Decimal("0.10"),
        raid_item_modifier=Decimal("0.08"),
        destination_raid_modifiers={RaidDestination.DUMP: Decimal("0.08")},
    ),
    WORLD_EVENT_VET_RAID: WorldEventDefinition(
        code=WORLD_EVENT_VET_RAID,
        title="Ветеринарный рейд",
        description="Грязные трюки в моде хуже работают, а рейды реже заканчиваются позором.",
        sabotage_modifier=Decimal("-0.12"),
        raid_bad_outcome_modifier=Decimal("-0.10"),
    ),
}


def random_trait(rng: random.Random | None = None) -> PigTrait:
    resolved_rng = rng or random.Random()
    return resolved_rng.choice(list(PigTrait))


def get_trait_definition(trait: PigTrait) -> TraitDefinition:
    return TRAITS[trait]


def get_item_definition(item_code: str) -> ItemDefinition:
    return ITEMS[item_code]


def get_effect_definition(effect_code: str) -> EffectDefinition:
    return EFFECTS[effect_code]


def get_raid_destination(destination: RaidDestination) -> RaidDestinationDefinition:
    return RAID_DESTINATIONS[destination]


def get_world_event_definition(event_code: str) -> WorldEventDefinition:
    return WORLD_EVENTS[event_code]


def pick_next_world_event(*, rng: random.Random, previous_code: str | None = None) -> WorldEventDefinition:
    available = [definition for definition in WORLD_EVENTS.values() if definition.code != previous_code]
    return rng.choice(available)


def clamp_mood_score(value: int) -> int:
    return max(-100, min(100, value))


def clamp_loyalty(value: int) -> int:
    return max(0, min(100, value))


def get_mood_tier(mood_score: int) -> MoodTier:
    if mood_score >= 51:
        return MoodTier.ECSTATIC
    if mood_score >= 11:
        return MoodTier.HAPPY
    if mood_score >= -10:
        return MoodTier.NEUTRAL
    if mood_score >= -50:
        return MoodTier.UPSET
    return MoodTier.FURIOUS


def get_mood_label(mood_score: int) -> str:
    tier = get_mood_tier(mood_score)
    return {
        MoodTier.ECSTATIC: "в экстазе",
        MoodTier.HAPPY: "довольна",
        MoodTier.NEUTRAL: "нейтральна",
        MoodTier.UPSET: "недовольна",
        MoodTier.FURIOUS: "в ярости",
    }[tier]


def get_loyalty_tier(loyalty: int) -> LoyaltyTier:
    if loyalty >= 80:
        return LoyaltyTier.DEVOTED
    if loyalty >= 40:
        return LoyaltyTier.STEADY
    if loyalty >= 20:
        return LoyaltyTier.SHAKY
    return LoyaltyTier.MUTINOUS


def get_loyalty_label(loyalty: int) -> str:
    tier = get_loyalty_tier(loyalty)
    return {
        LoyaltyTier.DEVOTED: "предана",
        LoyaltyTier.STEADY: "держится нормально",
        LoyaltyTier.SHAKY: "косится с подозрением",
        LoyaltyTier.MUTINOUS: "почти готова бунтовать",
    }[tier]


def hours_since(moment: datetime | None, *, now: datetime) -> int:
    if moment is None:
        return 0
    normalized_moment = ensure_utc(moment) or moment
    normalized_now = ensure_utc(now) or now
    return max(int((normalized_now - normalized_moment).total_seconds() // 3600), 0)
