from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories.event_repo import PigEventRepository
from app.db.repositories.group_repo import GroupRepository
from app.db.repositories.pig_repo import PigRepository
from app.db.repositories.user_repo import UserRepository
from app.domain.exceptions import InvalidPigNameError, PigAlreadyExistsError, PigNotFoundError
from app.domain.models.pig import PigCooldowns, PigSnapshot
from app.domain.rules.combat import STARTING_PIG_WEIGHT
from app.domain.rules.cooldowns import get_remaining_cooldown
from app.schemas.pig import PigProfile


class PigService:
    def __init__(self, session: AsyncSession, *, feed_cooldown, battle_cooldown) -> None:
        self._session = session
        self._groups = GroupRepository(session)
        self._users = UserRepository(session)
        self._pigs = PigRepository(session)
        self._events = PigEventRepository(session)
        self._feed_cooldown = feed_cooldown
        self._battle_cooldown = battle_cooldown

    async def create_pig(
        self,
        *,
        telegram_group_id: int,
        group_title: str,
        telegram_user_id: int,
        username: str | None,
        first_name: str,
        last_name: str | None,
        pig_name: str,
        now: datetime,
    ) -> PigProfile:
        normalized_name = self._normalize_name(pig_name)

        async with self._session.begin():
            group = await self._groups.get_or_create(telegram_group_id, group_title)
            user = await self._users.get_or_create(
                telegram_user_id,
                username=username,
                first_name=first_name,
                last_name=last_name,
            )
            existing = await self._pigs.get_by_group_owner(group_id=group.id, owner_user_id=user.id)
            if existing is not None:
                raise PigAlreadyExistsError

            pig = await self._pigs.create(
                group_id=group.id,
                owner_user_id=user.id,
                name=normalized_name,
                weight_kg=STARTING_PIG_WEIGHT,
            )
            await self._events.create(
                pig_id=pig.id,
                group_id=group.id,
                event_type="pig_created",
                payload={"name": pig.name, "weight_kg": str(pig.weight_kg)},
            )

        return self._to_profile(pig, now=now)

    async def get_pig_profile(
        self,
        *,
        telegram_group_id: int,
        telegram_user_id: int,
        now: datetime,
    ) -> PigProfile:
        pig = await self._pigs.get_group_with_pig_for_owner(
            telegram_group_id=telegram_group_id,
            telegram_user_id=telegram_user_id,
        )
        if pig is None:
            raise PigNotFoundError

        return self._to_profile(pig, now=now)

    def _normalize_name(self, pig_name: str) -> str:
        normalized = " ".join(pig_name.split()).strip()
        if not 3 <= len(normalized) <= 40:
            raise InvalidPigNameError
        return normalized

    def _to_profile(self, pig, *, now: datetime) -> PigProfile:
        snapshot = PigSnapshot(
            id=pig.id,
            name=pig.name,
            weight_kg=pig.weight_kg,
            status=pig.status,
            wins=pig.wins,
            losses=pig.losses,
            last_feed_at=pig.last_feed_at,
            last_battle_at=pig.last_battle_at,
            battle_ready_until=pig.battle_ready_until,
        )
        cooldowns = PigCooldowns(
            next_feed_in=get_remaining_cooldown(snapshot.last_feed_at, self._feed_cooldown, now),
            next_battle_in=get_remaining_cooldown(snapshot.last_battle_at, self._battle_cooldown, now),
        )
        return PigProfile(
            pig_id=snapshot.id,
            name=snapshot.name,
            weight_kg=snapshot.weight_kg,
            status=snapshot.status,
            wins=snapshot.wins,
            losses=snapshot.losses,
            next_feed_in=cooldowns.next_feed_in,
            next_battle_in=cooldowns.next_battle_in,
            battle_ready_until=snapshot.battle_ready_until,
        )
