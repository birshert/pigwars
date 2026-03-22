from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from aiogram.exceptions import TelegramMigrateToChat
from aiogram.methods import SendMessage
from sqlalchemy import select, update

from app.bot.formatting import format_daily_digest_message
from app.bot.routers import admin as admin_router_module
from app.db.models import Battle, GroupDailyDigest, PigEvent
from app.db.repositories.world_event_repo import WorldEventRepository
from app.daily_digest import DailyDigestDispatchResult, send_digest_for_group
from app.domain.models.daily_digest import DailyDigestStatus
from app.domain.services.battle_service import BattleQueueService
from app.domain.services.daily_digest_facts_service import DailyDigestFactsService
from app.domain.services.matchmaking_service import MatchmakingService
from app.domain.services.pig_service import PigService
from app.domain.services.feeding_service import FeedingService
from app.schemas.disease import DiseaseAnnouncement
from app.worker import run_worker_tick
from app import worker as worker_module


class FakeBot:
    def __init__(self) -> None:
        self.messages: list[tuple[int, str, dict[str, object]]] = []

    async def send_message(self, chat_id: int, text: str, **kwargs):
        self.messages.append((chat_id, text, kwargs))
        return SimpleNamespace(message_id=len(self.messages))


class FakePrivateMessage:
    def __init__(self, user_id: int) -> None:
        self.chat = SimpleNamespace(id=user_id, type="private", title=None)
        self.from_user = SimpleNamespace(id=user_id)
        self.answers: list[str] = []

    async def answer(self, text: str) -> None:
        self.answers.append(text)


@pytest.mark.asyncio
async def test_daily_digest_facts_collect_counts_and_message(session, settings, rng, lock_manager) -> None:
    pig_service = PigService(
        session,
        feed_cooldown=settings.feed_cooldown,
        battle_cooldown=settings.battle_cooldown,
        sabotage_cooldown=settings.sabotage_cooldown,
        raid_cooldown=settings.raid_cooldown,
        rng=rng,
    )
    feed_service = FeedingService(
        session,
        feed_cooldown=settings.feed_cooldown,
        rng=rng,
        lock_manager=lock_manager,
    )
    queue_service = BattleQueueService(
        session,
        battle_cooldown=settings.battle_cooldown,
        battle_ready_ttl=settings.battle_ready_ttl,
        rng=rng,
        lock_manager=lock_manager,
    )
    matchmaking_service = MatchmakingService(
        session,
        settings=settings,
        rng=rng,
        lock_manager=lock_manager,
    )
    now = datetime(2026, 3, 18, 10, 0, tzinfo=timezone.utc)

    await pig_service.create_pig(
        telegram_group_id=-10100,
        group_title="Digest Group",
        telegram_user_id=1001,
        username="alpha",
        first_name="Alpha",
        last_name=None,
        pig_name="Пятачелло",
        now=now,
    )
    await pig_service.create_pig(
        telegram_group_id=-10100,
        group_title="Digest Group",
        telegram_user_id=1002,
        username="beta",
        first_name="Beta",
        last_name=None,
        pig_name="Хряпыч",
        now=now,
    )

    await feed_service.feed_pig(
        telegram_group_id=-10100,
        telegram_user_id=1001,
        now=now + timedelta(minutes=1),
    )
    await feed_service.feed_pig(
        telegram_group_id=-10100,
        telegram_user_id=1002,
        now=now + timedelta(minutes=2),
    )
    await queue_service.enter_battle_mode(
        telegram_group_id=-10100,
        telegram_user_id=1001,
        now=now + timedelta(minutes=3),
    )
    await queue_service.enter_battle_mode(
        telegram_group_id=-10100,
        telegram_user_id=1002,
        now=now + timedelta(minutes=3),
    )
    await matchmaking_service.process_matchmaking_cycle(now=now + timedelta(minutes=4))
    await session.execute(update(PigEvent).values(created_at=now + timedelta(hours=1)))
    await session.execute(update(Battle).values(created_at=now + timedelta(hours=1, minutes=5)))
    await session.commit()

    group_id = await session.scalar(select(Battle.group_id).limit(1))
    assert group_id is not None

    facts = await DailyDigestFactsService(session).build_for_group(
        group_id=group_id,
        digest_day=now.date(),
        now=now + timedelta(hours=12),
    )

    assert facts.counts.battles == 1
    assert facts.counts.feeds == 2
    assert facts.counts.new_pigs == 2
    assert facts.leaderboard[0].pig_name in {"Пятачелло", "Хряпыч"}
    assert any(highlight.type == "top_gain" for highlight in facts.highlights)

    message = format_daily_digest_message(facts, "Вчера в загоне было шумно и жирно.")
    assert "🌅 Хрюкодайджест за 18.03" in message
    assert "Текущий топ по весу:" in message


