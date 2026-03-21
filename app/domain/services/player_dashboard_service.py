from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories.item_repo import PigItemRepository
from app.db.repositories.pig_repo import PigRepository
from app.db.repositories.player_dashboard_repo import PlayerDashboardRepository
from app.domain.rules.cooldowns import get_remaining_cooldown
from app.domain.services.pig_modifier_resolver import PigModifierResolver
from app.schemas.pig import PigProfile


@dataclass(slots=True)
class PlayerPigDashboard:
    group_title: str
    group_telegram_id: int
    profile: PigProfile
    inventory_count: int


class PlayerDashboardService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        feed_cooldown,
        battle_cooldown,
        sabotage_cooldown,
        raid_cooldown,
    ) -> None:
        self._session = session
        self._pigs = PigRepository(session)
        self._items = PigItemRepository(session)
        self._resolver = PigModifierResolver(session)
        self._dashboard = PlayerDashboardRepository(session)
        self._feed_cooldown = feed_cooldown
        self._battle_cooldown = battle_cooldown
        self._sabotage_cooldown = sabotage_cooldown
        self._raid_cooldown = raid_cooldown

    async def build_dashboard(self, *, telegram_user_id: int, now: datetime) -> dict[str, object]:
        pigs = await self._pigs.list_by_owner_telegram_id(telegram_user_id=telegram_user_id)
        pig_dashboards = [
            await self._build_pig_dashboard(pig, now=now)
            for pig in pigs
        ]
        summary = await self._dashboard.get_summary(telegram_user_id=telegram_user_id)
        recent_events = await self._dashboard.list_recent_events_for_owner(
            telegram_user_id=telegram_user_id,
        )
        return {
            "summary": summary,
            "pigs": [self._serialize_pig_dashboard(item) for item in pig_dashboards],
            "recent_events": recent_events,
        }

    async def _build_pig_dashboard(self, pig, *, now: datetime) -> PlayerPigDashboard:
        resolved = await self._resolver.resolve_profile_state(pig, now=now)
        inventory_count = await self._items.count_inventory(pig_id=pig.id, now=now)
        profile = PigProfile(
            pig_id=pig.id,
            name=pig.name,
            weight_kg=pig.weight_kg,
            status=pig.status,
            trait_title=resolved.trait_title,
            trait_summary=resolved.trait_summary,
            mood_score=resolved.mood_score,
            mood_label=resolved.mood_label,
            loyalty=pig.loyalty,
            loyalty_label=resolved.loyalty_label,
            wins=pig.wins,
            losses=pig.losses,
            next_feed_in=get_remaining_cooldown(pig.last_feed_at, self._feed_cooldown, now),
            next_battle_in=get_remaining_cooldown(pig.last_battle_at, self._battle_cooldown, now),
            next_sabotage_in=get_remaining_cooldown(pig.last_sabotage_at, self._sabotage_cooldown, now),
            next_raid_in=get_remaining_cooldown(pig.last_raid_at, self._raid_cooldown, now),
            battle_ready_until=pig.battle_ready_until,
            raid_until=pig.raid_until,
            quarantine_until=pig.quarantine_until,
            equipped_item=resolved.equipped_item,
            active_effects=resolved.active_effects,
            world_event_title=resolved.world_event_title,
            world_event_description=resolved.world_event_description,
        )
        return PlayerPigDashboard(
            group_title=pig.group.title,
            group_telegram_id=pig.group.telegram_group_id,
            profile=profile,
            inventory_count=inventory_count,
        )

    def _serialize_pig_dashboard(self, item: PlayerPigDashboard) -> dict[str, object]:
        profile = item.profile
        return {
            "group_title": item.group_title,
            "group_telegram_id": item.group_telegram_id,
            "profile": {
                "pig_id": str(profile.pig_id),
                "name": profile.name,
                "weight_kg": self._serialize_decimal(profile.weight_kg),
                "status": profile.status.value,
                "trait_title": profile.trait_title,
                "trait_summary": profile.trait_summary,
                "mood_score": profile.mood_score,
                "mood_label": profile.mood_label,
                "loyalty": profile.loyalty,
                "loyalty_label": profile.loyalty_label,
                "wins": profile.wins,
                "losses": profile.losses,
                "next_feed_in_seconds": int(profile.next_feed_in.total_seconds()),
                "next_battle_in_seconds": int(profile.next_battle_in.total_seconds()),
                "next_sabotage_in_seconds": int(profile.next_sabotage_in.total_seconds()),
                "next_raid_in_seconds": int(profile.next_raid_in.total_seconds()),
                "battle_ready_until": profile.battle_ready_until.isoformat() if profile.battle_ready_until else None,
                "raid_until": profile.raid_until.isoformat() if profile.raid_until else None,
                "quarantine_until": profile.quarantine_until.isoformat() if profile.quarantine_until else None,
                "equipped_item": (
                    {
                        "title": profile.equipped_item.title,
                        "summary": profile.equipped_item.summary,
                    }
                    if profile.equipped_item is not None
                    else None
                ),
                "active_effects": [
                    {
                        "title": effect.title,
                        "summary": effect.summary,
                        "expires_at": effect.expires_at.isoformat() if effect.expires_at else None,
                    }
                    for effect in profile.active_effects
                ],
                "world_event_title": profile.world_event_title,
                "world_event_description": profile.world_event_description,
            },
            "inventory_count": item.inventory_count,
        }

    @staticmethod
    def _serialize_decimal(value: Decimal) -> str:
        return f"{value:.2f}"
