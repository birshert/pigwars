from __future__ import annotations

import random
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db.repositories.effect_repo import PigEffectRepository
from app.db.repositories.event_repo import PigEventRepository
from app.db.repositories.group_repo import GroupRepository
from app.db.repositories.pig_repo import PigRepository
from app.db.repositories.raid_repo import PigRaidRepository
from app.db.repositories.user_repo import UserRepository
from app.domain.feature_catalog import (
    EFFECT_ARENA_NERVES,
    EFFECT_BATTLE_FOCUS,
    EFFECT_FEED_SPOILED,
    EFFECT_GOOD_OMENS,
    EFFECT_MUDDY_PANIC,
    EFFECT_ROUTE_CONFUSED,
    get_item_definition,
    get_loyalty_label,
    get_mood_label,
    get_raid_destination,
)
from app.domain.exceptions import PigBusyError, PigNotFoundError, RaidCooldownError, RaidRefusedError
from app.domain.models.pig import PigRaidStatus, PigStatus, RaidDestination
from app.domain.rules.combat import quantize_weight
from app.domain.rules.cooldowns import get_remaining_cooldown
from app.domain.rules.pig_state import apply_loyalty_change, apply_mood_change
from app.domain.services.item_service import ItemService
from app.domain.services.pig_modifier_resolver import PigModifierResolver
from app.schemas.pig import RaidResolutionResult, RaidStartResult