@pytest.mark.asyncio
async def test_worker_sends_daily_digest_once(session_factory, settings, rng, lock_manager, monkeypatch) -> None:
    settings.daily_digest_enabled = True
    settings.daily_digest_hour_msk = 9
    settings.daily_digest_group_allowlist = (-10101,)
    settings.disease_enabled = False

    fixed_now = datetime(2026, 3, 19, 6, 5, tzinfo=timezone.utc)

    async with session_factory() as session:
        pig_service = PigService(
            session,
            feed_cooldown=settings.feed_cooldown,
            battle_cooldown=settings.battle_cooldown,
            sabotage_cooldown=settings.sabotage_cooldown,
            raid_cooldown=settings.raid_cooldown,
            rng=rng,
        )
        await pig_service.create_pig(
            telegram_group_id=-10101,
            group_title="Worker Digest Group",
            telegram_user_id=2001,
            username="worker",
            first_name="Worker",
            last_name=None,
            pig_name="Беконтий",
            now=fixed_now - timedelta(days=1, hours=1),
        )
        await pig_service.create_pig(
            telegram_group_id=-10102,
            group_title="Blocked Digest Group",
            telegram_user_id=2002,
            username="blocked",
            first_name="Blocked",
            last_name=None,
            pig_name="Молчаливчик",
            now=fixed_now - timedelta(days=1, hours=1),
        )

        world_repo = WorldEventRepository(session)
        async with session.begin():
            event = await world_repo.create(
                event_code="divine_oink",
                title="Тестовая ярмарка",
                description="Просто висит и не шумит.",
                starts_at=fixed_now - timedelta(hours=2),
                ends_at=fixed_now + timedelta(hours=8),
                modifiers={"code": "divine_oink"},
            )
            await world_repo.mark_announced(event, now=fixed_now - timedelta(minutes=1))

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            if tz is None:
                return fixed_now.replace(tzinfo=None)
            return fixed_now.astimezone(tz)

    monkeypatch.setattr(worker_module, "datetime", FrozenDateTime)

    fake_bot = FakeBot()
    app_context = SimpleNamespace(
        settings=settings,
        bot=fake_bot,
        lock_manager=lock_manager,
        rng=rng,
        session_factory=session_factory,
    )

    await run_worker_tick(app_context)
    await run_worker_tick(app_context)

    assert len(fake_bot.messages) == 1
    assert fake_bot.messages[0][0] == -10101
    assert "🌅 Хрюкодайджест за 18.03" in fake_bot.messages[0][1]

    async with session_factory() as session:
        digests = list((await session.scalars(select(GroupDailyDigest))).all())

    assert len(digests) == 1
    assert digests[0].status == DailyDigestStatus.SENT
    assert digests[0].telegram_message_id == 1


@pytest.mark.asyncio
async def test_send_digest_for_group_skips_disallowed_group(settings) -> None:
    settings.daily_digest_group_allowlist = (-1003740637751, -1003758467163)
    app_context = SimpleNamespace(settings=settings)
    group = SimpleNamespace(id=1, title="Blocked Group", telegram_group_id=-1009999999999)

    result = await send_digest_for_group(
        app_context,
        group=group,
        digest_day=datetime(2026, 3, 21, tzinfo=timezone.utc).date(),
        now=datetime(2026, 3, 22, 6, 0, tzinfo=timezone.utc),
    )

    assert result.status == "skipped"
    assert result.reason == "group_not_allowed"
    assert result.telegram_group_id == -1009999999999


