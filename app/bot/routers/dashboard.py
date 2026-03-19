from __future__ import annotations

import asyncio

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.bootstrap import AppContext
from app.bot.keyboards.admin import build_player_dashboard_keyboard, build_url_keyboard
from app.infra.ngrok import resolve_player_mini_app_url


router = Router(name="dashboard")


@router.message(Command("dashboard"))
async def dashboard_handler(message: Message, app_context: AppContext) -> None:
    if message.from_user is None:
        return

    dashboard_url = await asyncio.to_thread(resolve_player_mini_app_url, app_context.settings)
    if not dashboard_url:
        await message.answer(
            "Не удалось определить публичный URL личного дашборда. "
            "Запусти web-сервис и ngrok или задай PLAYER_MINI_APP_URL."
        )
        return

    if message.chat.type == "private":
        await message.answer(
            "Открыть личный дашборд PigWars:",
            reply_markup=build_player_dashboard_keyboard(dashboard_url),
        )
        return

    bot_user = await app_context.bot.get_me()
    if not bot_user.username:
        await message.answer(
            "Telegram не даёт открыть mini app кнопкой прямо в группе. Напиши боту в личку: /dashboard"
        )
        return

    await message.answer(
        "В группе Telegram не разрешает запускать `web_app` кнопки.\n"
        "Нажми кнопку ниже: она откроет личку с ботом, и там сразу появится кнопка дашборда.",
        reply_markup=build_url_keyboard(
            text="Открыть в личке",
            url=f"https://t.me/{bot_user.username}?start=dashboard",
        ),
    )
