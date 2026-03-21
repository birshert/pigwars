from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import GroupDiseaseRoll
from app.domain.models.disease import DiseaseRollStatus


class GroupDiseaseRollRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_group_slot(self, *, group_id: int, scheduled_for: datetime) -> GroupDiseaseRoll | None:
        stmt = select(GroupDiseaseRoll).where(
            GroupDiseaseRoll.group_id == group_id,
            GroupDiseaseRoll.scheduled_for == scheduled_for,
        )
        return await self._session.scalar(stmt)

    async def create(
        self,
        *,
        group_id: int,
        scheduled_for: datetime,
        status: DiseaseRollStatus,
        pig_id: UUID | None = None,
        disease_code: str | None = None,
        narrative_text: str | None = None,
        llm_model: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> GroupDiseaseRoll:
        roll = GroupDiseaseRoll(
            group_id=group_id,
            pig_id=pig_id,
            scheduled_for=scheduled_for,
            status=status,
            disease_code=disease_code,
            narrative_text=narrative_text,
            llm_model=llm_model,
            payload=payload,
        )
        self._session.add(roll)
        await self._session.flush()
        return roll

    async def list_recent_triggered_pig_ids(self, *, group_id: int, since: datetime) -> list[UUID]:
        stmt = (
            select(GroupDiseaseRoll.pig_id)
            .where(
                GroupDiseaseRoll.group_id == group_id,
                GroupDiseaseRoll.status == DiseaseRollStatus.TRIGGERED,
                GroupDiseaseRoll.pig_id.is_not(None),
                GroupDiseaseRoll.created_at >= since,
            )
            .distinct()
        )
        result = await self._session.scalars(stmt)
        return [pig_id for pig_id in result.all() if pig_id is not None]

    async def set_narrative(self, roll: GroupDiseaseRoll, *, narrative_text: str, llm_model: str | None) -> None:
        roll.narrative_text = narrative_text
        roll.llm_model = llm_model