@pytest.mark.asyncio
async def test_admin_digest_handler_runs_from_private_chat(monkeypatch) -> None:
    async def fake_list_due_groups(app_context, *, digest_day, now, limit):
        return [SimpleNamespace(id=1, title="Manual Group", telegram_group_id=-10123)]

    async def fake_send_digest(app_context, *, group, digest_day, now):
        return DailyDigestDispatchResult(
            group_title=group.title,
            telegram_group_id=group.telegram_group_id,
            digest_day=digest_day,
            status="sent",
            message_id=77,
        )

    monkeypatch.setattr(admin_router_module, "list_due_digest_groups", fake_list_due_groups)
    monkeypatch.setattr(admin_router_module, "send_digest_for_group", fake_send_digest)

    message = FakePrivateMessage(user_id=241301944)
    command = SimpleNamespace(args=None)
    app_context = SimpleNamespace()

    await admin_router_module.admin_digest_handler(message, command, app_context)

    assert len(message.answers) == 1
    assert "Отправлено: 1" in message.answers[0]
    assert "Manual Group" in message.answers[0]


@pytest.mark.asyncio
async def test_admin_disease_handler_runs_from_private_chat(monkeypatch) -> None:
    class FakeDiseaseService:
        def __init__(self, session, *, settings, rng) -> None:
            return None

        async def trigger_manual_disease(self, *, now, group_id=None):
            return DiseaseAnnouncement(
                roll_id=1,
                telegram_group_id=-10123,
                text="🤒 Тестовая свинья словила тестовую болезнь.",
                group_title="Manual Group",
            )

    @asynccontextmanager
    async def fake_session_scope(session_factory):
        yield SimpleNamespace()

    monkeypatch.setattr(admin_router_module, "DiseaseService", FakeDiseaseService)
    monkeypatch.setattr(admin_router_module, "session_scope", fake_session_scope)

    message = FakePrivateMessage(user_id=241301944)
    command = SimpleNamespace(args=None)
    fake_bot = FakeBot()
    app_context = SimpleNamespace(
        settings=SimpleNamespace(is_admin_telegram_user=lambda telegram_user_id: telegram_user_id == 241301944),
        bot=fake_bot,
        rng=None,
        session_factory=object(),
    )

    await admin_router_module.admin_disease_handler(message, command, app_context)

    assert len(fake_bot.messages) == 1
    assert fake_bot.messages[0][0] == -10123
    assert "тестовую болезнь" in fake_bot.messages[0][1]
    assert len(message.answers) == 1
    assert "Болезнь запущена вручную." in message.answers[0]
    assert "Manual Group" in message.answers[0]


@pytest.mark.asyncio
async def test_admin_disease_handler_retries_migrated_group(monkeypatch) -> None:
    class FakeDiseaseService:
        def __init__(self, session, *, settings, rng) -> None:
            return None

        async def trigger_manual_disease(self, *, now, group_id=None):
            return DiseaseAnnouncement(
                roll_id=1,
                telegram_group_id=-4630268163,
                text="🤒 Тестовая свинья словила тестовую болезнь.",
                group_title="Migrated Group",
            )

    class MigratingBot(FakeBot):
        async def send_message(self, chat_id: int, text: str, **kwargs):
            if chat_id == -4630268163:
                raise TelegramMigrateToChat(
                    SendMessage(chat_id=chat_id, text=text),
                    "group chat was upgraded to a supergroup chat",
                    -1003733861005,
                )
            return await super().send_message(chat_id, text, **kwargs)

    @asynccontextmanager
    async def fake_session_scope(session_factory):
        yield SimpleNamespace()

    monkeypatch.setattr(admin_router_module, "DiseaseService", FakeDiseaseService)
    monkeypatch.setattr(admin_router_module, "session_scope", fake_session_scope)

    message = FakePrivateMessage(user_id=241301944)
    command = SimpleNamespace(args=None)
    fake_bot = MigratingBot()
    app_context = SimpleNamespace(
        settings=SimpleNamespace(is_admin_telegram_user=lambda telegram_user_id: telegram_user_id == 241301944),
        bot=fake_bot,
        rng=None,
        session_factory=object(),
    )

    await admin_router_module.admin_disease_handler(message, command, app_context)

    assert len(fake_bot.messages) == 1
    assert fake_bot.messages[0][0] == -1003733861005
    assert len(message.answers) == 1
    assert "-1003733861005" in message.answers[0]
