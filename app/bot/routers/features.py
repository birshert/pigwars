from __future__ import annotations

from datetime import datetime, timezone

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from app.bootstrap import AppContext
from app.bot.formatting import (
    format_equip_result,
    format_inventory,
    format_raid_start,
    format_sabotage_result,
    format_use_item_result,
    format_world_event,
)
from app.bot.utils import is_group_chat
from app.db.base import session_scope
from app.domain.exceptions import (
    ItemEquipError,
    ItemNotFoundError,
    ItemUseError,
    PigBusyError,
    PigNotFoundError,
    RaidCooldownError,
    RaidRefusedError,
    SabotageBlockedError,
    SabotageCooldownError,
    SabotageTargetError,
)
from app.domain.models.pig import RaidDestination
from app.domain.rules.cooldowns import format_timedelta
from app.domain.services.item_service import ItemService
from app.domain.services.raid_service import RaidService
from app.domain.services.sabotage_service import SabotageService
from app.domain.services.world_event_service import WorldEventService


router = Router(name="features")


DESTINATION_ALIASES = {
    "свалка": RaidDestination.DUMP,
    "dump": RaidDestination.DUMP,
    "рынок": RaidDestination.MARKET,
    "market": RaidDestination.MARKET,
    "лес": RaidDestination.WOODS,
    "лесополоса": RaidDestination.WOODS,
    "woods": RaidDestination.WOODS,
}


@router.message(Command("inventory"))
async def inventory_handler(message: Message, app_context: AppContext) -> None:
    if not is_group_chat(message):
        await message.answer("Эта команда работает только в группе.")
        return
    if message.from_user is None:
        return

    now = datetime.now(timezone.utc)
    async with session_scope(app_context.session_factory) as session:
        service = ItemService(session, rng=app_context.rng)
        try:
            inventory = await service.get_inventory(
                telegram_group_id=message.chat.id,
                telegram_user_id=message.from_user.id,
                now=now,
            )
        except PigNotFoundError:
            await message.answer("Сначала создай свинью через /create_pig <name>.")
            return

    await message.answer(format_inventory(inventory))


@router.message(Command("equip"))
async def equip_handler(message: Message, command: CommandObject, app_context: AppContext) -> None:
    if not is_group_chat(message):
        await message.answer("Эта команда работает только в группе.")
        return
    if message.from_user is None:
        return
    if not command.args or not command.args.strip().isdigit():
        await message.answer("Использование: /equip <номер предмета из /inventory>.")
        return

    now = datetime.now(timezone.utc)
    async with session_scope(app_context.session_factory) as session:
        service = ItemService(session, rng=app_context.rng)
        try:
            result = await service.equip_item(
                telegram_group_id=message.chat.id,
                telegram_user_id=message.from_user.id,
                slot=int(command.args.strip()),
                now=now,
            )
        except PigNotFoundError:
            await message.answer("Сначала создай свинью через /create_pig <name>.")
            return
        except ItemNotFoundError:
            await message.answer("Такого слота в инвентаре нет.")
            return
        except ItemEquipError:
            await message.answer("Этот предмет нельзя надеть.")
            return
        except PigBusyError:
            await message.answer("Свинья занята и не может сейчас переэкипироваться.")
            return

    await message.answer(format_equip_result(result))


@router.message(Command("use_item"))
async def use_item_handler(message: Message, command: CommandObject, app_context: AppContext) -> None:
    if not is_group_chat(message):
        await message.answer("Эта команда работает только в группе.")
        return
    if message.from_user is None:
        return
    if not command.args or not command.args.strip().isdigit():
        await message.answer("Использование: /use_item <номер предмета из /inventory>.")
        return

    now = datetime.now(timezone.utc)
    async with session_scope(app_context.session_factory) as session:
        service = ItemService(session, rng=app_context.rng)
        try:
            result = await service.use_item(
                telegram_group_id=message.chat.id,
                telegram_user_id=message.from_user.id,
                slot=int(command.args.strip()),
                now=now,
            )
        except PigNotFoundError:
            await message.answer("Сначала создай свинью через /create_pig <name>.")
            return
        except ItemNotFoundError:
            await message.answer("Такого слота в инвентаре нет.")
            return
        except ItemUseError:
            await message.answer("Этот предмет нельзя использовать как расходник.")
            return
        except PigBusyError:
            await message.answer("Свинья сейчас занята и не может использовать предмет.")
            return

    await message.answer(format_use_item_result(result))


