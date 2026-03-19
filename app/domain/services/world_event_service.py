from __future__ import annotations

import random
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db.repositories.world_event_repo import WorldEventRepository
from app.domain.feature_catalog import get_world_event_definition, pick_next_world_event
from app.domain.rules.timezones import format_datetime_msk
from app.schemas.pig import WorldEventView


class WorldEventService:
    def __init__(self, session: AsyncSession, *, settings: Settings, rng: random.Random) -> None:
        self._session = session
        self._settings = settings
        self._rng = rng
        self._world_events = WorldEventRepository(session)

    async def ensure_active_event(self, *, now: datetime):
        active = await self._world_events.get_active(now=now)
        if active is not None:
            return active

        latest = await self._world_events.get_latest()
        definition = pick_next_world_event(rng=self._rng, previous_code=latest.event_code if latest else None)
        return await self._world_events.create(
            event_code=definition.code,
            title=definition.title,
            description=definition.description,
            starts_at=now,
            ends_at=now + self._settings.world_event_duration,
            modifiers={"code": definition.code},
        )

    async def get_current_view(self, *, now: datetime) -> WorldEventView:
        event = await self.ensure_active_event(now=now)
        definition = get_world_event_definition(event.event_code)
        return WorldEventView(
            title=event.title,
            description=event.description,
            ends_at=event.ends_at,
            effects=self._format_effects(definition),
        )

    async def list_unannounced_active(self, *, now: datetime):
        return await self._world_events.list_unannounced_active(now=now)

    def build_announcement(self, event) -> str:
        definition = get_world_event_definition(event.event_code)
        lines = [f"🌍 Мировое событие: {event.title}", event.description, ""]
        lines.extend(f"• {effect}" for effect in self._format_effects(definition))
        lines.append(f"До конца: {format_datetime_msk(event.ends_at)}")
        return "\n".join(lines)

    def _format_effects(self, definition) -> list[str]:
        effects: list[str] = []
        if definition.feed_modifier != 0:
            effects.append(
                "кормление "
                + ("сильнее" if definition.feed_modifier > 0 else "слабее")
                + f" на {abs(int(definition.feed_modifier * 100))}%"
            )
        if definition.battle_reward_modifier != 0:
            effects.append(f"победители боёв получают на {int(definition.battle_reward_modifier * 100)}% больше веса")
        if definition.sabotage_modifier != 0:
            effects.append(
                "диверсии "
                + ("проходят чаще" if definition.sabotage_modifier > 0 else "работают хуже")
            )
        if definition.raid_modifier != 0:
            effects.append("рейды в среднем меняются по удаче")
        if definition.raid_item_modifier != 0:
            effects.append("в рейдах чаще падают полезные предметы")
        if definition.raid_bad_outcome_modifier != 0:
            effects.append("плохие исходы рейдов случаются реже")
        if definition.destination_raid_modifiers:
            effects.append("часть направлений рейдов получила отдельный бонус")
        return effects
