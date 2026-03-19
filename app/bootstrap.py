from __future__ import annotations

import random
from dataclasses import dataclass, field

from aiogram import Bot
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.config import Settings, get_settings
from app.db.base import build_engine, build_session_factory
from app.infra.locks import RedisLockManager
from app.infra.redis import build_redis
from app.infra.telegram import build_bot
from app.logging import configure_logging


@dataclass(slots=True)
class AppContext:
    settings: Settings
    bot: Bot
    redis: Redis
    lock_manager: RedisLockManager
    session_factory: async_sessionmaker[AsyncSession]
    rng: random.Random = field(default_factory=random.Random)


async def build_app_context(settings: Settings | None = None) -> tuple[AppContext, AsyncEngine]:
    configure_logging()
    resolved_settings = settings or get_settings()
    engine = build_engine(resolved_settings)
    session_factory = build_session_factory(engine)
    redis = build_redis(resolved_settings)
    bot = build_bot(resolved_settings)
    context = AppContext(
        settings=resolved_settings,
        bot=bot,
        redis=redis,
        lock_manager=RedisLockManager(redis),
        session_factory=session_factory,
    )
    return context, engine


async def close_app_context(context: AppContext, engine: AsyncEngine) -> None:
    await context.bot.session.close()
    await context.redis.aclose()
    await engine.dispose()
