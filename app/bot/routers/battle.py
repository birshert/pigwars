from __future__ import annotations

from datetime import datetime, timezone

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.bootstrap import AppContext
from app.bot.formatting import format_battle_entry
from app.bot.utils import is_group_chat
from app.db.base import session_scope
from app.domain.exceptions import BattleCooldownError, ConcurrentActionError, PigBusyError, PigNotFoundError
from app.domain.rules.cooldowns import format_timedelta
from app.domain.services.battle_service import BattleQueueService


router = Router(name="battle")


@router.message(Command("battle"))
async def battle_handler(message: Message, app_context: AppContext) -> None:
    if not is_group_chat(message):
        await message.answer("Эта команда работает только в группе.")
        return
    if message.from_user is None:
        return

    now = datetime.now(timezone.utc)
    async with session_scope(app_context.session_factory) as session:
        service = BattleQueueService(
            session,
            battle_cooldown=app_context.settings.battle_cooldown,
            battle_ready_ttl=app_context.settings.battle_ready_ttl,
            rng=app_context.rng,
            lock_manager=app_context.lock_manager,
        )
        try:
            result = await service.enter_battle_mode(
                telegram_group_id=message.chat.id,
                telegram_user_id=message.from_user.id,
                now=now,
            )
        except PigNotFoundError:
            await message.answer("Сначала создай свинью через /create_pig <name>.")
            return
        except BattleCooldownError as error:
            await message.answer(
                "Свинья ещё не отошла от прошлого выхода на арену.\n"
                f"До следующего входа в бой осталось: {format_timedelta(error.remaining)}."
            )
            return
        except PigBusyError:
            await message.answer("Свинья уже ищет драку, дерётся или ушла в вылазку.")
            return
        except ConcurrentActionError:
            await message.answer("Команда уже обрабатывается. Попробуй ещё раз через пару секунд.")
            return

    await message.answer(format_battle_entry(result))
