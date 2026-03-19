from __future__ import annotations

from aiogram.types import Message


GROUP_CHAT_TYPES = {"group", "supergroup"}


def is_group_chat(message: Message) -> bool:
    return message.chat.type in GROUP_CHAT_TYPES
