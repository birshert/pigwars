from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(slots=True)
class DiseaseNarrativeContext:
    group_id: int
    pig_name: str
    disease_title: str
    disease_summary: str
    fatal_outcome: bool
    death_message: str | None
    weight_loss: Decimal
    current_weight: Decimal
    mood_label: str
    loyalty_label: str
    effect_expires_at: datetime
    quarantine_until: datetime | None
    tone_hint: str
    slot_kind: str

    def to_payload(self) -> dict[str, object]:
        return {
            "group_id": self.group_id,
            "pig_name": self.pig_name,
            "disease_title": self.disease_title,
            "disease_summary": self.disease_summary,
            "fatal_outcome": self.fatal_outcome,
            "death_message": self.death_message,
            "weight_loss_kg": f"{self.weight_loss:.2f}",
            "current_weight_kg": f"{self.current_weight:.2f}",
            "mood_label": self.mood_label,
            "loyalty_label": self.loyalty_label,
            "effect_expires_at": self.effect_expires_at.isoformat(),
            "quarantine_until": self.quarantine_until.isoformat() if self.quarantine_until is not None else None,
            "tone_hint": self.tone_hint,
            "slot_kind": self.slot_kind,
        }


@dataclass(slots=True)
class DiseaseNarrativeResult:
    text: str
    llm_model: str | None
    used_llm: bool


@dataclass(slots=True)
class DiseaseAnnouncement:
    roll_id: int
    telegram_group_id: int
    text: str
    group_title: str | None = None
    owner_telegram_user_id: int | None = None
    owner_mention_label: str | None = None
