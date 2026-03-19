from __future__ import annotations

import random
from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories.battle_repo import BattleRepository
from app.db.repositories.effect_repo import PigEffectRepository
from app.db.repositories.event_repo import PigEventRepository
from app.db.repositories.group_repo import GroupRepository
from app.db.repositories.pig_repo import PigRepository
from app.db.repositories.user_repo import UserRepository
from app.domain.exceptions import BattleCooldownError, ConcurrentActionError, PigBusyError, PigNotFoundError
from app.domain.feature_catalog import get_item_definition, get_trait_definition
from app.domain.models.pig import PigStatus
from app.domain.rules.combat import pig_can_enter_battle, resolve_battle
from app.domain.rules.cooldowns import ensure_utc, get_remaining_cooldown
from app.domain.rules.pig_state import apply_loyalty_change, apply_mood_change
from app.domain.services.item_service import ItemService
from app.domain.services.pig_modifier_resolver import PigModifierResolver
from app.infra.locks import RedisLockManager
from app.schemas.battle import BattleMessagePayload
from app.schemas.pig import BattleEntryResult


class BattleQueueService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        battle_cooldown,
        battle_ready_ttl,
        lock_manager: RedisLockManager,
    ) -> None:
        self._session = session
        self._groups = GroupRepository(session)
        self._users = UserRepository(session)
        self._pigs = PigRepository(session)
        self._events = PigEventRepository(session)
        self._battle_cooldown = battle_cooldown
        self._battle_ready_ttl = battle_ready_ttl
        self._lock_manager = lock_manager

    async def enter_battle_mode(
        self,
        *,
        telegram_group_id: int,
        telegram_user_id: int,
        now: datetime,
    ) -> BattleEntryResult:
        lease = await self._lock_manager.acquire(f"battle:{telegram_group_id}:{telegram_user_id}", ttl_seconds=10)
        if not lease.acquired:
            raise ConcurrentActionError

        try:
            async with self._session.begin():
                pig = await self._get_locked_pig(telegram_group_id=telegram_group_id, telegram_user_id=telegram_user_id)

                if not pig_can_enter_battle(pig.status, pig.battle_ready_until, now):
                    raise PigBusyError

                remaining = get_remaining_cooldown(pig.last_battle_at, self._battle_cooldown, now)
                if remaining.total_seconds() > 0:
                    raise BattleCooldownError(remaining=remaining)

                pig.status = PigStatus.BATTLE_READY
                pig.last_battle_at = now
                pig.battle_ready_until = now + self._battle_ready_ttl

                await self._events.create(
                    pig_id=pig.id,
                    group_id=pig.group_id,
                    event_type="battle_ready",
                    payload={"ready_until": pig.battle_ready_until.isoformat()},
                )
        finally:
            await lease.release()

        return BattleEntryResult(
            pig_name=pig.name,
            ready_until=pig.battle_ready_until,
            next_battle_in=self._battle_cooldown,
        )

    async def _get_locked_pig(self, *, telegram_group_id: int, telegram_user_id: int):
        group = await self._groups.get_by_telegram_id(telegram_group_id)
        user = await self._users.get_by_telegram_id(telegram_user_id)
        if group is None or user is None:
            raise PigNotFoundError

        pig = await self._pigs.get_by_group_owner_for_update(group_id=group.id, owner_user_id=user.id)
        if pig is None:
            raise PigNotFoundError
        return pig