@router.message(Command("raid"))
async def raid_handler(message: Message, command: CommandObject, app_context: AppContext) -> None:
    if not is_group_chat(message):
        await message.answer("Эта команда работает только в группе.")
        return
    if message.from_user is None:
        return
    if not command.args:
        await message.answer("Использование: /raid <свалка|рынок|лес>.")
        return

    destination = DESTINATION_ALIASES.get(command.args.strip().lower())
    if destination is None:
        await message.answer("Неизвестное направление. Доступно: свалка, рынок, лес.")
        return

    now = datetime.now(timezone.utc)
    async with session_scope(app_context.session_factory) as session:
        service = RaidService(session, settings=app_context.settings, rng=app_context.rng)
        try:
            result = await service.start_raid(
                telegram_group_id=message.chat.id,
                telegram_user_id=message.from_user.id,
                destination=destination,
                now=now,
            )
        except PigNotFoundError:
            await message.answer("Сначала создай свинью через /create_pig <name>.")
            return
        except PigBusyError:
            await message.answer("Свинья уже занята и не может уйти в экспедицию.")
            return
        except RaidCooldownError as error:
            await message.answer(
                "Свинья ещё отходит от прошлой вылазки.\n"
                f"До нового рейда осталось: {format_timedelta(error.remaining)}."
            )
            return
        except RaidRefusedError:
            await message.answer("Свинья посмотрела на тебя с презрением и отказалась идти в рейд.")
            return

    await message.answer(format_raid_start(result))


@router.message(Command("sabotage"))
async def sabotage_handler(message: Message, app_context: AppContext) -> None:
    if not is_group_chat(message):
        await message.answer("Эта команда работает только в группе.")
        return
    if message.from_user is None:
        return
    if message.reply_to_message is None or message.reply_to_message.from_user is None:
        await message.answer("Используй /sabotage ответом на сообщение владельца цели.")
        return

    now = datetime.now(timezone.utc)
    async with session_scope(app_context.session_factory) as session:
        service = SabotageService(session, settings=app_context.settings, rng=app_context.rng)
        try:
            result = await service.sabotage(
                telegram_group_id=message.chat.id,
                attacker_telegram_user_id=message.from_user.id,
                target_telegram_user_id=message.reply_to_message.from_user.id,
                now=now,
            )
        except PigNotFoundError:
            await message.answer("Нужны две живые свиньи в этой группе: твоя и цель.")
            return
        except SabotageTargetError:
            await message.answer("Саботировать собственную свинью нельзя.")
            return
        except PigBusyError:
            await message.answer("Твоя свинья сейчас не может устраивать диверсии.")
            return
        except SabotageBlockedError:
            await message.answer("Цель сейчас недоступна для диверсии или уже под активным эффектом.")
            return
        except SabotageCooldownError as error:
            await message.answer(
                "Свинья уже пакостила недавно.\n"
                f"До новой диверсии осталось: {format_timedelta(error.remaining)}."
            )
            return

    await message.answer(format_sabotage_result(result))


@router.message(Command("world"))
async def world_handler(message: Message, app_context: AppContext) -> None:
    if not is_group_chat(message):
        await message.answer("Эта команда работает только в группе.")
        return

    now = datetime.now(timezone.utc)
    async with session_scope(app_context.session_factory) as session:
        async with session.begin():
            service = WorldEventService(session, settings=app_context.settings, rng=app_context.rng)
            view = await service.get_current_view(now=now)

    await message.answer(format_world_event(view))
