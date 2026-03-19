from __future__ import annotations

import random
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories.event_repo import PigEventRepository
from app.db.repositories.group_repo import GroupRepository
from app.db.repositories.pig_repo import PigRepository
from app.db.repositories.user_repo import UserRepository
from app.domain.exceptions import ConcurrentActionError, FeedCooldownError, PigBusyError, PigNotFoundError
from app.domain.models.pig import PigStatus
from app.domain.rules.combat import roll_feed_gain
from app.domain.rules.cooldowns import get_remaining_cooldown
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

                gain = roll_feed_gain(self._rng)
                pig.weight_kg += gain
                pig.last_feed_at = now

                await self._events.create(
                    pig_id=pig.id,
                    group_id=pig.group_id,
                    event_type="pig_fed",
                    payload={"weight_gain": str(gain), "weight_kg": str(pig.weight_kg)},
                )
        finally:
            await lease.release()

        return FeedResult(
            pig_name=pig.name,
            weight_gain=gain,
            current_weight=pig.weight_kg,
            next_feed_in=self._feed_cooldown,
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
