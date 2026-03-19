from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import PigEvent


class PigEventRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        pig_id: UUID,
        group_id: int,
        event_type: str,
        payload: dict[str, Any] | None = None,
    ) -> PigEvent:
        event = PigEvent(
            pig_id=pig_id,
            group_id=group_id,
            event_type=event_type,
            payload=payload,
        )
        self._session.add(event)
        await self._session.flush()
        return event
