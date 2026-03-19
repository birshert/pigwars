from __future__ import annotations

import asyncio

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from app.bootstrap import AppContext
from app.bot.keyboards.admin import build_player_dashboard_keyboard
from app.bot.formatting import format_help_message, format_rules_message, format_start_message
from app.bot.utils import is_group_chat
from app.infra.ngrok import resolve_player_mini_app_url


router = Router(name="start")


@router.message(Command("start"))
async def start_handler(
    message: Message,
    command: CommandObject,
    app_context: AppContext,
) -> None:
    if (
        message.chat.type == "private"
        and command.args == "dashboard"
        and message.from_user is not None
    ):
        dashboard_url = await asyncio.to_thread(resolve_player_mini_app_url, app_context.settings)
        if not dashboard_url:
            await message.answer(
                "Не удалось определить публичный URL личного дашборда. "
                "Запусти web-сервис и ngrok или задай PLAYER_MINI_APP_URL."
            )
            return
        await message.answer(
            "Открыть личный дашборд PigWars:",
            reply_markup=build_player_dashboard_keyboard(dashboard_url),
        )
        return

    await message.answer(format_start_message(is_group=is_group_chat(message)))


@router.message(Command("help"))
async def help_handler(message: Message) -> None:
    await message.answer(format_help_message())


@router.message(Command("rules"))
async def rules_handler(message: Message) -> None:
    await message.answer(format_rules_message())
