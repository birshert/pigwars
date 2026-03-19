from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import PigItem
from app.domain.models.pig import PigItemType


class PigItemRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        pig_id: UUID,
        group_id: int,
        item_code: str,
        item_type: PigItemType,
        is_equipped: bool = False,
        durability: int | None = None,
        expires_at: datetime | None = None,
        payload: dict[str, Any] | None = None,
    ) -> PigItem:
        item = PigItem(
            pig_id=pig_id,
            group_id=group_id,
            item_code=item_code,
            item_type=item_type,
            is_equipped=is_equipped,
            durability=durability,
            expires_at=expires_at,
            payload=payload,
        )
        self._session.add(item)
        await self._session.flush()
        return item

    def _active_predicate(self, *, now: datetime):
        return and_(
            or_(PigItem.expires_at.is_(None), PigItem.expires_at > now),
            or_(PigItem.durability.is_(None), PigItem.durability > 0),
        )

    async def list_inventory(self, *, pig_id: UUID, now: datetime) -> list[PigItem]:
        stmt = (
            select(PigItem)
            .where(PigItem.pig_id == pig_id, self._active_predicate(now=now))
            .order_by(PigItem.is_equipped.desc(), PigItem.created_at.asc(), PigItem.id.asc())
        )
        result = await self._session.scalars(stmt)
        return list(result.all())

    async def count_inventory(self, *, pig_id: UUID, now: datetime) -> int:
        return len(await self.list_inventory(pig_id=pig_id, now=now))

    async def get_by_id_for_update(self, item_id: int) -> PigItem | None:
        stmt = select(PigItem).where(PigItem.id == item_id).with_for_update()
        return await self._session.scalar(stmt)

    async def get_equipped_item(self, *, pig_id: UUID, now: datetime) -> PigItem | None:
        stmt = (
            select(PigItem)
            .where(
                PigItem.pig_id == pig_id,
                PigItem.is_equipped.is_(True),
                self._active_predicate(now=now),
            )
            .order_by(PigItem.created_at.desc())
        )
        return await self._session.scalar(stmt)

    async def unequip_all(self, *, pig_id: UUID) -> None:
        items = await self.list_all_for_update(pig_id=pig_id)
        for item in items:
            item.is_equipped = False

    async def list_all_for_update(self, *, pig_id: UUID) -> list[PigItem]:
        stmt = select(PigItem).where(PigItem.pig_id == pig_id).with_for_update()
        result = await self._session.scalars(stmt)
        return list(result.all())
