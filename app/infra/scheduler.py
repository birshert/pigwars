from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from time import monotonic


logger = logging.getLogger(__name__)


async def run_periodic_job(
    name: str,
    interval_seconds: int,
    job: Callable[[], Awaitable[None]],
) -> None:
    while True:
        started_at = monotonic()
        try:
            await job()
        except Exception:
            logger.exception("Periodic job failed: %s", name)
        elapsed = monotonic() - started_at
        await asyncio.sleep(max(interval_seconds - elapsed, 0.1))
