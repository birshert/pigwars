from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories.daily_action_repo import PigDailyActionRepository
from app.db.repositories.effect_repo import PigEffectRepository
from app.db.repositories.event_repo import PigEventRepository
from app.db.repositories.group_repo import GroupRepository
from app.db.repositories.pig_repo import PigRepository
from app.db.repositories.user_repo import UserRepository
from app.db.repositories.world_event_repo import WorldEventRepository
from app.domain.exceptions import PigBusyError, PigNotFoundError
from app.domain.feature_catalog import (
    EFFECT_BATTLE_FOCUS,
    EFFECT_GOOD_OMENS,
    EFFECT_HOROSCOPE_BARN_ARCHER,
    EFFECT_HOROSCOPE_BOAR_LION,
    EFFECT_HOROSCOPE_MUD_FISH,
    EFFECT_HOROSCOPE_SWINE_SCALES,
    EFFECT_WHEEL_APPLAUSE,
    EFFECT_WHEEL_CABBAGE_OMEN,
    EFFECT_WHEEL_FAIR,
    EFFECT_WHEEL_HAY,
    EFFECT_WHEEL_PUDDLE,
    EFFECT_WHEEL_STICKY,
    ITEM_BOAR_HORSESHOES,
    ITEM_IRON_POT,
    ITEM_LUCKY_CHARM,
    ITEM_STINKY_OINTMENT,
    ITEM_WET_NEWSPAPER,
    get_world_event_definition,
)
from app.domain.models.pig import PigStatus
from app.domain.rules.combat import quantize_weight
from app.domain.rules.timezones import end_of_game_day, get_game_day
from app.domain.services.item_service import ItemService
from app.domain.services.pig_modifier_resolver import PigModifierResolver
from app.schemas.pig import DailyActionResult, DailyActionState, DailyView


ACTION_DAILY_HOROSCOPE = "daily_horoscope"
ACTION_DAILY_TROUGH = "daily_trough"
ACTION_DAILY_SHAME_WHEEL = "daily_shame_wheel"


@dataclass(frozen=True, slots=True)
class _DailyOption:
    key: str
    title: str
    text: str
    effect_type: str | None = None


@dataclass(frozen=True, slots=True)
class _WeightedChoice:
    weight: int
    key: str


HOROSCOPE_OPTIONS: tuple[_DailyOption, ...] = (
    _DailyOption(
        key="boar_lion",
        title="Кабан-Лев",
        text="Деревенский звездочет велит идти напролом: сегодня арена любит наглых, но хитрость у тебя слегка отсырела.",
        effect_type=EFFECT_HOROSCOPE_BOAR_LION,
    ),
    _DailyOption(
        key="swine_scales",
        title="Свин-Весы",
        text="Навозные созвездия сулят ровный пятачок и полезный фарт в вылазках, если не начать сомневаться посреди драки.",
        effect_type=EFFECT_HOROSCOPE_SWINE_SCALES,
    ),
    _DailyOption(
        key="mud_fish",
        title="Поросенок-Рыбы",
        text="Сегодня чуешь знаки в любой луже. Мир склизкий, но кое-как помогает избегать особенно тупых неприятностей.",
        effect_type=EFFECT_HOROSCOPE_MUD_FISH,
    ),
    _DailyOption(
        key="barn_archer",
        title="Кабан-Стрелец",
        text="Комбикормовые звезды обещают дерзость и кривую, но бодрую удачу. Главное не перепутать подвиг с пакостью.",
        effect_type=EFFECT_HOROSCOPE_BARN_ARCHER,
    ),
)

TROUGH_WEIGHTS: tuple[_WeightedChoice, ...] = (
    _WeightedChoice(weight=28, key="wet_newspaper"),
    _WeightedChoice(weight=24, key="turnip_haul"),
    _WeightedChoice(weight=14, key="stinky_ointment"),
    _WeightedChoice(weight=12, key="good_omens"),
    _WeightedChoice(weight=10, key="lucky_charm"),
    _WeightedChoice(weight=8, key="battle_focus"),
    _WeightedChoice(weight=3, key="iron_pot"),
    _WeightedChoice(weight=1, key="boar_horseshoes"),
)

WHEEL_WEIGHTS: tuple[_WeightedChoice, ...] = (
    _WeightedChoice(weight=24, key="puddle"),
    _WeightedChoice(weight=22, key="hay"),
    _WeightedChoice(weight=18, key="sticky"),
    _WeightedChoice(weight=14, key="fair"),
    _WeightedChoice(weight=12, key="applause"),
    _WeightedChoice(weight=10, key="cabbage_omen"),
)


