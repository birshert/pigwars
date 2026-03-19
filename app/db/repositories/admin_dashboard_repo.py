from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import case, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.db.models import Battle, Pig, PigEvent, PigRaid, TelegramGroup, TelegramUser, WorldEvent
from app.domain.models.pig import PigRaidStatus, PigStatus


class AdminDashboardRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_overview(self, *, now: datetime) -> dict[str, int]:
        return {
            "groups": await self._count(TelegramGroup.id, TelegramGroup),
            "users": await self._count(TelegramUser.id, TelegramUser),
            "pigs": await self._count(Pig.id, Pig),
            "battles": await self._count(Battle.id, Battle),
            "raids": await self._count(PigRaid.id, PigRaid),
            "battle_ready_pigs": await self._count(
                Pig.id,
                Pig,
                Pig.status == PigStatus.BATTLE_READY,
                Pig.battle_ready_until.is_not(None),
                Pig.battle_ready_until > now,
            ),
            "active_raids": await self._count(
                PigRaid.id,
                PigRaid,
                PigRaid.status == PigRaidStatus.ACTIVE,
                PigRaid.resolve_at > now,
            ),
            "active_world_events": await self._count(
                WorldEvent.id,
                WorldEvent,
                WorldEvent.starts_at <= now,
                WorldEvent.ends_at >= now,
            ),
        }

    async def list_active_world_events(self, *, now: datetime, limit: int = 4) -> list[dict[str, Any]]:
        stmt = (
            select(WorldEvent)
            .where(WorldEvent.starts_at <= now, WorldEvent.ends_at >= now)
            .order_by(WorldEvent.ends_at.asc(), WorldEvent.id.desc())
            .limit(limit)
        )
        events = list((await self._session.scalars(stmt)).all())
        return [
            {
                "title": event.title,
                "description": event.description,
                "event_code": event.event_code,
                "starts_at": self._serialize_datetime(event.starts_at),
                "ends_at": self._serialize_datetime(event.ends_at),
            }
            for event in events
        ]

    async def list_top_pigs(self, *, limit: int = 8) -> list[dict[str, Any]]:
        stmt = (
            select(Pig, TelegramUser, TelegramGroup)
            .join(TelegramUser, Pig.owner_user_id == TelegramUser.id)
            .join(TelegramGroup, Pig.group_id == TelegramGroup.id)
            .order_by(desc(Pig.weight_kg), desc(Pig.wins), Pig.name.asc())
            .limit(limit)
        )
        rows = list((await self._session.execute(stmt)).all())
        return [
            {
                "pig_name": pig.name,
                "weight_kg": self._serialize_decimal(pig.weight_kg),
                "trait": pig.trait.value,
                "status": pig.status.value,
                "wins": pig.wins,
                "losses": pig.losses,
                "owner_name": self._format_owner_label(owner),
                "group_title": group.title,
                "group_telegram_id": group.telegram_group_id,
            }
            for pig, owner, group in rows
        ]

    async def list_group_summaries(self, *, limit: int = 12) -> list[dict[str, Any]]:
        pig_stats = (
            select(
                Pig.group_id.label("group_id"),
                func.count(Pig.id).label("pig_count"),
                func.avg(Pig.weight_kg).label("avg_weight"),
                func.sum(case((Pig.status == PigStatus.BATTLE_READY, 1), else_=0)).label("ready_count"),
                func.sum(case((Pig.status == PigStatus.ON_RAID, 1), else_=0)).label("raiding_count"),
                func.max(Pig.updated_at).label("last_pig_update_at"),
            )
            .group_by(Pig.group_id)
            .subquery()
        )
        battle_stats = (
            select(
                Battle.group_id.label("group_id"),
                func.count(Battle.id).label("battle_count"),
                func.max(Battle.created_at).label("last_battle_at"),
            )
            .group_by(Battle.group_id)
            .subquery()
        )
        event_stats = (
            select(
                PigEvent.group_id.label("group_id"),
                func.count(PigEvent.id).label("event_count"),
                func.max(PigEvent.created_at).label("last_event_at"),
            )
            .group_by(PigEvent.group_id)
            .subquery()
        )
        top_pig_name = (
            select(Pig.name)
            .where(Pig.group_id == TelegramGroup.id)
            .order_by(desc(Pig.weight_kg), desc(Pig.wins), Pig.name.asc())
            .limit(1)
            .scalar_subquery()
        )
        top_pig_weight = (
            select(Pig.weight_kg)
            .where(Pig.group_id == TelegramGroup.id)
            .order_by(desc(Pig.weight_kg), desc(Pig.wins), Pig.name.asc())
            .limit(1)
            .scalar_subquery()
        )
        stmt = (
            select(
                TelegramGroup,
                func.coalesce(pig_stats.c.pig_count, 0),
                pig_stats.c.avg_weight,
                func.coalesce(pig_stats.c.ready_count, 0),
                func.coalesce(pig_stats.c.raiding_count, 0),
                pig_stats.c.last_pig_update_at,
                func.coalesce(battle_stats.c.battle_count, 0),
                battle_stats.c.last_battle_at,
                func.coalesce(event_stats.c.event_count, 0),
                event_stats.c.last_event_at,
                top_pig_name,
                top_pig_weight,
            )
            .outerjoin(pig_stats, pig_stats.c.group_id == TelegramGroup.id)
            .outerjoin(battle_stats, battle_stats.c.group_id == TelegramGroup.id)
            .outerjoin(event_stats, event_stats.c.group_id == TelegramGroup.id)
            .order_by(
                desc(func.coalesce(pig_stats.c.pig_count, 0)),
                desc(func.coalesce(battle_stats.c.battle_count, 0)),
                TelegramGroup.title.asc(),
            )
            .limit(limit)
        )
        rows = list((await self._session.execute(stmt)).all())
        return [
            {
                "title": group.title,
                "telegram_group_id": group.telegram_group_id,
                "pig_count": pig_count,
                "avg_weight_kg": self._serialize_decimal(avg_weight),
                "ready_count": ready_count,
                "raiding_count": raiding_count,
                "battle_count": battle_count,
                "event_count": event_count,
                "top_pig_name": top_name,
                "top_pig_weight_kg": self._serialize_decimal(top_weight),
                "last_activity_at": self._serialize_datetime(
                    self._latest_datetime(last_pig_update_at, last_battle_at, last_event_at)
                ),
            }
            for (
                group,
                pig_count,
                avg_weight,
                ready_count,
                raiding_count,
                last_pig_update_at,
                battle_count,
                last_battle_at,
                event_count,
                last_event_at,
                top_name,
                top_weight,
            ) in rows
        ]

    async def list_recent_battles(self, *, limit: int = 8) -> list[dict[str, Any]]:
        pig1 = aliased(Pig)
        pig2 = aliased(Pig)
        winner = aliased(Pig)
        stmt = (
            select(
                Battle,
                TelegramGroup.title,
                pig1.name,
                pig2.name,
                winner.name,
            )
            .join(TelegramGroup, Battle.group_id == TelegramGroup.id)
            .join(pig1, Battle.pig1_id == pig1.id)
            .join(pig2, Battle.pig2_id == pig2.id)
            .outerjoin(winner, Battle.winner_pig_id == winner.id)
            .order_by(Battle.created_at.desc())
            .limit(limit)
        )
        rows = list((await self._session.execute(stmt)).all())
        return [
            {
                "group_title": group_title,
                "pig1_name": pig1_name,
                "pig2_name": pig2_name,
                "winner_name": winner_name,
                "created_at": self._serialize_datetime(battle.created_at),
                "winner_gain_kg": self._serialize_decimal(battle.weight_delta_winner),
                "loser_loss_kg": self._serialize_decimal(battle.weight_delta_loser),
            }
            for battle, group_title, pig1_name, pig2_name, winner_name in rows
        ]

    async def list_recent_raids(self, *, limit: int = 8) -> list[dict[str, Any]]:
        stmt = (
            select(PigRaid, Pig.name, TelegramGroup.title)
            .join(Pig, PigRaid.pig_id == Pig.id)
            .join(TelegramGroup, PigRaid.group_id == TelegramGroup.id)
            .order_by(PigRaid.created_at.desc())
            .limit(limit)
        )
        rows = list((await self._session.execute(stmt)).all())
        return [
            {
                "pig_name": pig_name,
                "group_title": group_title,
                "destination": raid.destination.value,
                "status": raid.status.value,
                "started_at": self._serialize_datetime(raid.started_at),
                "resolve_at": self._serialize_datetime(raid.resolve_at),
                "resolved_at": self._serialize_datetime(raid.resolved_at),
            }
            for raid, pig_name, group_title in rows
        ]

    async def list_recent_pig_events(self, *, limit: int = 10) -> list[dict[str, Any]]:
        stmt = (
            select(PigEvent, Pig.name, TelegramGroup.title)
            .join(Pig, PigEvent.pig_id == Pig.id)
            .join(TelegramGroup, PigEvent.group_id == TelegramGroup.id)
            .order_by(PigEvent.created_at.desc(), PigEvent.id.desc())
            .limit(limit)
        )
        rows = list((await self._session.execute(stmt)).all())
        return [
            {
                "event_type": event.event_type,
                "pig_name": pig_name,
                "group_title": group_title,
                "created_at": self._serialize_datetime(event.created_at),
            }
            for event, pig_name, group_title in rows
        ]

    async def _count(self, column: Any, model: Any, *conditions: Any) -> int:
        stmt = select(func.count(column)).select_from(model)
        if conditions:
            stmt = stmt.where(*conditions)
        value = await self._session.scalar(stmt)
        return int(value or 0)

    @staticmethod
    def _serialize_datetime(value: datetime | None) -> str | None:
        return value.isoformat() if value is not None else None

    @staticmethod
    def _serialize_decimal(value: Decimal | float | None) -> str | None:
        if value is None:
            return None
        decimal_value = value if isinstance(value, Decimal) else Decimal(str(value))
        return format(decimal_value.quantize(Decimal("0.01")), "f")

    @staticmethod
    def _latest_datetime(*values: datetime | None) -> datetime | None:
        candidates = [value for value in values if value is not None]
        return max(candidates) if candidates else None

    @staticmethod
    def _format_owner_label(owner: TelegramUser) -> str:
        if owner.username:
            return f"@{owner.username}"
        full_name = " ".join(part for part in [owner.first_name, owner.last_name] if part)
        return full_name or str(owner.telegram_user_id)
