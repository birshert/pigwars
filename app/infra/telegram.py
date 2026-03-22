from __future__ import annotations

from typing import Any

from aiogram import Bot
from aiogram.exceptions import TelegramMigrateToChat

from app.config import Settings


def build_bot(settings: Settings) -> Bot:
    return Bot(token=settings.bot_token)


async def send_message_with_migration(
    bot: Bot,
    chat_id: int,
    text: str,
    **kwargs: Any,
):
    try:
        sent_message = await bot.send_message(chat_id, text, **kwargs)
        return sent_message, chat_id
    except TelegramMigrateToChat as exc:
        migrated_chat_id = exc.migrate_to_chat_id
        sent_message = await bot.send_message(migrated_chat_id, text, **kwargs)
        return sent_message, migrated_chat_id
