from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import and_, asc, delete, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.db.models import Pig, PigDailyAction, PigEffect, PigItem, TelegramGroup, TelegramUser
from app.domain.models.pig import PigStatus, PigTrait


class PigRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        group_id: int,
        owner_user_id: int,
        name: str,
        weight_kg: Decimal,
        trait: PigTrait,
        mood_score: int = 0,
        loyalty: int = 50,
    ) -> Pig:
        pig = Pig(
            group_id=group_id,
            owner_user_id=owner_user_id,
            name=name,
            weight_kg=weight_kg,
            status=PigStatus.IDLE,
            trait=trait,
            mood_score=mood_score,
            loyalty=loyalty,
        )
        self._session.add(pig)
        await self._session.flush()
        return pig

    async def get_by_group_owner(self, *, group_id: int, owner_user_id: int) -> Pig | None:
        stmt = select(Pig).where(
            Pig.group_id == group_id,
            Pig.owner_user_id == owner_user_id,
        )
        return await self._session.scalar(stmt)

    async def get_by_group_owner_for_update(self, *, group_id: int, owner_user_id: int) -> Pig | None:
        stmt = (
            select(Pig)
            .where(Pig.group_id == group_id, Pig.owner_user_id == owner_user_id)
            .with_for_update()
        )
        return await self._session.scalar(stmt)

    async def revive(
        self,
        pig: Pig,
        *,
        name: str,
        weight_kg: Decimal,
        trait: PigTrait,
        mood_score: int = 0,
        loyalty: int = 50,
    ) -> Pig:
        await self._session.execute(delete(PigItem).where(PigItem.pig_id == pig.id))
        await self._session.execute(delete(PigEffect).where(PigEffect.pig_id == pig.id))
        await self._session.execute(delete(PigDailyAction).where(PigDailyAction.pig_id == pig.id))

        pig.name = name
        pig.weight_kg = weight_kg
        pig.status = PigStatus.IDLE
        pig.trait = trait
        pig.mood_score = mood_score
        pig.loyalty = loyalty
        pig.wins = 0
        pig.losses = 0
        pig.last_feed_at = None
        pig.last_battle_at = None
        pig.last_sabotage_at = None
        pig.last_raid_at = None
        pig.battle_ready_until = None
        pig.raid_until = None
        pig.quarantine_until = None
        await self._session.flush()
        return pig

    async def get_by_ids_for_update(self, pig_ids: Sequence[UUID]) -> list[Pig]:
        stmt = select(Pig).where(Pig.id.in_(pig_ids)).with_for_update()
        result = await self._session.scalars(stmt)
        return list(result.all())

    async def get_by_id(self, pig_id: UUID) -> Pig | None:
        stmt = select(Pig).where(Pig.id == pig_id)
        return await self._session.scalar(stmt)

    async def get_by_id_for_update(self, pig_id: UUID) -> Pig | None:
        stmt = select(Pig).where(Pig.id == pig_id).with_for_update()
        return await self._session.scalar(stmt)

    async def list_ready_pigs(self, *, group_id: int, now: datetime, limit: int) -> list[Pig]:
        stmt = (
            select(Pig)
            .where(
                Pig.group_id == group_id,
                Pig.status == PigStatus.BATTLE_READY,
                Pig.battle_ready_until.is_not(None),
                Pig.battle_ready_until > now,
            )
            .order_by(asc(Pig.last_battle_at), asc(Pig.created_at))
            .limit(limit)
        )
        result = await self._session.scalars(stmt)
        return list(result.all())

    async def expire_ready_pigs(self, *, now: datetime) -> list[Pig]:
        stmt = select(Pig).where(
            Pig.status == PigStatus.BATTLE_READY,
            Pig.battle_ready_until.is_not(None),
            Pig.battle_ready_until <= now,
        )
        result = await self._session.scalars(stmt)
        pigs = list(result.all())
        for pig in pigs:
            pig.status = PigStatus.IDLE
            pig.battle_ready_until = None
        return pigs

    async def expire_quarantined_pigs(self, *, now: datetime) -> list[Pig]:
        stmt = select(Pig).where(
            Pig.status == PigStatus.QUARANTINED,
            Pig.quarantine_until.is_not(None),
            Pig.quarantine_until <= now,
        )
        result = await self._session.scalars(stmt)
        pigs = list(result.all())
        for pig in pigs:
            pig.status = PigStatus.IDLE
            pig.quarantine_until = None
        return pigs

    async def list_ready_group_ids(self, *, now: datetime, limit: int) -> list[int]:
        stmt = (
            select(Pig.group_id)
            .where(
                Pig.status == PigStatus.BATTLE_READY,
                Pig.battle_ready_until.is_not(None),
                Pig.battle_ready_until > now,
            )
            .group_by(Pig.group_id)
            .order_by(func.min(Pig.last_battle_at))
            .limit(limit)
        )
        result = await self._session.scalars(stmt)
        return list(result.all())

    async def list_group_ids_with_pigs(self) -> list[int]:
        stmt = (
            select(Pig.group_id)
            .where(Pig.status != PigStatus.DEAD)
            .group_by(Pig.group_id)
            .order_by(Pig.group_id.asc())
        )
        result = await self._session.scalars(stmt)
        return list(result.all())

    async def list_disease_candidates(
        self,
        *,
        group_id: int,
        excluded_pig_ids: Sequence[UUID] | None = None,
    ) -> list[Pig]:
        stmt = select(Pig).where(
            Pig.group_id == group_id,
            Pig.status.in_((PigStatus.IDLE, PigStatus.QUARANTINED)),
        ).order_by(asc(Pig.created_at), asc(Pig.name))
        if excluded_pig_ids:
            stmt = stmt.where(Pig.id.not_in(list(excluded_pig_ids)))
        result = await self._session.scalars(stmt)
        return list(result.all())

    async def list_weight_leaderboard(self, *, group_id: int, limit: int) -> list[tuple[Pig, TelegramUser]]:
        stmt = (
            select(Pig, TelegramUser)
            .join(TelegramUser, Pig.owner_user_id == TelegramUser.id)
            .where(Pig.group_id == group_id, Pig.status != PigStatus.DEAD)
            .order_by(desc(Pig.weight_kg), desc(Pig.wins), asc(Pig.name))
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.all())

    async def get_group_with_pig_for_owner(self, *, telegram_group_id: int, telegram_user_id: int) -> Pig | None:
        stmt = (
            select(Pig)
            .join(TelegramGroup, Pig.group_id == TelegramGroup.id)
            .join(TelegramUser, Pig.owner_user_id == TelegramUser.id)
            .where(
                TelegramGroup.telegram_group_id == telegram_group_id,
                TelegramUser.telegram_user_id == telegram_user_id,
            )
            .options(joinedload(Pig.owner), joinedload(Pig.group))
        )
        return await self._session.scalar(stmt)

    async def get_group_with_pig_by_owner_telegram_id(
        self,
        *,
        telegram_group_id: int,
        telegram_user_id: int,
    ) -> Pig | None:
        stmt = (
            select(Pig)
            .join(TelegramGroup, Pig.group_id == TelegramGroup.id)
            .join(TelegramUser, Pig.owner_user_id == TelegramUser.id)
            .where(
                TelegramGroup.telegram_group_id == telegram_group_id,
                TelegramUser.telegram_user_id == telegram_user_id,
            )
            .options(joinedload(Pig.owner), joinedload(Pig.group))
        )
        return await self._session.scalar(stmt)

    async def list_by_owner_telegram_id(self, *, telegram_user_id: int) -> list[Pig]:
        stmt = (
            select(Pig)
            .join(TelegramUser, Pig.owner_user_id == TelegramUser.id)
            .join(TelegramGroup, Pig.group_id == TelegramGroup.id)
            .where(TelegramUser.telegram_user_id == telegram_user_id)
            .options(joinedload(Pig.owner), joinedload(Pig.group))
            .order_by(TelegramGroup.title.asc(), Pig.created_at.asc())
        )
        result = await self._session.scalars(stmt)
        return list(result.unique().all())
