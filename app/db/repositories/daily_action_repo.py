from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import PigDailyAction


class PigDailyActionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        pig_id: UUID,
        action_type: str,
        action_day: date,
        result_key: str,
        payload: dict[str, Any] | None = None,
    ) -> PigDailyAction:
        action = PigDailyAction(
            pig_id=pig_id,
            action_type=action_type,
            action_day=action_day,
            result_key=result_key,
            payload=payload,
        )
        self._session.add(action)
        await self._session.flush()
        return action

    async def get_for_day(
        self,
        *,
        pig_id: UUID,
        action_type: str,
        action_day: date,
    ) -> PigDailyAction | None:
        stmt = (
            select(PigDailyAction)
            .where(
                PigDailyAction.pig_id == pig_id,
                PigDailyAction.action_type == action_type,
                PigDailyAction.action_day == action_day,
            )
            .order_by(PigDailyAction.id.desc())
        )
        return await self._session.scalar(stmt)

    async def list_for_day(self, *, pig_id: UUID, action_day: date) -> list[PigDailyAction]:
        stmt = (
            select(PigDailyAction)
            .where(
                PigDailyAction.pig_id == pig_id,
                PigDailyAction.action_day == action_day,
            )
            .order_by(PigDailyAction.created_at.asc(), PigDailyAction.id.asc())
        )
        result = await self._session.scalars(stmt)
        return list(result.all())
