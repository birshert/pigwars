from __future__ import annotations

from decimal import Decimal
import random
from dataclasses import dataclass
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


@dataclass(frozen=True, slots=True)
class WeightCorridor:
    max_difference_kg: Decimal
    max_difference_ratio: Decimal


EARLY_CORRIDOR = WeightCorridor(max_difference_kg=Decimal("4.00"), max_difference_ratio=Decimal("0.15"))
MID_CORRIDOR = WeightCorridor(max_difference_kg=Decimal("7.00"), max_difference_ratio=Decimal("0.25"))
LATE_CORRIDOR = WeightCorridor(max_difference_kg=Decimal("12.00"), max_difference_ratio=Decimal("0.40"))
EARLY_WAIT_WINDOW = timedelta(minutes=2)
MID_WAIT_WINDOW = timedelta(minutes=4)


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
        pairs: list[tuple[UUID, UUID]] = []
        available = list(pigs)

        while len(available) > 1:
            anchor = available.pop(0)
            candidate_index = self._find_best_candidate(anchor, available, now=now)
            if candidate_index is None:
                continue

            candidate = available.pop(candidate_index)
            if self._should_match(anchor.last_battle_at or now, candidate.last_battle_at or now, now=now):
                pairs.append((anchor.id, candidate.id))
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

    def _find_best_candidate(self, anchor, candidates: list, *, now: datetime) -> int | None:
        best_index: int | None = None
        best_key: tuple[Decimal, datetime, datetime] | None = None

        for index, candidate in enumerate(candidates):
            if not self._is_within_weight_corridor(anchor, candidate, now=now):
                continue

            key = (
                self._calculate_relative_weight_gap(anchor.weight_kg, candidate.weight_kg),
                ensure_utc(candidate.last_battle_at) or now,
                candidate.created_at,
            )
            if best_key is None or key < best_key:
                best_index = index
                best_key = key

        return best_index

    def _is_within_weight_corridor(self, pig1, pig2, *, now: datetime) -> bool:
        weight_gap = abs(pig1.weight_kg - pig2.weight_kg)
        heavier_weight = max(pig1.weight_kg, pig2.weight_kg)
        corridor_limit = min(
            self._calculate_weight_corridor(pig1.last_battle_at or now, heavier_weight=heavier_weight, now=now),
            self._calculate_weight_corridor(pig2.last_battle_at or now, heavier_weight=heavier_weight, now=now),
        )
        return weight_gap <= corridor_limit

    def _calculate_weight_corridor(self, ready_at: datetime, *, heavier_weight: Decimal, now: datetime) -> Decimal:
        corridor = self._resolve_weight_corridor(ready_at, now=now)
        return max(corridor.max_difference_kg, heavier_weight * corridor.max_difference_ratio)

    def _resolve_weight_corridor(self, ready_at: datetime, *, now: datetime) -> WeightCorridor:
        normalized_now = ensure_utc(now) or now
        normalized_ready_at = ensure_utc(ready_at) or ready_at
        waited_for = max(normalized_now - normalized_ready_at, timedelta())

        if waited_for < EARLY_WAIT_WINDOW:
            return EARLY_CORRIDOR
        if waited_for < MID_WAIT_WINDOW:
            return MID_CORRIDOR
        return LATE_CORRIDOR

    def _calculate_relative_weight_gap(self, weight1: Decimal, weight2: Decimal) -> Decimal:
        heavier_weight = max(weight1, weight2)
        if heavier_weight <= Decimal("0.00"):
            return Decimal("0.00")
        return abs(weight1 - weight2) / heavier_weight