class RaidService:
    def __init__(self, session: AsyncSession, *, settings: Settings, rng: random.Random) -> None:
        self._session = session
        self._settings = settings
        self._rng = rng
        self._groups = GroupRepository(session)
        self._users = UserRepository(session)
        self._pigs = PigRepository(session)
        self._events = PigEventRepository(session)
        self._effects = PigEffectRepository(session)
        self._raids = PigRaidRepository(session)
        self._resolver = PigModifierResolver(session)
        self._items = ItemService(session, rng=rng)

    async def start_raid(
        self,
        *,
        telegram_group_id: int,
        telegram_user_id: int,
        destination: RaidDestination,
        now: datetime,
    ) -> RaidStartResult:
        async with self._session.begin():
            pig = await self._get_locked_pig(telegram_group_id=telegram_group_id, telegram_user_id=telegram_user_id)
            if pig.status != PigStatus.IDLE:
                raise PigBusyError

            remaining = get_remaining_cooldown(pig.last_raid_at, self._settings.raid_cooldown, now)
            if remaining.total_seconds() > 0:
                raise RaidCooldownError(remaining=remaining)

            if pig.loyalty < 20 and self._rng.random() < 0.25:
                apply_mood_change(pig, delta=-4)
                apply_loyalty_change(pig, delta=-2)
                raise RaidRefusedError

            resolve_at = now + self._settings.raid_duration
            pig.status = PigStatus.ON_RAID
            pig.last_raid_at = now
            pig.raid_until = resolve_at
            await self._raids.create(
                pig_id=pig.id,
                group_id=pig.group_id,
                destination=destination,
                status=PigRaidStatus.ACTIVE,
                started_at=now,
                resolve_at=resolve_at,
            )
            await self._events.create(
                pig_id=pig.id,
                group_id=pig.group_id,
                event_type="raid_started",
                payload={"destination": destination.value, "resolve_at": resolve_at.isoformat()},
            )

        return RaidStartResult(
            pig_name=pig.name,
            destination_title=get_raid_destination(destination).title,
            resolve_at=resolve_at,
            next_raid_in=self._settings.raid_cooldown,
        )

    async def resolve_due_raids(self, *, now: datetime) -> list[RaidResolutionResult]:
        results: list[RaidResolutionResult] = []
        async with self._session.begin():
            raids = await self._raids.list_due_for_update(
                now=now,
                limit=self._settings.raid_resolution_batch_size,
            )
            for raid in raids:
                pig = await self._pigs.get_by_id_for_update(raid.pig_id)
                if pig is None:
                    continue
                result = await self._resolve_single_raid(pig, raid=raid, now=now)
                if result is not None:
                    results.append(result)
        return results

    async def _resolve_single_raid(self, pig, *, raid, now: datetime) -> RaidResolutionResult | None:
        raid_state = await self._resolver.resolve_raid_state(pig, destination=raid.destination, now=now)
        destination = get_raid_destination(raid.destination)
        good_chance, bad_chance = self._build_outcome_chances(raid_state.modifier, raid_state.bad_outcome_modifier)
        roll = self._rng.random()

        if roll < good_chance:
            outcome = "good"
        elif roll < good_chance + bad_chance:
            outcome = "bad"
        else:
            outcome = "neutral"

        if outcome == "bad" and raid_state.guard_effect is not None:
            await self._effects.consume(raid_state.guard_effect, now=now)
            outcome = "neutral"

        for effect in raid_state.one_shot_effects:
            await self._effects.consume(effect, now=now)

        found_item_title: str | None = None
        granted_effect_title: str | None = None
        weight_change = Decimal("0.00")
        narrative = ""
        mood_delta = 0
        loyalty_delta = 0

        if outcome == "good":
            weight_change = quantize_weight(
                Decimal(str(self._rng.uniform(0.30, 1.10))) * raid_state.reward_multiplier
            )
            pig.weight_kg += weight_change
            mood_delta = apply_mood_change(pig, delta=8)
            loyalty_delta = apply_loyalty_change(pig, delta=3)
            item_chance = max(0.15, min(0.85, 0.40 + float(raid_state.item_modifier)))
            if self._rng.random() < item_chance:
                found_item = await self._items.award_random_item(
                    pig=pig,
                    source_key=raid.destination.value,
                    now=now,
                    source_type="raid",
                    source_id=str(raid.id),
                )
                if found_item is not None:
                    found_item_title = found_item.title
            elif raid.destination == RaidDestination.WOODS:
                await self._effects.create(
                    pig_id=pig.id,
                    group_id=pig.group_id,
                    effect_type=EFFECT_BATTLE_FOCUS,
                    source_type="raid",
                    source_id=str(raid.id),
                    expires_at=now + timedelta(hours=12),
                )
                granted_effect_title = "Боевой раж"
            else:
                await self._effects.create(
                    pig_id=pig.id,
                    group_id=pig.group_id,
                    effect_type=EFFECT_GOOD_OMENS,
                    source_type="raid",
                    source_id=str(raid.id),
                    expires_at=now + timedelta(hours=12),
                )
                granted_effect_title = "Добрые приметы"
            narrative = self._good_narrative(destination.title, found_item_title, granted_effect_title)
            outcome_title = "Удачная вылазка"
        elif outcome == "neutral":
            mood_delta = apply_mood_change(pig, delta=2)
            narrative = f"{pig.name} вернулась из локации «{destination.title}» без большого лута, но и без позора."
            outcome_title = "Нейтральный исход"
        else:
            mood_delta = apply_mood_change(pig, delta=-12)
            loyalty_delta = apply_loyalty_change(pig, delta=-4)
            bad_effect = self._bad_raid_effect(raid.destination)
            await self._effects.create(
                pig_id=pig.id,
                group_id=pig.group_id,
                effect_type=bad_effect,
                source_type="raid",
                source_id=str(raid.id),
                expires_at=now + timedelta(hours=12),
            )
            granted_effect_title = {
                EFFECT_FEED_SPOILED: "Испорченный корм",
                EFFECT_ARENA_NERVES: "Нервы перед ареной",
                EFFECT_MUDDY_PANIC: "Грязная паника",
                EFFECT_ROUTE_CONFUSED: "Сбитый маршрут",
            }[bad_effect]
            narrative = self._bad_narrative(destination.title, granted_effect_title)
            outcome_title = "Провальная вылазка"

        broken_item = await self._wear_raid_item(raid_state.equipped_item, now=now)
        pig.status = PigStatus.IDLE
        pig.raid_until = None
        await self._raids.mark_resolved(
            raid,
            now=now,
            result_payload={
                "outcome": outcome,
                "weight_change": str(weight_change),
                "found_item_title": found_item_title,
                "granted_effect_title": granted_effect_title,
                "world_event_title": raid_state.world_event_title,
            },
        )
        await self._events.create(
            pig_id=pig.id,
            group_id=pig.group_id,
            event_type="raid_finished",
            payload={
                "destination": raid.destination.value,
                "outcome": outcome,
                "weight_change": str(weight_change),
                "found_item_title": found_item_title,
                "granted_effect_title": granted_effect_title,
            },
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
        if broken_item is not None:
            narrative += f" Экипировка «{broken_item}» не пережила это приключение."

        group = await self._groups.get_by_id(pig.group_id)
        if group is None:
            return None
        return RaidResolutionResult(
            telegram_group_id=group.telegram_group_id,
            pig_name=pig.name,
            destination_title=destination.title,
            outcome_title=outcome_title,
            narrative=narrative,
            weight_change=weight_change,
            mood_label=get_mood_label(pig.mood_score),
            loyalty_label=get_loyalty_label(pig.loyalty),
            found_item_title=found_item_title,
            granted_effect_title=granted_effect_title,
        )

    async def _get_locked_pig(self, *, telegram_group_id: int, telegram_user_id: int):
        group = await self._groups.get_by_telegram_id(telegram_group_id)
        user = await self._users.get_by_telegram_id(telegram_user_id)
        if group is None or user is None:
            raise PigNotFoundError

        pig = await self._pigs.get_by_group_owner_for_update(group_id=group.id, owner_user_id=user.id)
        if pig is None:
            raise PigNotFoundError
        return pig

    def _build_outcome_chances(self, modifier: Decimal, bad_outcome_modifier: Decimal) -> tuple[float, float]:
        good = max(0.20, min(0.75, 0.45 + float(modifier)))
        bad = max(0.05, min(0.45, 0.22 + float(bad_outcome_modifier) - float(modifier) / 2))
        if good + bad > 0.90:
            overflow = good + bad - 0.90
            bad = max(0.05, bad - overflow)
        return good, bad

    def _good_narrative(self, destination_title: str, found_item_title: str | None, granted_effect_title: str | None) -> str:
        if found_item_title is not None:
            return f"В локации «{destination_title}» свинья нарыла трофей: {found_item_title}."
        if granted_effect_title is not None:
            return f"Вылазка в «{destination_title}» закалила свинью и дала эффект «{granted_effect_title}»."
        return f"Вылазка в «{destination_title}» прошла на редкость бодро."

    def _bad_narrative(self, destination_title: str, effect_title: str) -> str:
        return f"Поход в «{destination_title}» закончился позором. Свинья вернулась с эффектом «{effect_title}»."

    def _bad_raid_effect(self, destination: RaidDestination) -> str:
        if destination == RaidDestination.DUMP:
            return EFFECT_MUDDY_PANIC
        if destination == RaidDestination.MARKET:
            return EFFECT_FEED_SPOILED
        if destination == RaidDestination.WOODS and self._rng.random() < 0.5:
            return EFFECT_ARENA_NERVES
        return EFFECT_ROUTE_CONFUSED

    async def _wear_raid_item(self, item, *, now: datetime) -> str | None:
        if item is None:
            return None
        if get_item_definition(item.item_code).raid_modifier <= 0:
            return None
        return await self._items.wear_item(item, now=now)
