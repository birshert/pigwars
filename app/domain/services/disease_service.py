from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db.repositories.disease_repo import GroupDiseaseRollRepository
from app.db.repositories.effect_repo import PigEffectRepository
from app.db.repositories.event_repo import PigEventRepository
from app.db.repositories.group_repo import GroupRepository
from app.db.repositories.pig_repo import PigRepository
from app.db.repositories.user_repo import UserRepository
from app.domain.disease_catalog import DISEASE_EFFECT_TYPES, DiseaseDefinition, pick_disease_definition
from app.domain.feature_catalog import get_loyalty_label, get_mood_label
from app.domain.models.disease import DiseaseRollStatus
from app.domain.models.pig import PigStatus
from app.domain.rules.combat import MIN_PIG_WEIGHT, quantize_weight
from app.domain.rules.disease_schedule import DiseaseSlot, get_current_disease_slot
from app.domain.rules.pig_state import apply_loyalty_change, apply_mood_change
from app.domain.rules.timezones import end_of_game_day
from app.domain.services.disease_narrative_service import DiseaseNarrativeService
from app.schemas.disease import DiseaseAnnouncement, DiseaseNarrativeContext


@dataclass(slots=True)
class _PendingAnnouncement:
    roll: object
    telegram_group_id: int
    group_title: str
    owner_telegram_user_id: int | None
    owner_mention_label: str | None
    context: DiseaseNarrativeContext


