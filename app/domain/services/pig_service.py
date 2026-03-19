from __future__ import annotations

import random
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories.event_repo import PigEventRepository
from app.db.repositories.group_repo import GroupRepository
from app.db.repositories.pig_repo import PigRepository
from app.db.repositories.user_repo import UserRepository
from app.domain.feature_catalog import random_trait
from app.domain.exceptions import InvalidPigNameError, PigAlreadyExistsError, PigNotFoundError
from app.domain.models.pig import PigCooldowns, PigSnapshot
from app.domain.rules.combat import STARTING_PIG_WEIGHT
from app.domain.rules.cooldowns import get_remaining_cooldown
from app.domain.services.daily_feature_service import DailyFeatureService
from app.domain.services.pig_modifier_resolver import PigModifierResolver
from app.schemas.pig import PigProfile, RenamePigResult


class PigService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        feed_cooldown,
        battle_cooldown,
        sabotage_cooldown,
        raid_cooldown,
        rng: random.Random | None = None,
    ) -> None:
        self._session = session
        self._groups = GroupRepository(session)
        self._users = UserRepository(session)
        self._pigs = PigRepository(session)
        self._events = PigEventRepository(session)
        self._rng = rng or random.Random()
        self._resolver = PigModifierResolver(session)
        self._daily = DailyFeatureService(session, rng=self._rng)
        self._feed_cooldown = feed_cooldown
        self._battle_cooldown = battle_cooldown
        self._sabotage_cooldown = sabotage_cooldown
        self._raid_cooldown = raid_cooldown

    async def create_pig(
        self,
        *,
        telegram_group_id: int,
        group_title: str,
        telegram_user_id: int,
        username: str | None,
        first_name: str,
        last_name: str | None,
        pig_name: str,
        now: datetime,
    ) -> PigProfile:
        normalized_name = self._normalize_name(pig_name)

        async with self._session.begin():
            group = await self._groups.get_or_create(telegram_group_id, group_title)
            user = await self._users.get_or_create(
                telegram_user_id,
                username=username,
                first_name=first_name,
                last_name=last_name,
            )
            existing = await self._pigs.get_by_group_owner(group_id=group.id, owner_user_id=user.id)
            if existing is not None:
                raise PigAlreadyExistsError

            trait = random_trait(self._rng)
            pig = await self._pigs.create(
                group_id=group.id,
                owner_user_id=user.id,
                name=normalized_name,
                weight_kg=STARTING_PIG_WEIGHT,
                trait=trait,
            )
            await self._events.create(
                pig_id=pig.id,
                group_id=group.id,
                event_type="pig_created",
                payload={"name": pig.name, "weight_kg": str(pig.weight_kg), "trait": pig.trait.value},
            )
            await self._events.create(
                pig_id=pig.id,
                group_id=group.id,
                event_type="trait_assigned",
                payload={"trait": pig.trait.value},
            )
            profile = await self._to_profile(pig, now=now)

        return profile

    async def get_pig_profile(
        self,
        *,
        telegram_group_id: int,
        telegram_user_id: int,
        now: datetime,
    ) -> PigProfile:
        async with self._session.begin():
            pig = await self._get_locked_pig_for_owner(
                telegram_group_id=telegram_group_id,
                telegram_user_id=telegram_user_id,
            )
            await self._daily.ensure_horoscope_for_pig(pig, now=now)
            return await self._to_profile(pig, now=now)

    async def rename_pig(
        self,
        *,
        telegram_group_id: int,
        telegram_user_id: int,
        new_name: str,
        now: datetime,
    ) -> RenamePigResult:
        normalized_name = self._normalize_name(new_name)

        async with self._session.begin():
            pig = await self._get_locked_pig_for_owner(
                telegram_group_id=telegram_group_id,
                telegram_user_id=telegram_user_id,
            )
            old_name = pig.name
            changed = normalized_name != old_name
            if changed:
                pig.name = normalized_name
                await self._events.create(
                    pig_id=pig.id,
                    group_id=pig.group_id,
                    event_type="pig_renamed",
                    payload={"old_name": old_name, "new_name": normalized_name, "renamed_at": now.isoformat()},
                )

        return RenamePigResult(old_name=old_name, new_name=normalized_name, changed=changed)

    def _normalize_name(self, pig_name: str) -> str:
        normalized = " ".join(pig_name.split()).strip()
        if not 3 <= len(normalized) <= 40:
            raise InvalidPigNameError
        return normalized

    async def _to_profile(self, pig, *, now: datetime) -> PigProfile:
        snapshot = PigSnapshot(
            id=pig.id,
            name=pig.name,
            weight_kg=pig.weight_kg,
            status=pig.status,
            trait=pig.trait,
            mood_score=pig.mood_score,
            loyalty=pig.loyalty,
            wins=pig.wins,
            losses=pig.losses,
            last_feed_at=pig.last_feed_at,
            last_battle_at=pig.last_battle_at,
            last_sabotage_at=pig.last_sabotage_at,
            last_raid_at=pig.last_raid_at,
            battle_ready_until=pig.battle_ready_until,
            raid_until=pig.raid_until,
        )
        cooldowns = PigCooldowns(
            next_feed_in=get_remaining_cooldown(snapshot.last_feed_at, self._feed_cooldown, now),
            next_battle_in=get_remaining_cooldown(snapshot.last_battle_at, self._battle_cooldown, now),
            next_sabotage_in=get_remaining_cooldown(snapshot.last_sabotage_at, self._sabotage_cooldown, now),
            next_raid_in=get_remaining_cooldown(snapshot.last_raid_at, self._raid_cooldown, now),
        )
        resolved = await self._resolver.resolve_profile_state(pig, now=now)
        return PigProfile(
            pig_id=snapshot.id,
            name=snapshot.name,
            weight_kg=snapshot.weight_kg,
            status=snapshot.status,
            trait_title=resolved.trait_title,
            trait_summary=resolved.trait_summary,
            mood_score=resolved.mood_score,
            mood_label=resolved.mood_label,
            loyalty=snapshot.loyalty,
            loyalty_label=resolved.loyalty_label,
            wins=snapshot.wins,
            losses=snapshot.losses,
            next_feed_in=cooldowns.next_feed_in,
            next_battle_in=cooldowns.next_battle_in,
            next_sabotage_in=cooldowns.next_sabotage_in,
            next_raid_in=cooldowns.next_raid_in,
            battle_ready_until=snapshot.battle_ready_until,
            raid_until=snapshot.raid_until,
            equipped_item=resolved.equipped_item,
            active_effects=resolved.active_effects,
            world_event_title=resolved.world_event_title,
            world_event_description=resolved.world_event_description,
        )

    async def _get_locked_pig_for_owner(self, *, telegram_group_id: int, telegram_user_id: int):
        group = await self._groups.get_by_telegram_id(telegram_group_id)
        user = await self._users.get_by_telegram_id(telegram_user_id)
        if group is None or user is None:
            raise PigNotFoundError

        pig = await self._pigs.get_by_group_owner_for_update(group_id=group.id, owner_user_id=user.id)
        if pig is None:
            raise PigNotFoundError
        return pig
