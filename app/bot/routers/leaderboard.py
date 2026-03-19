from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.bootstrap import AppContext
from app.bot.formatting import format_leaderboard
from app.bot.utils import is_group_chat
from app.db.base import session_scope
from app.domain.services.leaderboard_service import LeaderboardService


router = Router(name="leaderboard")


@router.message(Command("leaderboard"))
async def leaderboard_handler(message: Message, app_context: AppContext) -> None:
    if not is_group_chat(message):
        await message.answer("Эта команда работает только в группе.")
        return

    async with session_scope(app_context.session_factory) as session:
        service = LeaderboardService(session)
        entries = await service.get_weight_leaderboard(telegram_group_id=message.chat.id)

    await message.answer(format_leaderboard(entries))
