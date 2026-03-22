from __future__ import annotations

import random
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories.effect_repo import PigEffectRepository
from app.db.repositories.event_repo import PigEventRepository
from app.db.repositories.group_repo import GroupRepository
from app.db.repositories.item_repo import PigItemRepository
from app.db.repositories.pig_repo import PigRepository
from app.db.repositories.user_repo import UserRepository
from app.domain.feature_catalog import (
    EFFECT_RAID_BAD_LUCK_GUARD,
    EFFECT_SABOTAGE_GUARD,
    EFFECT_WET_NEWSPAPER_CURSE,
    ITEM_BOAR_HORSESHOES,
    ITEM_IRON_POT,
    ITEM_LUCKY_CHARM,
    ITEM_MUD_CLOAK,
    ITEM_STINKY_OINTMENT,
    ITEM_SUSPICIOUS_FEED,
    ITEM_WET_NEWSPAPER,
    get_item_definition,
)
from app.domain.exceptions import (
    ItemEquipError,
    ItemNotFoundError,
    ItemUseError,
    PigBusyError,
    PigNotFoundError,
    WetNewspaperBlockedError,
    WetNewspaperTargetError,
)
from app.domain.models.pig import PigItemType, PigStatus
from app.domain.rules.combat import quantize_weight
from app.domain.rules.pig_state import apply_mood_change
from app.schemas.pig import EquipResult, InventoryItemView, InventoryView, UseItemResult


RAID_ITEM_POOLS = {
    "dump": [ITEM_MUD_CLOAK, ITEM_STINKY_OINTMENT, ITEM_LUCKY_CHARM, ITEM_WET_NEWSPAPER],
    "market": [ITEM_SUSPICIOUS_FEED, ITEM_LUCKY_CHARM, ITEM_IRON_POT],
    "woods": [ITEM_BOAR_HORSESHOES, ITEM_IRON_POT, ITEM_LUCKY_CHARM],
    "mill": [ITEM_SUSPICIOUS_FEED, ITEM_BOAR_HORSESHOES, ITEM_LUCKY_CHARM],
    "pier": [ITEM_MUD_CLOAK, ITEM_WET_NEWSPAPER, ITEM_STINKY_OINTMENT, ITEM_LUCKY_CHARM],
    "manor": [ITEM_IRON_POT, ITEM_LUCKY_CHARM, ITEM_STINKY_OINTMENT, ITEM_SUSPICIOUS_FEED],
    "battle": [ITEM_IRON_POT, ITEM_SUSPICIOUS_FEED, ITEM_STINKY_OINTMENT],
    "world": [ITEM_LUCKY_CHARM, ITEM_STINKY_OINTMENT, ITEM_SUSPICIOUS_FEED, ITEM_WET_NEWSPAPER],
}


