from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import TelegramGroup


class GroupRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, group_id: int) -> TelegramGroup | None:
        stmt = select(TelegramGroup).where(TelegramGroup.id == group_id)
        return await self._session.scalar(stmt)

    async def get_by_telegram_id(self, telegram_group_id: int) -> TelegramGroup | None:
        stmt = select(TelegramGroup).where(TelegramGroup.telegram_group_id == telegram_group_id)
        return await self._session.scalar(stmt)

    async def get_or_create(self, telegram_group_id: int, title: str) -> TelegramGroup:
        group = await self.get_by_telegram_id(telegram_group_id)
        if group is not None:
            if group.title != title:
                group.title = title
            return group

        group = TelegramGroup(telegram_group_id=telegram_group_id, title=title)
        self._session.add(group)
        await self._session.flush()
        return group
