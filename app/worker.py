from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from app.bootstrap import AppContext, build_app_context, close_app_context
from app.bot.formatting import format_battle_result
from app.db.base import session_scope
from app.domain.services.matchmaking_service import MatchmakingService
from app.infra.scheduler import run_periodic_job
from app.logging import logger


async def run_worker_tick(app_context: AppContext) -> None:
    now = datetime.now(timezone.utc)

    async with session_scope(app_context.session_factory) as session:
        service = MatchmakingService(
            session,
            settings=app_context.settings,
            rng=app_context.rng,
            lock_manager=app_context.lock_manager,
        )
        expired = await service.expire_battle_mode(now=now)
        battles = await service.process_matchmaking_cycle(now=now)

    if expired:
        logger.info("Expired %s stale battle-ready pigs", expired)

    for battle in battles:
        await app_context.bot.send_message(battle.telegram_group_id, format_battle_result(battle))


async def main() -> None:
    app_context, engine = await build_app_context()
    try:
        logger.info("Starting PigWars worker")
        await run_periodic_job(
            "matchmaking",
            app_context.settings.matchmaking_interval_seconds,
            lambda: run_worker_tick(app_context),
        )
    finally:
        await close_app_context(app_context, engine)


if __name__ == "__main__":
    asyncio.run(main())
