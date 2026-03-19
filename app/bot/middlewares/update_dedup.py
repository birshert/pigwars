from __future__ import annotations

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from redis.asyncio import Redis


class UpdateDedupMiddleware(BaseMiddleware):
    def __init__(self, redis: Redis, ttl_seconds: int) -> None:
        self._redis = redis
        self._ttl_seconds = ttl_seconds

    async def __call__(self, handler, event: TelegramObject, data):
        update = data.get("event_update")
        if update is None:
            return await handler(event, data)

        key = f"telegram:update:{update.update_id}"
        is_new = await self._redis.set(key, "1", ex=self._ttl_seconds, nx=True)
        if not is_new:
            return None

        return await handler(event, data)
