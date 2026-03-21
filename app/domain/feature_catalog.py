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
ITEM_WET_NEWSPAPER = "wet_newspaper"

EFFECT_FEED_SPOILED = "feed_spoiled"
EFFECT_ARENA_NERVES = "arena_nerves"
EFFECT_ROUTE_CONFUSED = "route_confused"
EFFECT_MUDDY_PANIC = "muddy_panic"
EFFECT_SABOTAGE_GUARD = "sabotage_guard"
EFFECT_RAID_BAD_LUCK_GUARD = "raid_bad_luck_guard"
EFFECT_BATTLE_FOCUS = "battle_focus"
EFFECT_GOOD_OMENS = "good_omens"
EFFECT_HOROSCOPE_BOAR_LION = "horoscope_boar_lion"
EFFECT_HOROSCOPE_SWINE_SCALES = "horoscope_swine_scales"
EFFECT_HOROSCOPE_MUD_FISH = "horoscope_mud_fish"
EFFECT_HOROSCOPE_BARN_ARCHER = "horoscope_barn_archer"
EFFECT_WHEEL_PUDDLE = "wheel_puddle"
EFFECT_WHEEL_HAY = "wheel_hay"
EFFECT_WHEEL_STICKY = "wheel_sticky"
EFFECT_WHEEL_FAIR = "wheel_fair"
EFFECT_WHEEL_APPLAUSE = "wheel_applause"
EFFECT_WHEEL_CABBAGE_OMEN = "wheel_cabbage_omen"
EFFECT_WET_NEWSPAPER_CURSE = "wet_newspaper_curse"
EFFECT_DISEASE_FEED_COLD = "disease_feed_cold"
EFFECT_DISEASE_MUD_FEVER = "disease_mud_fever"
EFFECT_DISEASE_BARN_ITCH = "disease_barn_itch"
EFFECT_DISEASE_QUARANTINE_SCREAM = "disease_quarantine_scream"

