from __future__ import annotations

import random
from datetime import datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories.event_repo import PigEventRepository
from app.db.repositories.effect_repo import PigEffectRepository
from app.db.repositories.group_repo import GroupRepository
from app.db.repositories.pig_repo import PigRepository
from app.db.repositories.user_repo import UserRepository
from app.domain.exceptions import ConcurrentActionError, FeedCooldownError, PigBusyError, PigNotFoundError
from app.domain.models.pig import PigStatus
from app.domain.feature_catalog import get_loyalty_label, get_mood_label
from app.domain.rules.combat import quantize_weight, roll_feed_gain
from app.domain.rules.cooldowns import get_remaining_cooldown
from app.domain.rules.pig_state import apply_loyalty_change, apply_mood_change
from app.domain.services.pig_modifier_resolver import PigModifierResolver
from app.infra.locks import RedisLockManager
from app.schemas.pig import FeedResult


class FeedingService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        feed_cooldown,
        rng: random.Random,
        lock_manager: RedisLockManager,
    ) -> None:
        self._session = session
        self._groups = GroupRepository(session)
        self._users = UserRepository(session)
        self._pigs = PigRepository(session)
        self._events = PigEventRepository(session)
        self._effects = PigEffectRepository(session)
        self._resolver = PigModifierResolver(session)
        self._feed_cooldown = feed_cooldown
        self._rng = rng
        self._lock_manager = lock_manager

    async def feed_pig(
        self,
        *,
        telegram_group_id: int,
        telegram_user_id: int,
        now: datetime,
    ) -> FeedResult:
        lease = await self._lock_manager.acquire(f"feed:{telegram_group_id}:{telegram_user_id}", ttl_seconds=10)
        if not lease.acquired:
            raise ConcurrentActionError

        try:
            async with self._session.begin():
                pig = await self._get_locked_pig(telegram_group_id=telegram_group_id, telegram_user_id=telegram_user_id)
                if pig.status != PigStatus.IDLE:
                    raise PigBusyError

                remaining = get_remaining_cooldown(pig.last_feed_at, self._feed_cooldown, now)
                if remaining.total_seconds() > 0:
                    raise FeedCooldownError(remaining=remaining)

                feed_state = await self._resolver.resolve_feed_state(pig, now=now)
                gain = self._apply_feed_modifier(roll_feed_gain(self._rng), feed_state.modifier)
                pig.weight_kg += gain
                pig.last_feed_at = now
                mood_delta = apply_mood_change(pig, delta=6)
                loyalty_delta = apply_loyalty_change(pig, delta=2)
                for effect in feed_state.one_shot_effects:
                    await self._effects.consume(effect, now=now)

                await self._events.create(
                    pig_id=pig.id,
                    group_id=pig.group_id,
                    event_type="pig_fed",
                    payload={
                        "weight_gain": str(gain),
                        "weight_kg": str(pig.weight_kg),
                        "modifier": str(feed_state.modifier),
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
        finally:
            await lease.release()

        return FeedResult(
            pig_name=pig.name,
            weight_gain=gain,
            current_weight=pig.weight_kg,
            next_feed_in=self._feed_cooldown,
            mood_label=get_mood_label(pig.mood_score),
            loyalty_label=get_loyalty_label(pig.loyalty),
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

    def _apply_feed_modifier(self, gain: Decimal, modifier: Decimal) -> Decimal:
        return quantize_weight(gain * (Decimal("1.00") + modifier))
