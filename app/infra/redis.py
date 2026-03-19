from __future__ import annotations

from redis.asyncio import Redis

from app.config import Settings


def build_redis(settings: Settings) -> Redis:
    return Redis.from_url(settings.redis_url, encoding="utf-8", decode_responses=True)
