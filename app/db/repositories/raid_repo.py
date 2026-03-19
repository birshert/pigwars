from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import PigRaid
from app.domain.models.pig import PigRaidStatus, RaidDestination


class PigRaidRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        pig_id: UUID,
        group_id: int,
        destination: RaidDestination,
        status: PigRaidStatus,
        started_at: datetime,
        resolve_at: datetime,
    ) -> PigRaid:
        raid = PigRaid(
            pig_id=pig_id,
            group_id=group_id,
            destination=destination,
            status=status,
            started_at=started_at,
            resolve_at=resolve_at,
        )
        self._session.add(raid)
        await self._session.flush()
        return raid

    async def list_due_for_update(self, *, now: datetime, limit: int) -> list[PigRaid]:
        stmt = (
            select(PigRaid)
            .where(PigRaid.status == PigRaidStatus.ACTIVE, PigRaid.resolve_at <= now)
            .order_by(PigRaid.resolve_at.asc(), PigRaid.created_at.asc())
            .limit(limit)
            .with_for_update()
        )
        result = await self._session.scalars(stmt)
        return list(result.all())

    async def get_active_for_pig(self, *, pig_id: UUID) -> PigRaid | None:
        stmt = (
            select(PigRaid)
            .where(PigRaid.pig_id == pig_id, PigRaid.status == PigRaidStatus.ACTIVE)
            .order_by(PigRaid.resolve_at.desc())
        )
        return await self._session.scalar(stmt)

    async def mark_resolved(
        self,
        raid: PigRaid,
        *,
        now: datetime,
        result_payload: dict[str, Any],
        status: PigRaidStatus = PigRaidStatus.RESOLVED,
    ) -> None:
        raid.status = status
        raid.resolved_at = now
        raid.result_payload = result_payload
