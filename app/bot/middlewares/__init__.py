"""Bot middlewares."""

from app.bot.middlewares.update_dedup import UpdateDedupMiddleware

__all__ = ["UpdateDedupMiddleware"]
