"""Bot routers."""

from aiogram import Dispatcher

from app.bot.routers.battle import router as battle_router
from app.bot.routers.leaderboard import router as leaderboard_router
from app.bot.routers.pigs import router as pigs_router
from app.bot.routers.start import router as start_router


def register_routers(dispatcher: Dispatcher) -> None:
    dispatcher.include_router(start_router)
    dispatcher.include_router(pigs_router)
    dispatcher.include_router(battle_router)
    dispatcher.include_router(leaderboard_router)


__all__ = ["register_routers"]
