from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from app.bootstrap import AppContext, build_app_context, close_app_context
from app.bot.formatting import format_battle_result, format_raid_result
from app.db.base import session_scope
from app.db.repositories.effect_repo import PigEffectRepository
from app.db.repositories.group_repo import GroupRepository
from app.db.repositories.world_event_repo import WorldEventRepository
from app.domain.services.matchmaking_service import MatchmakingService
from app.domain.services.raid_service import RaidService
from app.domain.services.world_event_service import WorldEventService
from app.infra.scheduler import run_periodic_job
from app.logging import logger


async def run_worker_tick(app_context: AppContext) -> None:
    now = datetime.now(timezone.utc)

    async with session_scope(app_context.session_factory) as session:
        world_service = WorldEventService(session, settings=app_context.settings, rng=app_context.rng)
        async with session.begin():
            await world_service.ensure_active_event(now=now)
            pending_world_events = await world_service.list_unannounced_active(now=now)
            groups = await GroupRepository(session).list_all() if pending_world_events else []
            world_announcements = [
                (group.telegram_group_id, world_service.build_announcement(event))
                for event in pending_world_events
                for group in groups
            ]
            world_repo = WorldEventRepository(session)
            for event in pending_world_events:
                await world_repo.mark_announced(event, now=now)

        raid_service = RaidService(session, settings=app_context.settings, rng=app_context.rng)
        raid_results = await raid_service.resolve_due_raids(now=now)

        service = MatchmakingService(
            session,
            settings=app_context.settings,
            rng=app_context.rng,
            lock_manager=app_context.lock_manager,
        )
        expired = await service.expire_battle_mode(now=now)
        battles = await service.process_matchmaking_cycle(now=now)
        async with session.begin():
            purged_effects = await PigEffectRepository(session).purge_inactive(now=now)

    if expired:
        logger.info("Expired %s stale battle-ready pigs", expired)
    if purged_effects:
        logger.info("Purged %s inactive temporary effects", purged_effects)

    for battle in battles:
        await app_context.bot.send_message(battle.telegram_group_id, format_battle_result(battle))
    for raid in raid_results:
        await app_context.bot.send_message(raid.telegram_group_id, format_raid_result(raid))
    for telegram_group_id, text in world_announcements:
        await app_context.bot.send_message(telegram_group_id, text)


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