class ItemService:
    def __init__(self, session: AsyncSession, *, rng: random.Random) -> None:
        self._session = session
        self._groups = GroupRepository(session)
        self._users = UserRepository(session)
        self._pigs = PigRepository(session)
        self._items = PigItemRepository(session)
        self._effects = PigEffectRepository(session)
        self._events = PigEventRepository(session)
        self._rng = rng

    async def get_inventory(
        self,
        *,
        telegram_group_id: int,
        telegram_user_id: int,
        now: datetime,
    ) -> InventoryView:
        pig = await self._get_pig_for_owner(telegram_group_id=telegram_group_id, telegram_user_id=telegram_user_id)
        items = await self._items.list_inventory(pig_id=pig.id, now=now)
        return InventoryView(pig_name=pig.name, items=[self._to_view(item) for item in items])

    async def equip_item(
        self,
        *,
        telegram_group_id: int,
        telegram_user_id: int,
        slot: int,
        now: datetime,
    ) -> EquipResult:
        async with self._session.begin():
            pig = await self._get_locked_pig_for_owner(
                telegram_group_id=telegram_group_id,
                telegram_user_id=telegram_user_id,
            )
            if pig.status != PigStatus.IDLE:
                raise PigBusyError
            item = await self._get_inventory_item_by_slot(pig_id=pig.id, slot=slot, now=now)
            if item.item_type != PigItemType.EQUIPMENT:
                raise ItemEquipError

            await self._items.unequip_all(pig_id=pig.id)
            item.is_equipped = True
            definition = get_item_definition(item.item_code)
            await self._events.create(
                pig_id=pig.id,
                group_id=pig.group_id,
                event_type="item_equipped",
                payload={"item_code": item.item_code},
            )
        return EquipResult(pig_name=pig.name, item_title=definition.title)

    async def use_item(
        self,
        *,
        telegram_group_id: int,
        telegram_user_id: int,
        slot: int,
        target_telegram_user_id: int | None = None,
        now: datetime,
    ) -> UseItemResult:
        async with self._session.begin():
            pig = await self._get_locked_pig_for_owner(
                telegram_group_id=telegram_group_id,
                telegram_user_id=telegram_user_id,
            )
            item = await self._get_inventory_item_by_slot(pig_id=pig.id, slot=slot, now=now)
            definition = get_item_definition(item.item_code)
            if item.item_type != PigItemType.CONSUMABLE:
                raise ItemUseError

            outcome_text, mood_delta = await self._apply_consumable(
                pig,
                item=item,
                target_telegram_user_id=target_telegram_user_id,
                now=now,
            )
            await self._consume_item(item, now=now)
            await self._events.create(
                pig_id=pig.id,
                group_id=pig.group_id,
                event_type="item_used",
                payload={"item_code": item.item_code, "target_telegram_user_id": target_telegram_user_id},
            )
            if mood_delta != 0:
                await self._events.create(
                    pig_id=pig.id,
                    group_id=pig.group_id,
                    event_type="mood_changed",
                    payload={"delta": mood_delta, "mood_score": pig.mood_score},
                )
        return UseItemResult(pig_name=pig.name, item_title=definition.title, outcome_text=outcome_text)

    async def award_random_item(
        self,
        *,
        pig,
        source_key: str,
        now: datetime,
        source_type: str,
        source_id: str | None = None,
    ) -> InventoryItemView | None:
        pool = RAID_ITEM_POOLS.get(source_key)
        if not pool:
            return None
        item_code = self._rng.choice(pool)
        item = await self.award_item(
            pig=pig,
            item_code=item_code,
            now=now,
            source_type=source_type,
            source_id=source_id,
        )
        return self._to_view(item) if item is not None else None

    async def award_item(
        self,
        *,
        pig,
        item_code: str,
        now: datetime,
        source_type: str,
        source_id: str | None = None,
    ):
        inventory_count = await self._items.count_inventory(pig_id=pig.id, now=now)
        if inventory_count >= 3:
            return None

        definition = get_item_definition(item_code)
        item = await self._items.create(
            pig_id=pig.id,
            group_id=pig.group_id,
            item_code=item_code,
            item_type=definition.item_type,
            durability=definition.default_durability,
        )
        await self._events.create(
            pig_id=pig.id,
            group_id=pig.group_id,
            event_type="item_found",
            payload={"item_code": item_code, "source_type": source_type, "source_id": source_id},
        )
        return item

    async def wear_item(self, item, *, now: datetime) -> str | None:
        if item is None or item.durability is None:
            return None

        item.durability -= 1
        if item.durability <= 0:
            item.is_equipped = False
            item.expires_at = now
            return get_item_definition(item.item_code).title
        return None

    async def _apply_consumable(
        self,
        pig,
        *,
        item,
        target_telegram_user_id: int | None,
        now: datetime,
    ) -> tuple[str, int]:
        if pig.status != PigStatus.IDLE:
            raise PigBusyError

        if item.item_code == ITEM_SUSPICIOUS_FEED:
            gain = quantize_weight(Decimal(str(self._rng.uniform(0.8, 1.8))))
            pig.weight_kg += gain
            mood_delta = 0
            if self._rng.random() < 0.45:
                mood_delta = apply_mood_change(pig, delta=-10)
            return (
                (
                    f"Прирост веса: +{gain} кг."
                    if mood_delta == 0
                    else f"Прирост веса: +{gain} кг, но настроение ощутимо испортилось."
                ),
                mood_delta,
            )

        if item.item_code == ITEM_LUCKY_CHARM:
            await self._effects.create(
                pig_id=pig.id,
                group_id=pig.group_id,
                effect_type=EFFECT_RAID_BAD_LUCK_GUARD,
                source_type="item",
                source_id=str(item.id),
                expires_at=now + timedelta(hours=12),
            )
            return "Следующий совсем плохой рейд будет смягчён.", 0

        if item.item_code == ITEM_STINKY_OINTMENT:
            await self._effects.create(
                pig_id=pig.id,
                group_id=pig.group_id,
                effect_type=EFFECT_SABOTAGE_GUARD,
                source_type="item",
                source_id=str(item.id),
                expires_at=now + timedelta(hours=8),
            )
            return "На несколько часов свинья стала отвратительно неудобной целью.", 0

        if item.item_code == ITEM_WET_NEWSPAPER:
            return await self._apply_wet_newspaper(
                pig,
                item=item,
                target_telegram_user_id=target_telegram_user_id,
                now=now,
            )

        raise ItemUseError

    async def _consume_item(self, item, *, now: datetime) -> None:
        item.is_equipped = False
        item.expires_at = now
        item.durability = 0

    async def _get_pig_for_owner(self, *, telegram_group_id: int, telegram_user_id: int):
        pig = await self._pigs.get_group_with_pig_for_owner(
            telegram_group_id=telegram_group_id,
            telegram_user_id=telegram_user_id,
        )
        if pig is None:
            raise PigNotFoundError
        return pig

    async def _get_locked_pig_for_owner(self, *, telegram_group_id: int, telegram_user_id: int):
        group = await self._groups.get_by_telegram_id(telegram_group_id)
        user = await self._users.get_by_telegram_id(telegram_user_id)
        if group is None or user is None:
            raise PigNotFoundError

        pig = await self._pigs.get_by_group_owner_for_update(group_id=group.id, owner_user_id=user.id)
        if pig is None:
            raise PigNotFoundError
        return pig

    async def _get_inventory_item_by_slot(self, *, pig_id, slot: int, now: datetime):
        if slot <= 0:
            raise ItemNotFoundError
        items = await self._items.list_inventory(pig_id=pig_id, now=now)
        index = slot - 1
        if index >= len(items):
            raise ItemNotFoundError
        return items[index]

    async def _apply_wet_newspaper(
        self,
        pig,
        *,
        item,
        target_telegram_user_id: int | None,
        now: datetime,
    ) -> tuple[str, int]:
        if target_telegram_user_id is None:
            raise WetNewspaperTargetError

        target_user = await self._users.get_by_telegram_id(target_telegram_user_id)
        if target_user is None or target_user.id == pig.owner_user_id:
            raise WetNewspaperTargetError

        target = await self._pigs.get_by_group_owner_for_update(group_id=pig.group_id, owner_user_id=target_user.id)
        if target is None:
            raise WetNewspaperTargetError
        if target.status in {PigStatus.ON_RAID, PigStatus.IN_BATTLE, PigStatus.QUARANTINED, PigStatus.DEAD}:
            raise WetNewspaperBlockedError

        existing = await self._effects.get_first_matching_for_update(
            pig_id=target.id,
            effect_types=[EFFECT_WET_NEWSPAPER_CURSE],
            now=now,
        )
        if existing is not None:
            raise WetNewspaperBlockedError

        await self._effects.create(
            pig_id=target.id,
            group_id=target.group_id,
            effect_type=EFFECT_WET_NEWSPAPER_CURSE,
            source_type="item",
            source_id=str(item.id),
            expires_at=now + timedelta(hours=12),
            payload={"remaining_battles": 3, "attacker_pig_id": str(pig.id)},
        )
        await self._events.create(
            pig_id=target.id,
            group_id=target.group_id,
            event_type="wet_newspaper_applied",
            payload={"attacker_id": str(pig.id), "target_id": str(target.id)},
        )
        return (
            f"Мокрая газета с хлюпом прилетела в {target.name}. До 12 часов или трёх боёв от неё будет пахнуть редакцией и стыдом.",
            0,
        )

    def _to_view(self, item) -> InventoryItemView:
        definition = get_item_definition(item.item_code)
        return InventoryItemView(
            item_id=item.id,
            code=item.item_code,
            title=definition.title,
            summary=definition.summary,
            item_type=item.item_type,
            is_equipped=item.is_equipped,
            durability=item.durability,
            expires_at=item.expires_at,
        )