class DiseaseService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        settings: Settings,
        rng: random.Random,
    ) -> None:
        self._session = session
        self._settings = settings
        self._rng = rng
        self._groups = GroupRepository(session)
        self._pigs = PigRepository(session)
        self._users = UserRepository(session)
        self._effects = PigEffectRepository(session)
        self._events = PigEventRepository(session)
        self._rolls = GroupDiseaseRollRepository(session)
        self._narratives = DiseaseNarrativeService(settings)

    async def expire_quarantines(self, *, now: datetime) -> int:
        async with self._session.begin():
            expired = await self._pigs.expire_quarantined_pigs(now=now)
            for pig in expired:
                await self._events.create(
                    pig_id=pig.id,
                    group_id=pig.group_id,
                    event_type="disease_quarantine_ended",
                    payload={"ended_at": now.isoformat()},
                )
        return len(expired)

    async def process_current_slot(self, *, now: datetime) -> list[DiseaseAnnouncement]:
        if not self._settings.disease_enabled:
            return []

        slot = get_current_disease_slot(
            now,
            interval_minutes=self._settings.disease_interval_minutes,
            day_start_hour_msk=self._settings.disease_day_start_hour_msk,
            day_end_hour_msk=self._settings.disease_day_end_hour_msk,
        )
        if slot is None:
            return []

        pending: list[_PendingAnnouncement] = []
        async with self._session.begin():
            group_ids = await self._pigs.list_group_ids_with_pigs()
            for group_id in group_ids:
                existing = await self._rolls.get_by_group_slot(group_id=group_id, scheduled_for=slot.scheduled_for)
                if existing is not None:
                    continue
                prepared = await self._prepare_group_slot(group_id=group_id, slot=slot, now=now)
                if prepared is not None:
                    pending.append(prepared)

        return [await self._finalize_pending(item) for item in pending]

    async def trigger_manual_disease(
        self,
        *,
        now: datetime,
        group_id: int | None = None,
    ) -> DiseaseAnnouncement | None:
        pending: _PendingAnnouncement | None = None
        async with self._session.begin():
            if group_id is not None:
                pending = await self._prepare_manual_group(group_id=group_id, now=now)
            else:
                group_ids = await self._pigs.list_group_ids_with_pigs()
                self._rng.shuffle(group_ids)
                for candidate_group_id in group_ids:
                    pending = await self._prepare_manual_group(group_id=candidate_group_id, now=now)
                    if pending is not None:
                        break

        if pending is None:
            return None
        return await self._finalize_pending(pending)

    async def _prepare_group_slot(
        self,
        *,
        group_id: int,
        slot: DiseaseSlot,
        now: datetime,
    ) -> _PendingAnnouncement | None:
        chance = (
            self._settings.disease_day_chance
            if slot.slot_kind == "day"
            else self._settings.disease_night_chance
        )
        if self._rng.random() > chance:
            await self._rolls.create(
                group_id=group_id,
                scheduled_for=slot.scheduled_for,
                status=DiseaseRollStatus.SKIPPED,
                payload={
                    "reason": "chance_missed",
                    "slot_kind": slot.slot_kind,
                    "chance": chance,
                },
            )
            return None

        pig = await self._pick_candidate(group_id=group_id, now=now)
        if pig is None:
            await self._rolls.create(
                group_id=group_id,
                scheduled_for=slot.scheduled_for,
                status=DiseaseRollStatus.SKIPPED,
                payload={"reason": "no_candidates", "slot_kind": slot.slot_kind},
            )
            return None

        group = await self._groups.get_by_id(group_id)
        if group is None:
            await self._rolls.create(
                group_id=group_id,
                scheduled_for=slot.scheduled_for,
                status=DiseaseRollStatus.SKIPPED,
                payload={"reason": "group_not_found", "slot_kind": slot.slot_kind},
            )
            return None

        return await self._infect_pig(
            pig=pig,
            group=group,
            scheduled_for=slot.scheduled_for,
            slot_kind=slot.slot_kind,
            now=now,
        )

    async def _prepare_manual_group(
        self,
        *,
        group_id: int,
        now: datetime,
    ) -> _PendingAnnouncement | None:
        pig = await self._pick_candidate(
            group_id=group_id,
            now=now,
            ignore_recent_history=True,
            ignore_active_diseases=True,
        )
        if pig is None:
            return None

        group = await self._groups.get_by_id(group_id)
        if group is None:
            return None

        return await self._infect_pig(
            pig=pig,
            group=group,
            scheduled_for=now,
            slot_kind="manual",
            now=now,
            payload_extra={"trigger_mode": "manual"},
        )

    async def _pick_candidate(
        self,
        *,
        group_id: int,
        now: datetime,
        ignore_recent_history: bool = False,
        ignore_active_diseases: bool = False,
    ):
        active_disease_ids: list = []
        if not ignore_active_diseases:
            active_disease_ids = await self._effects.list_active_pig_ids_by_effect_types(
                group_id=group_id,
                effect_types=list(DISEASE_EFFECT_TYPES),
                now=now,
            )
        recent_disease_ids: list = []
        if not ignore_recent_history:
            recent_disease_ids = await self._rolls.list_recent_triggered_pig_ids(
                group_id=group_id,
                since=now - self._settings.disease_repeat_cooldown,
            )
        excluded = set(active_disease_ids) | set(recent_disease_ids)
        candidates = await self._pigs.list_disease_candidates(group_id=group_id)
        candidates = [
            pig
            for pig in candidates
            if pig.status == PigStatus.QUARANTINED or pig.id not in excluded
        ]
        if not candidates and recent_disease_ids:
            active_only = set(active_disease_ids)
            candidates = await self._pigs.list_disease_candidates(group_id=group_id)
            candidates = [
                pig
                for pig in candidates
                if pig.status == PigStatus.QUARANTINED or pig.id not in active_only
            ]
        if not candidates:
            return None
        return self._rng.choice(candidates)

    async def _infect_pig(
        self,
        *,
        pig,
        group,
        scheduled_for: datetime,
        slot_kind: str,
        now: datetime,
        payload_extra: dict[str, str] | None = None,
    ) -> _PendingAnnouncement:
        definition = pick_disease_definition(rng=self._rng)
        weight_loss = self._roll_weight_loss(current_weight=pig.weight_kg)
        pig.weight_kg -= weight_loss
        fatal_outcome = definition.fatal_outcome
        death_message = self._build_fatal_message(definition=definition, pig_name=pig.name) if fatal_outcome else None
        effect_expires_at = now if fatal_outcome else self._calculate_effect_expiry(definition=definition, now=now)
        quarantine_until = effect_expires_at if definition.quarantine_until_end_of_day and not fatal_outcome else None
        mood_delta = 0
        loyalty_delta = 0

        if fatal_outcome:
            pig.status = PigStatus.DEAD
            pig.quarantine_until = None
            pig.battle_ready_until = None
            pig.raid_until = None
        else:
            mood_delta = apply_mood_change(pig, delta=definition.mood_delta)
            loyalty_delta = apply_loyalty_change(pig, delta=definition.loyalty_delta)
            if quarantine_until is not None:
                pig.status = PigStatus.QUARANTINED
                pig.quarantine_until = quarantine_until
            if definition.effect_type is not None:
                await self._effects.create(
                    pig_id=pig.id,
                    group_id=pig.group_id,
                    effect_type=definition.effect_type,
                    source_type="disease",
                    payload={"disease_code": definition.code, "scheduled_for": scheduled_for.isoformat()},
                    expires_at=effect_expires_at,
                )

        await self._events.create(
            pig_id=pig.id,
            group_id=pig.group_id,
            event_type="disease_started",
            payload={
                "disease_code": definition.code,
                "disease_title": definition.title,
                "weight_loss": str(weight_loss),
                "effect_expires_at": effect_expires_at.isoformat() if not fatal_outcome else None,
                "quarantine_until": quarantine_until.isoformat() if quarantine_until is not None else None,
                "fatal_outcome": fatal_outcome,
                "death_message": death_message,
            },
        )
        if fatal_outcome:
            await self._events.create(
                pig_id=pig.id,
                group_id=pig.group_id,
                event_type="pig_died",
                payload={
                    "disease_code": definition.code,
                    "disease_title": definition.title,
                    "death_message": death_message,
                    "died_at": now.isoformat(),
                },
            )
        if quarantine_until is not None:
            await self._events.create(
                pig_id=pig.id,
                group_id=pig.group_id,
                event_type="disease_quarantined",
                payload={"quarantine_until": quarantine_until.isoformat()},
            )
        if mood_delta != 0:
            await self._events.create(
                pig_id=pig.id,
                group_id=pig.group_id,
                event_type="mood_changed",
                payload={"delta": mood_delta, "mood_score": pig.mood_score},
            )
        if loyalty_delta != 0:
            await self._events.create(
                pig_id=pig.id,
                group_id=pig.group_id,
                event_type="loyalty_changed",
                payload={"delta": loyalty_delta, "loyalty": pig.loyalty},
            )

        context = DiseaseNarrativeContext(
            group_id=group.id,
            pig_name=pig.name,
            disease_title=definition.title,
            disease_summary=definition.summary,
            fatal_outcome=fatal_outcome,
            death_message=death_message,
            weight_loss=weight_loss,
            current_weight=pig.weight_kg,
            mood_label=get_mood_label(pig.mood_score),
            loyalty_label=get_loyalty_label(pig.loyalty),
            effect_expires_at=effect_expires_at,
            quarantine_until=quarantine_until,
            tone_hint=definition.tone_hint,
            slot_kind=slot_kind,
        )
        fallback = self._narratives.build_fallback(context)
        payload = {
            "disease_title": definition.title,
            "effect_type": definition.effect_type,
            "weight_loss": str(weight_loss),
            "effect_expires_at": effect_expires_at.isoformat() if not fatal_outcome else None,
            "quarantine_until": quarantine_until.isoformat() if quarantine_until is not None else None,
            "slot_kind": slot_kind,
            "fatal_outcome": fatal_outcome,
            "death_message": death_message,
        }
        if payload_extra:
            payload.update(payload_extra)
        owner = await self._users.get_by_id(pig.owner_user_id)
        roll = await self._rolls.create(
            group_id=group.id,
            pig_id=pig.id,
            scheduled_for=scheduled_for,
            status=DiseaseRollStatus.TRIGGERED,
            disease_code=definition.code,
            narrative_text=fallback,
            llm_model=None,
            payload=payload,
        )
        return _PendingAnnouncement(
            roll=roll,
            telegram_group_id=group.telegram_group_id,
            group_title=group.title,
            owner_telegram_user_id=owner.telegram_user_id if owner is not None else None,
            owner_mention_label=self._owner_mention_label(owner),
            context=context,
        )

    async def _finalize_pending(self, item: _PendingAnnouncement) -> DiseaseAnnouncement:
        result = await self._narratives.generate_narrative(item.context)
        if result.text != item.roll.narrative_text or result.llm_model != item.roll.llm_model:
            async with self._session.begin():
                await self._rolls.set_narrative(
                    item.roll,
                    narrative_text=result.text,
                    llm_model=result.llm_model,
                )
        return DiseaseAnnouncement(
            roll_id=item.roll.id,
            telegram_group_id=item.telegram_group_id,
            text=result.text,
            group_title=item.group_title,
            owner_telegram_user_id=item.owner_telegram_user_id,
            owner_mention_label=item.owner_mention_label,
        )

    def _owner_mention_label(self, owner) -> str | None:
        if owner is None:
            return None
        if owner.username:
            return f"@{owner.username}"
        parts = [owner.first_name, owner.last_name]
        full_name = " ".join(part for part in parts if part)
        return full_name or owner.first_name

    def _roll_weight_loss(self, *, current_weight: Decimal) -> Decimal:
        raw_loss_percent = Decimal(
            str(
                self._rng.uniform(
                    self._settings.disease_weight_loss_min_percent,
                    self._settings.disease_weight_loss_max_percent,
                )
            )
        )
        raw_loss = current_weight * (raw_loss_percent / Decimal("100"))
        safe_loss = min(raw_loss, max(current_weight - MIN_PIG_WEIGHT, Decimal("0.00")))
        return quantize_weight(max(safe_loss, Decimal("0.00")))

    def _build_fatal_message(self, *, definition: DiseaseDefinition, pig_name: str) -> str:
        templates = definition.fatal_message_templates
        if not templates:
            return f"☠️ {pig_name} скончалась от «{definition.title}». Хлев даже не стал делать скорбное лицо."
        template = self._rng.choice(templates)
        return template.format(pig_name=pig_name, disease_title=definition.title)

    def _calculate_effect_expiry(self, *, definition: DiseaseDefinition, now: datetime) -> datetime:
        if definition.quarantine_until_end_of_day:
            return end_of_game_day(now)
        return now + timedelta(hours=definition.duration_hours or 0)
