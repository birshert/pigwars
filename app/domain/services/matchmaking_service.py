from __future__ import annotations

import random
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db.repositories.event_repo import PigEventRepository
from app.db.repositories.pig_repo import PigRepository
from app.domain.rules.cooldowns import ensure_utc
from app.domain.services.battle_service import BattleService
from app.infra.locks import RedisLockManager
from app.schemas.battle import BattleMessagePayload


class MatchmakingService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        settings: Settings,
        rng: random.Random,
        lock_manager: RedisLockManager,
    ) -> None:
        self._session = session
        self._settings = settings
        self._rng = rng
        self._pigs = PigRepository(session)
        self._events = PigEventRepository(session)
        self._battle_service = BattleService(session, rng=rng, lock_manager=lock_manager)

    async def expire_battle_mode(self, *, now: datetime) -> int:
        async with self._session.begin():
            expired = await self._pigs.expire_ready_pigs(now=now)
            for pig in expired:
                await self._events.create(
                    pig_id=pig.id,
                    group_id=pig.group_id,
                    event_type="battle_ready_expired",
                    payload={"expired_at": now.isoformat()},
                )
        return len(expired)

    async def find_candidate_pairs(self, *, group_id: int, now: datetime) -> list[tuple[UUID, UUID]]:
        pigs = await self._pigs.list_ready_pigs(
            group_id=group_id,
            now=now,
            limit=self._settings.matchmaking_batch_size,
        )
        self._rng.shuffle(pigs)

        pairs: list[tuple[UUID, UUID]] = []
        for index in range(0, len(pigs) - 1, 2):
            first = pigs[index]
            second = pigs[index + 1]
            if self._should_match(first.last_battle_at or now, second.last_battle_at or now, now=now):
                pairs.append((first.id, second.id))
        return pairs

    async def process_matchmaking_cycle(self, *, now: datetime) -> list[BattleMessagePayload]:
        group_ids = await self._pigs.list_ready_group_ids(
            now=now,
            limit=self._settings.matchmaking_batch_size,
        )
        await self._session.commit()
        battles: list[BattleMessagePayload] = []

        for group_id in group_ids:
            pairs = await self.find_candidate_pairs(group_id=group_id, now=now)
            await self._session.commit()
            for pig1_id, pig2_id in pairs:
                payload = await self._battle_service.resolve_pair(
                    group_id=group_id,
                    pig1_id=pig1_id,
                    pig2_id=pig2_id,
                    now=now,
                )
                if payload is not None:
                    battles.append(payload)

        return battles

    def _should_match(self, pig1_ready_at: datetime, pig2_ready_at: datetime, *, now: datetime) -> bool:
        first_ready_at = ensure_utc(pig1_ready_at) or pig1_ready_at
        second_ready_at = ensure_utc(pig2_ready_at) or pig2_ready_at
        probability = self._calculate_probability(min(first_ready_at, second_ready_at), now=now)
        return self._rng.random() <= probability

    def _calculate_probability(self, ready_at: datetime, *, now: datetime) -> float:
        normalized_now = ensure_utc(now) or now
        normalized_ready_at = ensure_utc(ready_at) or ready_at
        waited_seconds = max((normalized_now - normalized_ready_at).total_seconds(), 0.0)
        increments = int(waited_seconds // timedelta(seconds=self._settings.match_wait_bonus_every_seconds).total_seconds())
        probability = self._settings.match_base_probability + (increments * self._settings.match_wait_bonus)
        return min(probability, self._settings.match_probability_cap)