class DailyFeatureService:
    def __init__(self, session: AsyncSession, *, rng: random.Random) -> None:
        self._session = session
        self._rng = rng
        self._groups = GroupRepository(session)
        self._users = UserRepository(session)
        self._pigs = PigRepository(session)
        self._actions = PigDailyActionRepository(session)
        self._effects = PigEffectRepository(session)
        self._events = PigEventRepository(session)
        self._world_events = WorldEventRepository(session)
        self._resolver = PigModifierResolver(session)
        self._items = ItemService(session, rng=rng)

    async def get_daily_view(
        self,
        *,
        telegram_group_id: int,
        telegram_user_id: int,
        now: datetime,
    ) -> DailyView:
        async with self._session.begin():
            pig = await self._get_locked_pig_for_owner(
                telegram_group_id=telegram_group_id,
                telegram_user_id=telegram_user_id,
            )
            horoscope_action = await self.ensure_horoscope_for_pig(pig, now=now)
            action_day = get_game_day(now)
            actions = {
                action.action_type: action
                for action in await self._actions.list_for_day(pig_id=pig.id, action_day=action_day)
            }
            resolved = await self._resolver.resolve_profile_state(pig, now=now)
            world_event = await self._world_events.get_active(now=now)

        horoscope_payload = horoscope_action.payload or {}
        world_definition = get_world_event_definition(world_event.event_code) if world_event is not None else None
        return DailyView(
            pig_name=pig.name,
            horoscope_title=str(horoscope_payload.get("title", "Безымянный хлевный знак")),
            horoscope_text=str(horoscope_payload.get("text", "Звезды молчат, но навоз насторожен.")),
            trough=self._to_action_state(actions.get(ACTION_DAILY_TROUGH), action_name="Корыто удачи", command_hint="/daily корыто"),
            wheel=self._to_action_state(
                actions.get(ACTION_DAILY_SHAME_WHEEL),
                action_name="Колесо деревенского позора",
                command_hint="/daily колесо",
            ),
            active_effects=resolved.active_effects,
            world_event_title=world_event.title if world_event is not None else None,
            world_event_description=world_definition.description if world_definition is not None else None,
        )

    async def use_trough(
        self,
        *,
        telegram_group_id: int,
        telegram_user_id: int,
        now: datetime,
    ) -> DailyActionResult:
        async with self._session.begin():
            pig = await self._get_locked_pig_for_owner(
                telegram_group_id=telegram_group_id,
                telegram_user_id=telegram_user_id,
            )
            await self.ensure_horoscope_for_pig(pig, now=now)
            self._ensure_pig_is_available(pig)
            action_day = get_game_day(now)
            existing = await self._actions.get_for_day(
                pig_id=pig.id,
                action_type=ACTION_DAILY_TROUGH,
                action_day=action_day,
            )
            if existing is not None:
                return self._action_result(existing, pig_name=pig.name, action_name="Корыто удачи", already_used=True)

            result_key = self._weighted_choice(TROUGH_WEIGHTS)
            created = await self._resolve_trough_result(pig, result_key=result_key, now=now, action_day=action_day)
            await self._events.create(
                pig_id=pig.id,
                group_id=pig.group_id,
                event_type="daily_trough_used",
                payload={"result_key": created.result_key},
            )
        return self._action_result(created, pig_name=pig.name, action_name="Корыто удачи", already_used=False)

    async def spin_shame_wheel(
        self,
        *,
        telegram_group_id: int,
        telegram_user_id: int,
        now: datetime,
    ) -> DailyActionResult:
        async with self._session.begin():
            pig = await self._get_locked_pig_for_owner(
                telegram_group_id=telegram_group_id,
                telegram_user_id=telegram_user_id,
            )
            await self.ensure_horoscope_for_pig(pig, now=now)
            self._ensure_pig_is_available(pig)
            action_day = get_game_day(now)
            existing = await self._actions.get_for_day(
                pig_id=pig.id,
                action_type=ACTION_DAILY_SHAME_WHEEL,
                action_day=action_day,
            )
            if existing is not None:
                return self._action_result(
                    existing,
                    pig_name=pig.name,
                    action_name="Колесо деревенского позора",
                    already_used=True,
                )

            result_key = self._weighted_choice(WHEEL_WEIGHTS)
            created = await self._resolve_wheel_result(pig, result_key=result_key, now=now, action_day=action_day)
            await self._events.create(
                pig_id=pig.id,
                group_id=pig.group_id,
                event_type="daily_shame_wheel_used",
                payload={"result_key": created.result_key},
            )
        return self._action_result(
            created,
            pig_name=pig.name,
            action_name="Колесо деревенского позора",
            already_used=False,
        )

    async def ensure_horoscope_for_pig(self, pig, *, now: datetime):
        action_day = get_game_day(now)
        existing = await self._actions.get_for_day(
            pig_id=pig.id,
            action_type=ACTION_DAILY_HOROSCOPE,
            action_day=action_day,
        )
        if existing is not None:
            return existing

        option = self._rng.choice(HOROSCOPE_OPTIONS)
        payload = {
            "title": option.title,
            "text": option.text,
            "effect_type": option.effect_type,
        }
        action = await self._actions.create(
            pig_id=pig.id,
            action_type=ACTION_DAILY_HOROSCOPE,
            action_day=action_day,
            result_key=option.key,
            payload=payload,
        )
        if option.effect_type is not None:
            await self._effects.create(
                pig_id=pig.id,
                group_id=pig.group_id,
                effect_type=option.effect_type,
                source_type="daily_horoscope",
                source_id=str(action.id),
                expires_at=end_of_game_day(now),
                payload={"action_day": action_day.isoformat()},
            )
        await self._events.create(
            pig_id=pig.id,
            group_id=pig.group_id,
            event_type="daily_horoscope_assigned",
            payload={"result_key": option.key},
        )
        return action

    async def _resolve_trough_result(self, pig, *, result_key: str, now: datetime, action_day):
        if result_key == "wet_newspaper":
            return await self._create_trough_item_result(
                pig,
                item_code=ITEM_WET_NEWSPAPER,
                result_key=result_key,
                action_day=action_day,
                title="На дне булькнула мокрая газета",
                text="Пахнет редакцией, сыростью и воспитательным потенциалом. Предмет улетел в инвентарь.",
                now=now,
            )
        if result_key == "turnip_haul":
            gain = quantize_weight(Decimal(str(self._rng.uniform(0.18, 0.42))))
            pig.weight_kg += gain
            return await self._actions.create(
                pig_id=pig.id,
                action_type=ACTION_DAILY_TROUGH,
                action_day=action_day,
                result_key=result_key,
                payload={
                    "title": "Корыто отдало горсть корнеплодов",
                    "text": f"Свинья вылизала дно и неожиданно потяжелела на +{gain} кг.",
                },
            )
        if result_key == "stinky_ointment":
            return await self._create_trough_item_result(
                pig,
                item_code=ITEM_STINKY_OINTMENT,
                result_key=result_key,
                action_day=action_day,
                title="Корыто выплюнуло вонючую мазь",
                text="Жижа пахнет так, будто это и есть защита. Предмет добавлен в инвентарь.",
                now=now,
            )
        if result_key == "lucky_charm":
            return await self._create_trough_item_result(
                pig,
                item_code=ITEM_LUCKY_CHARM,
                result_key=result_key,
                action_day=action_day,
                title="На дне блеснул талисман удачи",
                text="Не сказать что чистый, зато явно обещает один полезный счастливый случай.",
                now=now,
            )
        if result_key == "iron_pot":
            return await self._create_trough_item_result(
                pig,
                item_code=ITEM_IRON_POT,
                result_key=result_key,
                action_day=action_day,
                title="Корыто достало кастрюлю",
                text="Похоже, кто-то варил в ней величие. Теперь можно носить это на голове.",
                now=now,
            )
        if result_key == "boar_horseshoes":
            return await self._create_trough_item_result(
                pig,
                item_code=ITEM_BOAR_HORSESHOES,
                result_key=result_key,
                action_day=action_day,
                title="Джекпот: кабаньи подковы",
                text="Корыто вдруг решило, что сегодня у тебя редкий приступ деревенского величия.",
                now=now,
            )
        if result_key == "battle_focus":
            return await self._create_trough_effect_result(
                pig,
                effect_type=EFFECT_BATTLE_FOCUS,
                result_key=result_key,
                action_day=action_day,
                title="Корыто ударило в боевой раж",
                text="Свинья вытащила из жижи странную уверенность. Следующая драка должна зайти бодрее.",
                now=now,
            )
        return await self._create_trough_effect_result(
            pig,
            effect_type=EFFECT_GOOD_OMENS,
            result_key=result_key,
            action_day=action_day,
            title="Корыто нашептало добрые приметы",
            text="На дне нашёлся сельский знак удачи. Следующая вылазка выглядит чуть менее безнадёжно.",
            now=now,
        )

    async def _resolve_wheel_result(self, pig, *, result_key: str, now: datetime, action_day):
        options = {
            "puddle": (
                EFFECT_WHEEL_PUDDLE,
                "Колесо решило: сегодня ты упала в лужу",
                "Деревня всё видела. Позор мокрый, но мягкий, и до конца дня будет идти за тобой.",
            ),
            "hay": (
                EFFECT_WHEEL_HAY,
                "Колесо присудило аромат сена",
                "Теперь от свиньи тянет сеновалом так уверенно, будто это официальный парфюм сезона.",
            ),
            "sticky": (
                EFFECT_WHEEL_STICKY,
                "Колесо объявило липкую эпоху",
                "Никто не знает почему, но сегодня свинья подозрительно липкая и слегка недовольная собой.",
            ),
            "fair": (
                EFFECT_WHEEL_FAIR,
                "Колесо вспомнило ярмарочный конфуз",
                "Самоуверенность была хороша ровно до первой канавы. Остальное добьёт сама память.",
            ),
            "applause": (
                EFFECT_WHEEL_APPLAUSE,
                "Редкость: ярмарочные аплодисменты",
                "Колесо на секунду полюбило тебя и даже выдало приличный бонус вместо обычного стыда.",
            ),
            "cabbage_omen": (
                EFFECT_WHEEL_CABBAGE_OMEN,
                "Колесо пожаловало капустную примету",
                "Впервые за долгое время деревенский абсурд сработал в плюс. Чуть-чуть, но приятно.",
            ),
        }
        effect_type, title, text = options[result_key]
        await self._effects.create(
            pig_id=pig.id,
            group_id=pig.group_id,
            effect_type=effect_type,
            source_type="daily_wheel",
            expires_at=end_of_game_day(now),
            payload={"action_day": action_day.isoformat()},
        )
        return await self._actions.create(
            pig_id=pig.id,
            action_type=ACTION_DAILY_SHAME_WHEEL,
            action_day=action_day,
            result_key=result_key,
            payload={"title": title, "text": text, "effect_type": effect_type},
        )

    async def _create_trough_item_result(
        self,
        pig,
        *,
        item_code: str,
        result_key: str,
        action_day,
        title: str,
        text: str,
        now: datetime,
    ):
        awarded = await self._items.award_item(
            pig=pig,
            item_code=item_code,
            now=now,
            source_type="daily_trough",
        )
        payload = {"title": title, "text": text, "item_code": item_code}
        if awarded is None:
            fallback_gain = quantize_weight(Decimal("0.12"))
            pig.weight_kg += fallback_gain
            payload["text"] = (
                f"Инвентарь забит, поэтому корыто просто вмазало свинье по аппетиту. Прирост веса: +{fallback_gain} кг."
            )
        return await self._actions.create(
            pig_id=pig.id,
            action_type=ACTION_DAILY_TROUGH,
            action_day=action_day,
            result_key=result_key,
            payload=payload,
        )

    async def _create_trough_effect_result(
        self,
        pig,
        *,
        effect_type: str,
        result_key: str,
        action_day,
        title: str,
        text: str,
        now: datetime,
    ):
        await self._effects.create(
            pig_id=pig.id,
            group_id=pig.group_id,
            effect_type=effect_type,
            source_type="daily_trough",
            expires_at=end_of_game_day(now),
            payload={"action_day": action_day.isoformat()},
        )
        return await self._actions.create(
            pig_id=pig.id,
            action_type=ACTION_DAILY_TROUGH,
            action_day=action_day,
            result_key=result_key,
            payload={"title": title, "text": text, "effect_type": effect_type},
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

    def _ensure_pig_is_available(self, pig) -> None:
        if pig.status in {PigStatus.IN_BATTLE, PigStatus.ON_RAID, PigStatus.QUARANTINED, PigStatus.DEAD}:
            raise PigBusyError

    def _to_action_state(self, action, *, action_name: str, command_hint: str) -> DailyActionState:
        payload = (action.payload or {}) if action is not None else {}
        return DailyActionState(
            action_name=action_name,
            available=action is None,
            result_title=payload.get("title") if action is not None else None,
            result_text=payload.get("text") if action is not None else None,
            command_hint=command_hint,
        )

    def _action_result(self, action, *, pig_name: str, action_name: str, already_used: bool) -> DailyActionResult:
        payload = action.payload or {}
        return DailyActionResult(
            pig_name=pig_name,
            action_name=action_name,
            already_used=already_used,
            result_title=str(payload.get("title", action_name)),
            result_text=str(payload.get("text", "Корыто бурлит, но объяснять отказывается.")),
        )

    def _weighted_choice(self, weighted_values: tuple[_WeightedChoice, ...]) -> str:
        options = [value.key for value in weighted_values]
        weights = [value.weight for value in weighted_values]
        return self._rng.choices(options, weights=weights, k=1)[0]
