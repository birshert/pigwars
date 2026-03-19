from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import TelegramUser


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, user_id: int) -> TelegramUser | None:
        stmt = select(TelegramUser).where(TelegramUser.id == user_id)
        return await self._session.scalar(stmt)

    async def get_by_telegram_id(self, telegram_user_id: int) -> TelegramUser | None:
        stmt = select(TelegramUser).where(TelegramUser.telegram_user_id == telegram_user_id)
        return await self._session.scalar(stmt)

    async def get_or_create(
        self,
        telegram_user_id: int,
        *,
        username: str | None,
        first_name: str,
        last_name: str | None,
    ) -> TelegramUser:
        user = await self.get_by_telegram_id(telegram_user_id)
        if user is not None:
            user.username = username
            user.first_name = first_name
            user.last_name = last_name
            return user

        user = TelegramUser(
            telegram_user_id=telegram_user_id,
            username=username,
            first_name=first_name,
            last_name=last_name,
        )
        self._session.add(user)
        await self._session.flush()
        return user
