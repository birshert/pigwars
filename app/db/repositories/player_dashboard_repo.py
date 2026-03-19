from __future__ import annotations

from typing import Any

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Pig, PigEvent, TelegramGroup, TelegramUser


class PlayerDashboardRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_recent_events_for_owner(
        self,
        *,
        telegram_user_id: int,
        limit: int = 12,
    ) -> list[dict[str, Any]]:
        stmt = (
            select(PigEvent, Pig.name, TelegramGroup.title)
            .join(Pig, PigEvent.pig_id == Pig.id)
            .join(TelegramUser, Pig.owner_user_id == TelegramUser.id)
            .join(TelegramGroup, Pig.group_id == TelegramGroup.id)
            .where(TelegramUser.telegram_user_id == telegram_user_id)
            .order_by(PigEvent.created_at.desc(), PigEvent.id.desc())
            .limit(limit)
        )
        rows = list((await self._session.execute(stmt)).all())
        return [
            {
                "event_type": event.event_type,
                "pig_name": pig_name,
                "group_title": group_title,
                "created_at": event.created_at.isoformat(),
            }
            for event, pig_name, group_title in rows
        ]

    async def get_summary(self, *, telegram_user_id: int) -> dict[str, int | str | None]:
        stmt = (
            select(
                func.count(Pig.id),
                func.coalesce(func.sum(Pig.weight_kg), 0),
                func.coalesce(func.sum(Pig.wins), 0),
                func.coalesce(func.sum(Pig.losses), 0),
            )
            .select_from(Pig)
            .join(TelegramUser, Pig.owner_user_id == TelegramUser.id)
            .where(TelegramUser.telegram_user_id == telegram_user_id)
        )
        pig_count, total_weight, total_wins, total_losses = (await self._session.execute(stmt)).one()

        latest_group_stmt = (
            select(TelegramGroup.title)
            .join(Pig, Pig.group_id == TelegramGroup.id)
            .join(TelegramUser, Pig.owner_user_id == TelegramUser.id)
            .where(TelegramUser.telegram_user_id == telegram_user_id)
            .order_by(desc(Pig.updated_at), desc(Pig.created_at))
            .limit(1)
        )
        latest_group_title = await self._session.scalar(latest_group_stmt)

        return {
            "pig_count": int(pig_count or 0),
            "total_weight_kg": f"{total_weight:.2f}" if total_weight is not None else "0.00",
            "total_wins": int(total_wins or 0),
            "total_losses": int(total_losses or 0),
            "latest_group_title": latest_group_title,
        }
