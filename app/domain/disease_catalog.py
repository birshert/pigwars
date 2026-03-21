from __future__ import annotations

import random
from dataclasses import dataclass
from decimal import Decimal

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
    effect_type: str
    weight_loss_min: Decimal
    weight_loss_max: Decimal
    mood_delta: int
    loyalty_delta: int
    duration_hours: int | None
    quarantine_until_end_of_day: bool = False
    selection_weight: float = 1.0
    tone_hint: str = "иронично-жалостливый"


DISEASES: dict[str, DiseaseDefinition] = {
    DISEASE_FEED_COLD: DiseaseDefinition(
        code=DISEASE_FEED_COLD,
        title="Комбикормный насморк",
        summary="Лёгкая, но унизительная простуда с плохим аппетитом.",
        effect_type=EFFECT_DISEASE_FEED_COLD,
        weight_loss_min=Decimal("0.24"),
        weight_loss_max=Decimal("0.52"),
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
        weight_loss_min=Decimal("0.42"),
        weight_loss_max=Decimal("0.92"),
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
        weight_loss_min=Decimal("0.30"),
        weight_loss_max=Decimal("0.72"),
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
        weight_loss_min=Decimal("0.80"),
        weight_loss_max=Decimal("1.45"),
        mood_delta=-14,
        loyalty_delta=-4,
        duration_hours=None,
        quarantine_until_end_of_day=True,
        selection_weight=0.45,
        tone_hint="сдержанно-драматично, будто в хлеву объявили ЧП",
    ),
}


DISEASE_EFFECT_TYPES = tuple(definition.effect_type for definition in DISEASES.values())


def get_disease_definition(code: str) -> DiseaseDefinition:
    return DISEASES[code]


def pick_disease_definition(*, rng: random.Random) -> DiseaseDefinition:
    definitions = list(DISEASES.values())
    weights = [definition.selection_weight for definition in definitions]
    return rng.choices(definitions, weights=weights, k=1)[0]
