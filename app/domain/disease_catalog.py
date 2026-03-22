from __future__ import annotations

import random
from dataclasses import dataclass

from app.domain.feature_catalog import (
    EFFECT_DISEASE_BARN_ITCH,
    EFFECT_DISEASE_FEED_COLD,
    EFFECT_DISEASE_MUD_FEVER,
    EFFECT_DISEASE_QUARANTINE_SCREAM,
)


DISEASE_FEED_COLD = "feed_cold"
DISEASE_MUD_FEVER = "mud_fever"
DISEASE_BARN_ITCH = "barn_itch"
DISEASE_QUARANTINE_SCREAM = "quarantine_scream"


@dataclass(frozen=True, slots=True)
class DiseaseDefinition:
    code: str
    title: str
    summary: str
    effect_type: str | None
    mood_delta: int
    loyalty_delta: int
    duration_hours: int | None
    quarantine_until_end_of_day: bool = False
    fatal_outcome: bool = False
    fatal_message_templates: tuple[str, ...] = ()
    selection_weight: float = 1.0
    tone_hint: str = "иронично-жалостливый"


DISEASES: dict[str, DiseaseDefinition] = {
    DISEASE_FEED_COLD: DiseaseDefinition(
        code=DISEASE_FEED_COLD,
        title="Комбикормный насморк",
        summary="Лёгкая, но унизительная простуда с плохим аппетитом.",
        effect_type=EFFECT_DISEASE_FEED_COLD,
        mood_delta=-5,
        loyalty_delta=-1,
        duration_hours=8,
        selection_weight=1.2,
        tone_hint="с лёгкой жалостью и деревенской насмешкой",
    ),
    DISEASE_MUD_FEVER: DiseaseDefinition(
        code=DISEASE_MUD_FEVER,
        title="Грязевая лихорадка",
        summary="Свинью лихорадит, и любые геройства выглядят сомнительно.",
        effect_type=EFFECT_DISEASE_MUD_FEVER,
        mood_delta=-10,
        loyalty_delta=-2,
        duration_hours=10,
        selection_weight=1.0,
        tone_hint="театрально и мрачно-комично",
    ),
    DISEASE_BARN_ITCH: DiseaseDefinition(
        code=DISEASE_BARN_ITCH,
        title="Амбарная чесотка",
        summary="Досадная зараза, которая делает свинью нервной и дёрганой.",
        effect_type=EFFECT_DISEASE_BARN_ITCH,
        mood_delta=-8,
        loyalty_delta=-2,
        duration_hours=12,
        selection_weight=0.9,
        tone_hint="едко, но без перегиба",
    ),
    DISEASE_QUARANTINE_SCREAM: DiseaseDefinition(
        code=DISEASE_QUARANTINE_SCREAM,
        title="Карантинный визгец",
        summary="Тяжёлый случай: свинью лучше изолировать до конца игрового дня.",
        effect_type=EFFECT_DISEASE_QUARANTINE_SCREAM,
        mood_delta=-14,
        loyalty_delta=-4,
        duration_hours=None,
        quarantine_until_end_of_day=True,
        selection_weight=0.45,
        tone_hint="сдержанно-драматично, будто в хлеву объявили ЧП",
    ),
    "hay_hemorrhoids": DiseaseDefinition(
        code="hay_hemorrhoids",
        title="Сенной геморрой",
        summary="Фатальная напасть с очень позорным финалом.",
        effect_type=None,
        mood_delta=0,
        loyalty_delta=0,
        duration_hours=None,
        fatal_outcome=True,
        fatal_message_templates=(
            "{pig_name} умерла от геморроя. Хлев молчит, потому что даже он в ахуе.",
            "{pig_name} сгубил сенной геморрой: позорная смерть, жирный финал и ноль уважения.",
            "У {pig_name} случился терминальный сенной геморрой. Медкорм списал её как безнадёжный случай.",
        ),
        selection_weight=0.45,
        tone_hint="злобно-насмешливо и без сантиментов",
    ),
    "lard_collapse": DiseaseDefinition(
        code="lard_collapse",
        title="Сальный завал",
        summary="Организм внезапно решил, что дальше тащить всё это сало не будет.",
        effect_type=None,
        mood_delta=0,
        loyalty_delta=0,
        duration_hours=None,
        fatal_outcome=True,
        fatal_message_templates=(
            "{pig_name} накрыл сальный завал. По итогам её просто забили на сало.",
            "{pig_name} не пережила сальный завал. Комиссия написала: «забили на сало, хоронить без фанфар».",
            "Сальный завал добил {pig_name}. В ведомости хлева стоит лаконичное: «ушла в мясной архив».",
        ),
        selection_weight=0.40,
        tone_hint="жестоко-иронично, как сельский некролог",
    ),
    "manure_stroke": DiseaseDefinition(
        code="manure_stroke",
        title="Навозный инсульт",
        summary="Свинью срубает так быстро, что даже мухи не успевают занять места.",
        effect_type=None,
        mood_delta=0,
        loyalty_delta=0,
        duration_hours=None,
        fatal_outcome=True,
        fatal_message_templates=(
            "{pig_name} получила навозный инсульт и отбыла в вечный хлев без апелляции.",
            "Навозный инсульт уложил {pig_name} быстрее, чем хозяин успел соврать про хороший уход.",
            "{pig_name} не вывезла навозный инсульт. Санитары только развели копытами.",
        ),
        selection_weight=0.42,
        tone_hint="мрачно-комично и беспощадно",
    ),
    "crackling_fever": DiseaseDefinition(
        code="crackling_fever",
        title="Шкварочная горячка",
        summary="Температура подскакивает до состояния «уже не спасти, только обсудить».",
        effect_type=None,
        mood_delta=0,
        loyalty_delta=0,
        duration_hours=None,
        fatal_outcome=True,
        fatal_message_templates=(
            "{pig_name} сгорела на шкварочной горячке. Финал пахнет жареным и юридически мутным.",
            "Шкварочная горячка довела {pig_name} до состояния «поминальная сковорода готова».",
            "{pig_name} не выдержала шкварочной горячки. Хлев уже спорит, кто виноват, но поздно.",
        ),
        selection_weight=0.38,
        tone_hint="едко и по-свински похоронно",
    ),
    "hoof_thrombosis": DiseaseDefinition(
        code="hoof_thrombosis",
        title="Копытный тромбоз",
        summary="Сосуды сказали «хватит», и комедия резко закончилась.",
        effect_type=None,
        mood_delta=0,
        loyalty_delta=0,
        duration_hours=None,
        fatal_outcome=True,
        fatal_message_templates=(
            "{pig_name} скосил копытный тромбоз. Даже ветеринар сделал вид, что у него срочный обед.",
            "Копытный тромбоз поставил точку в биографии {pig_name}. Толстую, жирную и окончательную.",
            "{pig_name} схлопнулась от копытного тромбоза. На мемориальной табличке будет один сплошной стыд.",
        ),
        selection_weight=0.35,
        tone_hint="сухо-жестоко, как отчёт о потере актива",
    ),
    "smoked_plague": DiseaseDefinition(
        code="smoked_plague",
        title="Коптильная чума",
        summary="Очень плохой диагноз для свиньи, которая уже выглядит подозрительно аппетитно.",
        effect_type=None,
        mood_delta=0,
        loyalty_delta=0,
        duration_hours=None,
        fatal_outcome=True,
        fatal_message_templates=(
            "{pig_name} догнала коптильная чума. Хлев уже делит, кому достанется моральная ответственность.",
            "Коптильная чума унесла {pig_name}. Формулировка в акте: «слишком вкусно выглядела, извините».",
            "{pig_name} проиграла коптильной чуме и отправилась туда, где нет ни корыта, ни пощады.",
        ),
        selection_weight=0.33,
        tone_hint="язвительно и похоронно-мемно",
    ),
}


DISEASE_EFFECT_TYPES = tuple(
    definition.effect_type
    for definition in DISEASES.values()
    if definition.effect_type is not None
)


def get_disease_definition(code: str) -> DiseaseDefinition:
    return DISEASES[code]


def pick_disease_definition(*, rng: random.Random) -> DiseaseDefinition:
    definitions = list(DISEASES.values())
    weights = [definition.selection_weight for definition in definitions]
    return rng.choices(definitions, weights=weights, k=1)[0]
