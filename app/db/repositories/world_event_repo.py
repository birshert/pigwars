from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import WorldEvent


class WorldEventRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        event_code: str,
        title: str,
        description: str,
        starts_at: datetime,
        ends_at: datetime,
        modifiers: dict[str, Any] | None,
    ) -> WorldEvent:
        event = WorldEvent(
            event_code=event_code,
            title=title,
            description=description,
            starts_at=starts_at,
            ends_at=ends_at,
            modifiers=modifiers,
        )
        self._session.add(event)
        await self._session.flush()
        return event

    async def get_active(self, *, now: datetime) -> WorldEvent | None:
        stmt = (
            select(WorldEvent)
            .where(WorldEvent.starts_at <= now, WorldEvent.ends_at > now)
            .order_by(WorldEvent.starts_at.desc(), WorldEvent.id.desc())
        )
        return await self._session.scalar(stmt)

    async def get_latest(self) -> WorldEvent | None:
        stmt = select(WorldEvent).order_by(WorldEvent.starts_at.desc(), WorldEvent.id.desc())
        return await self._session.scalar(stmt)

    async def list_unannounced_active(self, *, now: datetime) -> list[WorldEvent]:
        stmt = (
            select(WorldEvent)
            .where(WorldEvent.starts_at <= now, WorldEvent.ends_at > now, WorldEvent.announced_at.is_(None))
            .order_by(WorldEvent.starts_at.asc(), WorldEvent.id.asc())
        )
        result = await self._session.scalars(stmt)
        return list(result.all())

    async def mark_announced(self, event: WorldEvent, *, now: datetime) -> None:
        event.announced_at = now
