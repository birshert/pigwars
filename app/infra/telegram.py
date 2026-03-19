from __future__ import annotations

from aiogram import Bot

from app.config import Settings


def build_bot(settings: Settings) -> Bot:
    return Bot(token=settings.bot_token)
