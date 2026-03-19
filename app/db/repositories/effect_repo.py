from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import and_, delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import PigEffect


class PigEffectRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        pig_id: UUID,
        group_id: int,
        effect_type: str,
        source_type: str,
        source_id: str | None = None,
        payload: dict[str, Any] | None = None,
        expires_at: datetime | None = None,
    ) -> PigEffect:
        effect = PigEffect(
            pig_id=pig_id,
            group_id=group_id,
            effect_type=effect_type,
            source_type=source_type,
            source_id=source_id,
            payload=payload,
            expires_at=expires_at,
        )
        self._session.add(effect)
        await self._session.flush()
        return effect

    def _active_predicate(self, *, now: datetime):
        return and_(
            PigEffect.consumed_at.is_(None),
            or_(PigEffect.expires_at.is_(None), PigEffect.expires_at > now),
        )

    async def list_active_for_pig(self, *, pig_id: UUID, now: datetime) -> list[PigEffect]:
        stmt = (
            select(PigEffect)
            .where(PigEffect.pig_id == pig_id, self._active_predicate(now=now))
            .order_by(PigEffect.created_at.asc(), PigEffect.id.asc())
        )
        result = await self._session.scalars(stmt)
        return list(result.all())

    async def list_active_for_pigs(self, *, pig_ids: list[UUID], now: datetime) -> list[PigEffect]:
        stmt = (
            select(PigEffect)
            .where(PigEffect.pig_id.in_(pig_ids), self._active_predicate(now=now))
            .order_by(PigEffect.created_at.asc(), PigEffect.id.asc())
        )
        result = await self._session.scalars(stmt)
        return list(result.all())

    async def get_first_matching_for_update(
        self,
        *,
        pig_id: UUID,
        effect_types: list[str],
        now: datetime,
    ) -> PigEffect | None:
        stmt = (
            select(PigEffect)
            .where(
                PigEffect.pig_id == pig_id,
                PigEffect.effect_type.in_(effect_types),
                self._active_predicate(now=now),
            )
            .order_by(PigEffect.created_at.asc(), PigEffect.id.asc())
            .with_for_update()
        )
        return await self._session.scalar(stmt)

    async def has_active_sabotage(self, *, pig_id: UUID, now: datetime) -> bool:
        stmt = (
            select(PigEffect.id)
            .where(
                PigEffect.pig_id == pig_id,
                PigEffect.source_type == "sabotage",
                self._active_predicate(now=now),
            )
            .limit(1)
        )
        return await self._session.scalar(stmt) is not None

    async def consume(self, effect: PigEffect, *, now: datetime) -> None:
        effect.consumed_at = now

    async def purge_inactive(self, *, now: datetime) -> int:
        stmt = delete(PigEffect).where(
            or_(
                PigEffect.consumed_at.is_not(None),
                and_(PigEffect.expires_at.is_not(None), PigEffect.expires_at <= now),
            )
        )
        result = await self._session.execute(stmt)
        return result.rowcount or 0