class BattleService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        rng: random.Random,
        lock_manager: RedisLockManager,
    ) -> None:
        self._session = session
        self._pigs = PigRepository(session)
        self._groups = GroupRepository(session)
        self._battles = BattleRepository(session)
        self._events = PigEventRepository(session)
        self._effects = PigEffectRepository(session)
        self._resolver = PigModifierResolver(session)
        self._items = ItemService(session, rng=rng)
        self._rng = rng
        self._lock_manager = lock_manager

    async def resolve_pair(
        self,
        *,
        group_id: int,
        pig1_id: UUID,
        pig2_id: UUID,
        now: datetime,
    ) -> BattleMessagePayload | None:
        sorted_ids = sorted((str(pig1_id), str(pig2_id)))
        lease = await self._lock_manager.acquire(f"fight:{sorted_ids[0]}:{sorted_ids[1]}", ttl_seconds=30)
        if not lease.acquired:
            return None

        try:
            async with self._session.begin():
                pigs = await self._pigs.get_by_ids_for_update([pig1_id, pig2_id])
                if len(pigs) != 2:
                    return None

                pig_map = {pig.id: pig for pig in pigs}
                pig1 = pig_map[pig1_id]
                pig2 = pig_map[pig2_id]

                if pig1.group_id != group_id or pig2.group_id != group_id:
                    return None
                if not self._is_ready(pig1, now) or not self._is_ready(pig2, now):
                    return None

                pig1_weight_before = pig1.weight_kg
                pig2_weight_before = pig2.weight_kg
                pig1_state = await self._resolver.resolve_combat_state(pig1, now=now)
                pig2_state = await self._resolver.resolve_combat_state(pig2, now=now)
                pig1.status = PigStatus.IN_BATTLE
                pig2.status = PigStatus.IN_BATTLE

                result = resolve_battle(
                    pig1,
                    pig2,
                    rng=self._rng,
                    now=now,
                    pig1_modifier=pig1_state.modifier,
                    pig2_modifier=pig2_state.modifier,
                    winner_reward_modifier=max(pig1_state.reward_modifier, pig2_state.reward_modifier),
                )
                winner = pig_map[result.winner.pig_id]
                loser = pig_map[result.loser.pig_id]
                winner_state = pig1_state if winner.id == pig1.id else pig2_state
                loser_state = pig2_state if loser.id == pig2.id else pig1_state

                winner.weight_kg += result.winner_gain
                winner.wins += 1
                winner.status = PigStatus.IDLE
                winner.battle_ready_until = None

                loser.weight_kg -= result.loser_loss
                loser.losses += 1
                loser.status = PigStatus.IDLE
                loser.battle_ready_until = None
                winner_mood_delta = apply_mood_change(winner, delta=10)
                loser_mood_delta = apply_mood_change(
                    loser,
                    delta=-8 + get_trait_definition(loser.trait).battle_loss_mood_delta,
                )
                winner_loyalty_delta = apply_loyalty_change(winner, delta=2)
                loser_loyalty_delta = apply_loyalty_change(loser, delta=-1)
                for effect in winner_state.one_shot_effects + loser_state.one_shot_effects:
                    await self._effects.consume(effect, now=now)
                winner_broken_item = await self._wear_combat_item(winner_state.equipped_item, now=now)
                loser_broken_item = await self._wear_combat_item(loser_state.equipped_item, now=now)

                battle = await self._battles.create(
                    group_id=group_id,
                    pig1_id=pig1.id,
                    pig2_id=pig2.id,
                    winner_pig_id=winner.id,
                    loser_pig_id=loser.id,
                    pig1_score=result.winner.combat_score if result.winner.pig_id == pig1.id else result.loser.combat_score,
                    pig2_score=result.winner.combat_score if result.winner.pig_id == pig2.id else result.loser.combat_score,
                    weight_delta_winner=result.winner_gain,
                    weight_delta_loser=result.loser_loss,
                )
                loot = None
                if self._rng.random() < 0.15:
                    loot = await self._items.award_random_item(
                        pig=winner,
                        source_key="battle",
                        now=now,
                        source_type="battle",
                        source_id=str(battle.id),
                    )

                await self._events.create(
                    pig_id=winner.id,
                    group_id=group_id,
                    event_type="battle_won",
                    payload={
                        "opponent_id": str(loser.id),
                        "weight_gain": str(result.winner_gain),
                        "loot": loot.title if loot is not None else None,
                    },
                )
                await self._events.create(
                    pig_id=loser.id,
                    group_id=group_id,
                    event_type="battle_lost",
                    payload={"opponent_id": str(winner.id), "weight_loss": str(result.loser_loss)},
                )
                if winner_mood_delta != 0:
                    await self._events.create(
                        pig_id=winner.id,
                        group_id=group_id,
                        event_type="mood_changed",
                        payload={"delta": winner_mood_delta, "mood_score": winner.mood_score},
                    )
                if loser_mood_delta != 0:
                    await self._events.create(
                        pig_id=loser.id,
                        group_id=group_id,
                        event_type="mood_changed",
                        payload={"delta": loser_mood_delta, "mood_score": loser.mood_score},
                    )
                if winner_loyalty_delta != 0:
                    await self._events.create(
                        pig_id=winner.id,
                        group_id=group_id,
                        event_type="loyalty_changed",
                        payload={"delta": winner_loyalty_delta, "loyalty": winner.loyalty},
                    )
                if loser_loyalty_delta != 0:
                    await self._events.create(
                        pig_id=loser.id,
                        group_id=group_id,
                        event_type="loyalty_changed",
                        payload={"delta": loser_loyalty_delta, "loyalty": loser.loyalty},
                    )

                group = await self._groups.get_by_id(group_id)
                if group is None:
                    return None
        finally:
            await lease.release()

        return BattleMessagePayload(
            telegram_group_id=group.telegram_group_id,
            pig1_name=pig1.name,
            pig1_weight=pig1_weight_before,
            pig2_name=pig2.name,
            pig2_weight=pig2_weight_before,
            winner_name=winner.name,
            loser_name=loser.name,
            winner_gain=result.winner_gain,
            loser_loss=result.loser_loss,
            winner_trait_title=get_trait_definition(winner.trait).title,
            loser_trait_title=get_trait_definition(loser.trait).title,
            winner_loot_title=loot.title if loot is not None else None,
            broken_item_title=winner_broken_item or loser_broken_item,
        )

    def _is_ready(self, pig, now: datetime) -> bool:
        ready_until = ensure_utc(pig.battle_ready_until)
        normalized_now = ensure_utc(now) or now
        return (
            pig.status == PigStatus.BATTLE_READY
            and ready_until is not None
            and ready_until > normalized_now
        )

    async def _wear_combat_item(self, item, *, now: datetime) -> str | None:
        if item is None:
            return None
        if get_item_definition(item.item_code).combat_modifier <= 0:
            return None
        return await self._items.wear_item(item, now=now)
