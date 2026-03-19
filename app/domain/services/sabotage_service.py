from __future__ import annotations

import random
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db.repositories.effect_repo import PigEffectRepository
from app.db.repositories.event_repo import PigEventRepository
from app.db.repositories.group_repo import GroupRepository
from app.db.repositories.pig_repo import PigRepository
from app.db.repositories.user_repo import UserRepository
from app.domain.feature_catalog import (
    EFFECT_ARENA_NERVES,
    EFFECT_FEED_SPOILED,
    EFFECT_MUDDY_PANIC,
    EFFECT_ROUTE_CONFUSED,
    get_item_definition,
)
from app.domain.exceptions import PigBusyError, PigNotFoundError, SabotageBlockedError, SabotageCooldownError, SabotageTargetError
from app.domain.models.pig import PigStatus
from app.domain.rules.cooldowns import get_remaining_cooldown
from app.domain.rules.pig_state import apply_loyalty_change, apply_mood_change
from app.domain.services.daily_feature_service import DailyFeatureService
from app.domain.services.item_service import ItemService
from app.domain.services.pig_modifier_resolver import PigModifierResolver
from app.schemas.pig import SabotageResult


class SabotageService:
    def __init__(self, session: AsyncSession, *, settings: Settings, rng: random.Random) -> None:
        self._session = session
        self._settings = settings
        self._rng = rng
        self._groups = GroupRepository(session)
        self._users = UserRepository(session)
        self._pigs = PigRepository(session)
        self._effects = PigEffectRepository(session)
        self._events = PigEventRepository(session)
        self._resolver = PigModifierResolver(session)
        self._items = ItemService(session, rng=rng)
        self._daily = DailyFeatureService(session, rng=rng)

    async def sabotage(
        self,
        *,
        telegram_group_id: int,
        attacker_telegram_user_id: int,
        target_telegram_user_id: int,
        now: datetime,
    ) -> SabotageResult:
        async with self._session.begin():
            group = await self._groups.get_by_telegram_id(telegram_group_id)
            attacker_user = await self._users.get_by_telegram_id(attacker_telegram_user_id)
            target_user = await self._users.get_by_telegram_id(target_telegram_user_id)
            if group is None or attacker_user is None or target_user is None:
                raise PigNotFoundError
            if attacker_user.id == target_user.id:
                raise SabotageTargetError

            attacker = await self._pigs.get_by_group_owner(group_id=group.id, owner_user_id=attacker_user.id)
            target = await self._pigs.get_by_group_owner(group_id=group.id, owner_user_id=target_user.id)
            if attacker is None or target is None:
                raise PigNotFoundError

            pigs = await self._pigs.get_by_ids_for_update(sorted([attacker.id, target.id], key=str))
            pig_map = {pig.id: pig for pig in pigs}
            attacker = pig_map.get(attacker.id)
            target = pig_map.get(target.id)
            if attacker is None or target is None:
                raise PigNotFoundError

            if attacker.status in {PigStatus.ON_RAID, PigStatus.IN_BATTLE}:
                raise PigBusyError
            if target.status in {PigStatus.ON_RAID, PigStatus.IN_BATTLE}:
                raise SabotageBlockedError

            remaining = get_remaining_cooldown(attacker.last_sabotage_at, self._settings.sabotage_cooldown, now)
            if remaining.total_seconds() > 0:
                raise SabotageCooldownError(remaining=remaining)

            if await self._effects.has_active_sabotage(pig_id=target.id, now=now):
                raise SabotageBlockedError

            await self._daily.ensure_horoscope_for_pig(attacker, now=now)
            sabotage_state = await self._resolver.resolve_sabotage_modifiers(attacker, target, now=now)
            attacker.last_sabotage_at = now

            success = self._rng.random() < sabotage_state.success_chance
            target_equipped = await self._resolver.get_equipped_item(pig_id=target.id, now=now)
            if success:
                effect_type, effect_title = self._pick_effect(target.status)
                await self._effects.create(
                    pig_id=target.id,
                    group_id=target.group_id,
                    effect_type=effect_type,
                    source_type="sabotage",
                    source_id=str(attacker.id),
                    expires_at=now + timedelta(hours=8),
                )
                mood_delta = apply_mood_change(target, delta=-6)
                loyalty_delta = apply_loyalty_change(target, delta=-2)
                await self._events.create(
                    pig_id=target.id,
                    group_id=target.group_id,
                    event_type="sabotage_success",
                    payload={"attacker_id": str(attacker.id), "effect_type": effect_type},
                )
                if mood_delta != 0:
                    await self._events.create(
                        pig_id=target.id,
                        group_id=target.group_id,
                        event_type="mood_changed",
                        payload={"delta": mood_delta, "mood_score": target.mood_score},
                    )
                if loyalty_delta != 0:
                    await self._events.create(
                        pig_id=target.id,
                        group_id=target.group_id,
                        event_type="loyalty_changed",
                        payload={"delta": loyalty_delta, "loyalty": target.loyalty},
                    )
                broken_item = await self._wear_sabotage_item(target_equipped, now=now)
                narrative = (
                    f"{attacker.name} устроила диверсию против {target.name}. "
                    f"На цели повис эффект «{effect_title}»."
                )
                if broken_item is not None:
                    narrative += f" Защита «{broken_item}» не выдержала нагрузки."
                return SabotageResult(
                    attacker_name=attacker.name,
                    target_name=target.name,
                    success=True,
                    effect_title=effect_title,
                    narrative=narrative,
                )

            mood_delta = apply_mood_change(attacker, delta=-5)
            await self._events.create(
                pig_id=attacker.id,
                group_id=attacker.group_id,
                event_type="sabotage_failed",
                payload={"target_id": str(target.id)},
            )
            if mood_delta != 0:
                await self._events.create(
                    pig_id=attacker.id,
                    group_id=attacker.group_id,
                    event_type="mood_changed",
                    payload={"delta": mood_delta, "mood_score": attacker.mood_score},
                )
            broken_item = await self._wear_sabotage_item(target_equipped, now=now)
            defense_note = ""
            if target_equipped is not None:
                defense_item = get_item_definition(target_equipped.item_code)
                if defense_item.sabotage_defense_modifier > 0:
                    defense_note = f" {target.name} спасла экипировка «{defense_item.title}»."
            if broken_item is not None:
                defense_note += f" Правда, «{broken_item}» от такого почти развалилась."
            return SabotageResult(
                attacker_name=attacker.name,
                target_name=target.name,
                success=False,
                effect_title=None,
                narrative=f"{attacker.name} спалилась на диверсии против {target.name}.{defense_note}",
            )

    def _pick_effect(self, target_status: PigStatus) -> tuple[str, str]:
        if target_status == PigStatus.BATTLE_READY:
            return EFFECT_ARENA_NERVES, "Нервы перед ареной"
        roll = self._rng.random()
        if roll < 0.25:
            return EFFECT_FEED_SPOILED, "Испорченный корм"
        if roll < 0.50:
            return EFFECT_ARENA_NERVES, "Нервы перед ареной"
        if roll < 0.75:
            return EFFECT_MUDDY_PANIC, "Грязная паника"
        return EFFECT_ROUTE_CONFUSED, "Сбитый маршрут"

    async def _wear_sabotage_item(self, item, *, now: datetime) -> str | None:
        if item is None:
            return None
        if get_item_definition(item.item_code).sabotage_defense_modifier <= 0:
            return None
        return await self._items.wear_item(item, now=now)