WORLD_EVENT_HEAT = "heat"
WORLD_EVENT_LARD_FEST = "lard_fest"
WORLD_EVENT_FEED_SHORTAGE = "feed_shortage"
WORLD_EVENT_RAT_NIGHT = "rat_night"
WORLD_EVENT_VET_RAID = "vet_raid"
WORLD_EVENT_DIVINE_OINK = "divine_oink"


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
    battle_flavor: str | None = None
    raid_flavor: str | None = None


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
    selection_weight: float = 1.0
    duration_hours: int | None = None


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
    ITEM_WET_NEWSPAPER: ItemDefinition(
        code=ITEM_WET_NEWSPAPER,
        item_type=PigItemType.CONSUMABLE,
        title="Мокрая газета",
        summary="Ответом на сообщение цели можно наслать на чужую свинью сырой газетный позор.",
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
    EFFECT_HOROSCOPE_BOAR_LION: EffectDefinition(
        code=EFFECT_HOROSCOPE_BOAR_LION,
        title="Гороскоп дня: Кабан-Лев",
        summary="Сегодня свинья лезет в драку смелее обычного, но в тонких делах чересчур самоуверенна.",
        combat_modifier=Decimal("0.08"),
        sabotage_defense_modifier=Decimal("-0.05"),
        battle_flavor="Сегодня у {pig_name} день Кабана-Льва: она влетает в арену как в амбар без двери.",
    ),
    EFFECT_HOROSCOPE_SWINE_SCALES: EffectDefinition(
        code=EFFECT_HOROSCOPE_SWINE_SCALES,
        title="Гороскоп дня: Свин-Весы",
        summary="Чуть лучше тянет фарт в вылазках, но в драке слишком любит сомневаться у самого корыта.",
        combat_modifier=Decimal("-0.04"),
        raid_modifier=Decimal("0.08"),
        raid_flavor="{pig_name} весь день под знаком Свина-Весов и подозрительно нюхает дорогу на удачу.",
    ),
    EFFECT_HOROSCOPE_MUD_FISH: EffectDefinition(
        code=EFFECT_HOROSCOPE_MUD_FISH,
        title="Гороскоп дня: Поросенок-Рыбы",
        summary="Пятачок улавливает деревенские знаки лучше обычного и реже влезает в особенно тупые неприятности.",
        raid_modifier=Decimal("0.04"),
        sabotage_defense_modifier=Decimal("0.06"),
        mood_modifier=4,
        raid_flavor="{pig_name} сегодня как Поросенок-Рыбы: скользкая, чуткая и слишком мистическая для канавы.",
    ),
    EFFECT_HOROSCOPE_BARN_ARCHER: EffectDefinition(
        code=EFFECT_HOROSCOPE_BARN_ARCHER,
        title="Гороскоп дня: Кабан-Стрелец",
        summary="Свинья охотнее устраивает пакости и дерзит судьбе, но чуть хуже держит строй в долгих делах.",
        combat_modifier=Decimal("0.05"),
        sabotage_attack_modifier=Decimal("0.08"),
        raid_modifier=Decimal("-0.04"),
        battle_flavor="{pig_name} идёт под знаком Кабана-Стрельца и выглядит так, будто уже придумала лишнюю пакость.",
    ),
    EFFECT_WHEEL_PUDDLE: EffectDefinition(
        code=EFFECT_WHEEL_PUDDLE,
        title="Позор дня: упала в лужу",
        summary="Вид сырой, важность потеряна, боевой запал слегка размок.",
        combat_modifier=Decimal("-0.05"),
        battle_flavor="{pig_name} до сих пор хлюпает после позорного падения в лужу.",
    ),
    EFFECT_WHEEL_HAY: EffectDefinition(
        code=EFFECT_WHEEL_HAY,
        title="Позор дня: воняет сеном",
        summary="От свиньи тянет сеновалом так уверенно, что даже удача отходит на шаг.",
        raid_modifier=Decimal("-0.05"),
        raid_flavor="{pig_name} несёт сеном на полдеревни, и это почему-то влияет на фарт.",
    ),
    EFFECT_WHEEL_STICKY: EffectDefinition(
        code=EFFECT_WHEEL_STICKY,
        title="Позор дня: подозрительно липкая",
        summary="Никто не хочет подходить слишком близко, включая саму удачу.",
        sabotage_defense_modifier=Decimal("-0.05"),
        mood_modifier=-4,
        battle_flavor="{pig_name} выглядит подозрительно липкой, и это заметно сбивает ритм арены.",
    ),
    EFFECT_WHEEL_FAIR: EffectDefinition(
        code=EFFECT_WHEEL_FAIR,
        title="Позор дня: слишком уверенно шла на ярмарку",
        summary="Самоуверенность встретилась с канавой и теперь слегка мешает и в бою, и в дороге.",
        combat_modifier=Decimal("-0.03"),
        raid_modifier=Decimal("-0.03"),
        raid_flavor="{pig_name} всё ещё держится так, будто не опозорилась по пути на ярмарку.",
    ),
    EFFECT_WHEEL_APPLAUSE: EffectDefinition(
        code=EFFECT_WHEEL_APPLAUSE,
        title="Колесо: ярмарочные аплодисменты",
        summary="Редкий случай: деревня сочла свинью красавицей, и это бодрит до конца дня.",
        combat_modifier=Decimal("0.05"),
        battle_flavor="{pig_name} сегодня идёт под ярмарочные аплодисменты и сама в это почти поверила.",
    ),
    EFFECT_WHEEL_CABBAGE_OMEN: EffectDefinition(
        code=EFFECT_WHEEL_CABBAGE_OMEN,
        title="Колесо: капустная примета",
        summary="Колесо выдало приятный знак, и свинья увереннее рыщет по вылазкам.",
        raid_modifier=Decimal("0.05"),
        raid_flavor="{pig_name} поймала капустную примету и теперь хрюкает на удачу.",
    ),
    EFFECT_WET_NEWSPAPER_CURSE: EffectDefinition(
        code=EFFECT_WET_NEWSPAPER_CURSE,
        title="Проклятие мокрой газеты",
        summary="Пахнет сырой редакцией и стыдом, пока не переживёт три боя или не высохнет время.",
        combat_modifier=Decimal("-0.05"),
        raid_modifier=Decimal("-0.05"),
        battle_flavor="{pig_name} явилась под проклятием мокрой газеты и тянет за собой запах сырой типографии.",
        raid_flavor="{pig_name} несёт с собой влажный газетный стыд, и дорога от этого кажется ещё тупее.",
    ),
    EFFECT_DISEASE_FEED_COLD: EffectDefinition(
        code=EFFECT_DISEASE_FEED_COLD,
        title="Комбикормный насморк",
        summary="Свинья сипит, фыркает и ест заметно хуже обычного.",
        feed_modifier=Decimal("-0.18"),
        combat_modifier=Decimal("-0.04"),
        mood_modifier=-6,
        battle_flavor="{pig_name} хлюпает пятачком так жалобно, будто арену ей прописал деревенский терапевт.",
        raid_flavor="{pig_name} тащит в рейд комбикормный насморк и очень спорный запас бодрости.",
    ),
    EFFECT_DISEASE_MUD_FEVER: EffectDefinition(
        code=EFFECT_DISEASE_MUD_FEVER,
        title="Грязевая лихорадка",
        summary="Лихорадит, сушит и мешает и драке, и вылазкам.",
        combat_modifier=Decimal("-0.08"),
        raid_modifier=Decimal("-0.10"),
        mood_modifier=-10,
        battle_flavor="{pig_name} вышла с грязевой лихорадкой и видом свиньи, которую лично прокляла каждая лужа.",
        raid_flavor="{pig_name} ещё горит от грязевой лихорадки, поэтому дорога выглядит особенно злой.",
    ),
    EFFECT_DISEASE_BARN_ITCH: EffectDefinition(
        code=EFFECT_DISEASE_BARN_ITCH,
        title="Амбарная чесотка",
        summary="Чешется, злится и теряет остатки спортивного достоинства.",
        combat_modifier=Decimal("-0.10"),
        raid_modifier=Decimal("-0.06"),
        mood_modifier=-8,
        battle_flavor="{pig_name} дёргается от амбарной чесотки так, будто сражается сразу и с ареной, и с собой.",
        raid_flavor="{pig_name} несёт на себе амбарную чесотку и крайне неубедительную походку победителя.",
    ),
    EFFECT_DISEASE_QUARANTINE_SCREAM: EffectDefinition(
        code=EFFECT_DISEASE_QUARANTINE_SCREAM,
        title="Карантинный визгец",
        summary="Случай настолько тяжёлый, что хлев временно запретил подвиги и вывел свинью из игры.",
        mood_modifier=-14,
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
    RaidDestination.MILL: RaidDestinationDefinition(
        code=RaidDestination.MILL,
        title="Старая мельница",
        summary="Там полно зерна, муки и поводов вернуться белой от позора или довольства.",
        good_outcome_modifier=Decimal("0.04"),
        bad_outcome_modifier=Decimal("0.03"),
        item_chance_modifier=Decimal("0.10"),
        weight_reward_modifier=Decimal("1.18"),
    ),
    RaidDestination.PIER: RaidDestinationDefinition(
        code=RaidDestination.PIER,
        title="Речная пристань",
        summary="Ящики, рыба и скользкие доски. Лут бывает жирный, но дорога любит подставлять копыто.",
        good_outcome_modifier=Decimal("0.01"),
        bad_outcome_modifier=Decimal("0.10"),
        item_chance_modifier=Decimal("0.14"),
        weight_reward_modifier=Decimal("0.98"),
    ),
    RaidDestination.MANOR: RaidDestinationDefinition(
        code=RaidDestination.MANOR,
        title="Барская усадьба",
        summary="Чужой корм, тяжёлые ворота и большие шансы принести домой что-то неприлично ценное.",
        good_outcome_modifier=Decimal("-0.02"),
        bad_outcome_modifier=Decimal("0.12"),
        item_chance_modifier=Decimal("0.16"),
        weight_reward_modifier=Decimal("1.25"),
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
    WORLD_EVENT_DIVINE_OINK: WorldEventDefinition(
        code=WORLD_EVENT_DIVINE_OINK,
        title="Божественный хрюк",
        description="Великая Свинья прорезала небо священным визгом: победы жиреют быстрее, а рейды тянут на особенно странный лут.",
        battle_reward_modifier=Decimal("0.20"),
        raid_item_modifier=Decimal("0.15"),
        selection_weight=0.12,
        duration_hours=2,
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
    weights = [definition.selection_weight for definition in available]
    return rng.choices(available, weights=weights, k=1)[0]


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
