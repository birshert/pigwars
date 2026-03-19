from __future__ import annotations

import asyncio

from aiogram import Dispatcher
from aiogram.types import BotCommand

from app.bootstrap import build_app_context, close_app_context
from app.bot.middlewares import UpdateDedupMiddleware
from app.bot.routers import register_routers
from app.logging import logger


async def main() -> None:
    app_context, engine = await build_app_context()
    dispatcher = Dispatcher()
    dispatcher["app_context"] = app_context
    dispatcher.message.outer_middleware(
        UpdateDedupMiddleware(
            app_context.redis,
            ttl_seconds=app_context.settings.telegram_update_dedup_ttl_seconds,
        )
    )
    register_routers(dispatcher)

    await app_context.bot.set_my_commands(
        [
            BotCommand(command="create_pig", description="Create your pig"),
            BotCommand(command="pig", description="Show your pig"),
            BotCommand(command="feed", description="Feed your pig"),
            BotCommand(command="battle", description="Enter battle queue"),
            BotCommand(command="inventory", description="Show pig inventory"),
            BotCommand(command="equip", description="Equip an item by slot"),
            BotCommand(command="use_item", description="Use an item by slot"),
            BotCommand(command="raid", description="Send pig on a raid"),
            BotCommand(command="sabotage", description="Sabotage reply target"),
            BotCommand(command="world", description="Show current world event"),
            BotCommand(command="leaderboard", description="Show group leaderboard"),
            BotCommand(command="rules", description="Show game rules"),
        ]
    )

    try:
        logger.info("Starting PigWars bot polling")
        await dispatcher.start_polling(app_context.bot)
    finally:
        await close_app_context(app_context, engine)


if __name__ == "__main__":
    asyncio.run(main())
