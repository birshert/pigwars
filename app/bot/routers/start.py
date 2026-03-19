from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.bot.formatting import format_help_message, format_rules_message, format_start_message
from app.bot.utils import is_group_chat


router = Router(name="start")


@router.message(Command("start"))
async def start_handler(message: Message) -> None:
    await message.answer(format_start_message(is_group=is_group_chat(message)))


@router.message(Command("help"))
async def help_handler(message: Message) -> None:
    await message.answer(format_help_message())


@router.message(Command("rules"))
async def rules_handler(message: Message) -> None:
    await message.answer(format_rules_message())
