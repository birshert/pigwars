from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from app.bootstrap import AppContext
from app.bot.keyboards.admin import build_admin_dashboard_keyboard
from app.bot.utils import is_group_chat
from app.daily_digest import list_due_digest_groups, send_digest_for_group
from app.db.base import session_scope
from app.db.repositories.group_repo import GroupRepository
from app.domain.rules.timezones import get_game_day
from app.infra.ngrok import resolve_admin_mini_app_url


ADMIN_TELEGRAM_USER_ID = 241301944
MANUAL_DIGEST_GROUP_LIMIT = 1000


router = Router(name="admin")


def _is_admin_user(app_context: AppContext, telegram_user_id: int) -> bool:
    settings = getattr(app_context, "settings", None)
    settings_match = bool(
        settings is not None and settings.is_admin_telegram_user(telegram_user_id)
    )
    return (
        settings_match
        or telegram_user_id == ADMIN_TELEGRAM_USER_ID
    )


@router.message(Command("admin"))
async def admin_dashboard_handler(message: Message, app_context: AppContext) -> None:
    if message.chat.type != "private":
        await message.answer("Админ-панель открывается только в личке с ботом.")
        return
    if message.from_user is None or not _is_admin_user(app_context, message.from_user.id):
        await message.answer("У тебя нет доступа к админ-панели.")
        return
    admin_url = await asyncio.to_thread(resolve_admin_mini_app_url, app_context.settings)
    if not admin_url:
        await message.answer(
            "Не удалось определить публичный URL админки. "
            "Либо задай MINI_APP_URL, либо запусти ngrok на 8080."
        )
        return

    await message.answer(
        "Открыть админ-дашборд PigWars:",
        reply_markup=build_admin_dashboard_keyboard(admin_url),
    )


@router.message(Command("admin_digest"))
async def admin_digest_handler(
    message: Message,
    command: CommandObject,
    app_context: AppContext,
) -> None:
    if is_group_chat(message):
        await message.answer("Эта команда работает только в личке.")
        return
    if message.chat.type != "private":
        await message.answer("Эта команда работает только в личке.")
        return
    if message.from_user is None or not _is_admin_user(app_context, message.from_user.id):
        await message.answer("Команда недоступна.")
        return

    now = datetime.now(timezone.utc)
    digest_day = get_game_day(now)

    if command.args:
        group = await _resolve_group(app_context, command.args.strip())
        if group is None:
            await message.answer("Использование: /admin_digest <telegram_group_id> или просто /admin_digest для всех групп.")
            return
        results = [await send_digest_for_group(app_context, group=group, digest_day=digest_day, now=now)]
    else:
        groups = await list_due_digest_groups(
            app_context,
            digest_day=digest_day,
            now=now,
            limit=MANUAL_DIGEST_GROUP_LIMIT,
        )
        if not groups:
            await message.answer(f"За {digest_day.strftime('%d.%m')} нет групп, которым сейчас нужен ручной digest.")
            return
        results = [
            await send_digest_for_group(app_context, group=group, digest_day=digest_day, now=now)
            for group in groups
        ]

    sent = [result for result in results if result.status == "sent"]
    skipped = [result for result in results if result.status == "skipped"]
    failed = [result for result in results if result.status == "failed"]

    lines = [
        f"Хрюкодайджест за {digest_day.strftime('%d.%m')}:",
        f"Отправлено: {len(sent)}",
        f"Пропущено: {len(skipped)}",
        f"Ошибок: {len(failed)}",
    ]
    if sent:
        lines.append("")
        lines.append("Ушло в группы:")
        for result in sent[:10]:
            lines.append(f"• {result.group_title} ({result.telegram_group_id})")
    if failed:
        lines.append("")
        lines.append("Ошибки:")
        for result in failed[:5]:
            lines.append(f"• {result.group_title}: {result.reason}")
    if skipped:
        lines.append("")
        lines.append("Пропущено:")
        for result in skipped[:5]:
            suffix = f" ({result.reason})" if result.reason else ""
            lines.append(f"• {result.group_title}{suffix}")

    await message.answer("\n".join(lines))


async def _resolve_group(app_context: AppContext, raw_group_id: str):
    try:
        telegram_group_id = int(raw_group_id)
    except ValueError:
        return None

    async with session_scope(app_context.session_factory) as session:
        return await GroupRepository(session).get_by_telegram_id(telegram_group_id)
