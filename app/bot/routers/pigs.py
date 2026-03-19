from __future__ import annotations

from datetime import datetime, timezone

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from app.bootstrap import AppContext
from app.bot.formatting import format_feed_result, format_pig_profile, format_rename_pig_result
from app.bot.utils import is_group_chat
from app.db.base import session_scope
from app.domain.exceptions import ConcurrentActionError, FeedCooldownError, InvalidPigNameError, PigAlreadyExistsError, PigBusyError, PigNotFoundError
from app.domain.rules.cooldowns import format_timedelta
from app.domain.services.feeding_service import FeedingService
from app.domain.services.pig_service import PigService


router = Router(name="pigs")


@router.message(Command("create_pig"))
async def create_pig_handler(
    message: Message,
    command: CommandObject,
    app_context: AppContext,
) -> None:
    if not is_group_chat(message):
        await message.answer("Эта команда работает только в группе.")
        return
    if message.from_user is None:
        return
    if not command.args:
        await message.answer("Использование: /create_pig <name>")
        return

    now = datetime.now(timezone.utc)
    async with session_scope(app_context.session_factory) as session:
        service = PigService(
            session,
            feed_cooldown=app_context.settings.feed_cooldown,
            battle_cooldown=app_context.settings.battle_cooldown,
            sabotage_cooldown=app_context.settings.sabotage_cooldown,
            raid_cooldown=app_context.settings.raid_cooldown,
            rng=app_context.rng,
        )
        try:
            profile = await service.create_pig(
                telegram_group_id=message.chat.id,
                group_title=message.chat.title or "PigWars Group",
                telegram_user_id=message.from_user.id,
                username=message.from_user.username,
                first_name=message.from_user.first_name,
                last_name=message.from_user.last_name,
                pig_name=command.args,
                now=now,
            )
        except InvalidPigNameError:
            await message.answer("Имя свиньи должно быть длиной от 3 до 40 символов.")
            return
        except PigAlreadyExistsError:
            await message.answer("У тебя уже есть свинья в этой группе.")
            return

    await message.answer(
        "🐷 В группе появилась новая свинья: "
        f"{profile.name}!\n"
        f"Стартовый вес: {profile.weight_kg} кг\n"
        f"Черта: {profile.trait_title}\n"
        "Кормить можно уже сейчас. В бой тоже, если не страшно."
    )


@router.message(Command("rename_pig"))
async def rename_pig_handler(
    message: Message,
    command: CommandObject,
    app_context: AppContext,
) -> None:
    if not is_group_chat(message):
        await message.answer("Эта команда работает только в группе.")
        return
    if message.from_user is None:
        return
    if not command.args:
        await message.answer("Использование: /rename_pig <new name>")
        return

    now = datetime.now(timezone.utc)
    async with session_scope(app_context.session_factory) as session:
        service = PigService(
            session,
            feed_cooldown=app_context.settings.feed_cooldown,
            battle_cooldown=app_context.settings.battle_cooldown,
            sabotage_cooldown=app_context.settings.sabotage_cooldown,
            raid_cooldown=app_context.settings.raid_cooldown,
            rng=app_context.rng,
        )
        try:
            result = await service.rename_pig(
                telegram_group_id=message.chat.id,
                telegram_user_id=message.from_user.id,
                new_name=command.args,
                now=now,
            )
        except InvalidPigNameError:
            await message.answer("Имя свиньи должно быть длиной от 3 до 40 символов.")
            return
        except PigNotFoundError:
            await message.answer("В этой группе у тебя пока нет свиньи. Создай её через /create_pig <name>.")
            return

    await message.answer(format_rename_pig_result(result))


@router.message(Command("pig"))
async def pig_handler(message: Message, app_context: AppContext) -> None:
    if not is_group_chat(message):
        await message.answer("Эта команда работает только в группе.")
        return
    if message.from_user is None:
        return

    now = datetime.now(timezone.utc)
    async with session_scope(app_context.session_factory) as session:
        service = PigService(
            session,
            feed_cooldown=app_context.settings.feed_cooldown,
            battle_cooldown=app_context.settings.battle_cooldown,
            sabotage_cooldown=app_context.settings.sabotage_cooldown,
            raid_cooldown=app_context.settings.raid_cooldown,
            rng=app_context.rng,
        )
        try:
            profile = await service.get_pig_profile(
                telegram_group_id=message.chat.id,
                telegram_user_id=message.from_user.id,
                now=now,
            )
        except PigNotFoundError:
            await message.answer("В этой группе у тебя пока нет свиньи. Создай её через /create_pig <name>.")
            return

    await message.answer(format_pig_profile(profile))


@router.message(Command("feed"))
async def feed_handler(message: Message, app_context: AppContext) -> None:
    if not is_group_chat(message):
        await message.answer("Эта команда работает только в группе.")
        return
    if message.from_user is None:
        return

    now = datetime.now(timezone.utc)
    async with session_scope(app_context.session_factory) as session:
        service = FeedingService(
            session,
            feed_cooldown=app_context.settings.feed_cooldown,
            rng=app_context.rng,
            lock_manager=app_context.lock_manager,
        )
        try:
            result = await service.feed_pig(
                telegram_group_id=message.chat.id,
                telegram_user_id=message.from_user.id,
                now=now,
            )
        except PigNotFoundError:
            await message.answer("Сначала создай свинью через /create_pig <name>.")
            return
        except FeedCooldownError as error:
            await message.answer(
                "Свинья ещё переваривает.\n"
                f"До следующего кормления осталось: {format_timedelta(error.remaining)}."
            )
            return
        except PigBusyError:
            await message.answer("Нельзя кормить свинью, пока она занята боем или вылазкой.")
            return
        except ConcurrentActionError:
            await message.answer("Команда уже обрабатывается. Попробуй ещё раз через пару секунд.")
            return

    await message.answer(format_feed_result(result))
