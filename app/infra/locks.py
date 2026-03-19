from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from redis.asyncio import Redis


LOCK_RELEASE_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
  return redis.call('del', KEYS[1])
end
return 0
"""


@dataclass(slots=True)
class RedisLease:
    redis: Redis
    key: str
    token: str
    acquired: bool

    async def release(self) -> None:
        if not self.acquired:
            return
        await self.redis.eval(LOCK_RELEASE_SCRIPT, 1, self.key, self.token)
        self.acquired = False


class RedisLockManager:
    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def acquire(self, key: str, ttl_seconds: int) -> RedisLease:
        token = str(uuid4())
        acquired = bool(await self._redis.set(key, token, ex=ttl_seconds, nx=True))
        return RedisLease(redis=self._redis, key=key, token=token, acquired=acquired)
