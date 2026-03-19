from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.db.models import Pig
from app.domain.exceptions import FeedCooldownError, PigAlreadyExistsError
from app.domain.services.battle_service import BattleQueueService
from app.domain.services.feeding_service import FeedingService
from app.domain.services.matchmaking_service import MatchmakingService
from app.domain.services.pig_service import PigService


@pytest.mark.asyncio
async def test_create_pig_rejects_duplicates(session, settings) -> None:
    service = PigService(
        session,
        feed_cooldown=settings.feed_cooldown,
        battle_cooldown=settings.battle_cooldown,
    )
    now = datetime(2026, 3, 19, tzinfo=timezone.utc)

    await service.create_pig(
        telegram_group_id=-10001,
        group_title="Pig Group",
        telegram_user_id=111,
        username="alpha",
        first_name="Alpha",
        last_name=None,
        pig_name="Baconator",
        now=now,
    )

    with pytest.raises(PigAlreadyExistsError):
        await service.create_pig(
            telegram_group_id=-10001,
            group_title="Pig Group",
            telegram_user_id=111,
            username="alpha",
            first_name="Alpha",
            last_name=None,
            pig_name="Another Pig",
            now=now,
        )


@pytest.mark.asyncio
async def test_feed_respects_cooldown(session, settings, rng, lock_manager) -> None:
    pig_service = PigService(
        session,
        feed_cooldown=settings.feed_cooldown,
        battle_cooldown=settings.battle_cooldown,
    )
    feed_service = FeedingService(
        session,
        feed_cooldown=settings.feed_cooldown,
        rng=rng,
        lock_manager=lock_manager,
    )
    now = datetime(2026, 3, 19, 12, 0, tzinfo=timezone.utc)

    await pig_service.create_pig(
        telegram_group_id=-10002,
        group_title="Feed Group",
        telegram_user_id=222,
        username="feeder",
        first_name="Feed",
        last_name="Master",
        pig_name="Crunch",
        now=now,
    )

    first = await feed_service.feed_pig(
        telegram_group_id=-10002,
        telegram_user_id=222,
        now=now,
    )
    assert first.current_weight > first.weight_gain

    with pytest.raises(FeedCooldownError):
        await feed_service.feed_pig(
            telegram_group_id=-10002,
            telegram_user_id=222,
            now=now + timedelta(minutes=30),
        )

    second = await feed_service.feed_pig(
        telegram_group_id=-10002,
        telegram_user_id=222,
        now=now + timedelta(minutes=61),
    )
    assert second.current_weight > first.current_weight


@pytest.mark.asyncio
async def test_matchmaking_runs_battle_and_updates_weights(session, settings, rng, lock_manager) -> None:
    pig_service = PigService(
        session,
        feed_cooldown=settings.feed_cooldown,
        battle_cooldown=settings.battle_cooldown,
    )
    queue_service = BattleQueueService(
        session,
        battle_cooldown=settings.battle_cooldown,
        battle_ready_ttl=settings.battle_ready_ttl,
        lock_manager=lock_manager,
    )
    matchmaking_service = MatchmakingService(
        session,
        settings=settings,
        rng=rng,
        lock_manager=lock_manager,
    )
    now = datetime(2026, 3, 19, 12, 0, tzinfo=timezone.utc)

    await pig_service.create_pig(
        telegram_group_id=-10003,
        group_title="Arena Group",
        telegram_user_id=333,
        username="pig1",
        first_name="Pig",
        last_name="One",
        pig_name="Hammer",
        now=now,
    )
    await pig_service.create_pig(
        telegram_group_id=-10003,
        group_title="Arena Group",
        telegram_user_id=444,
        username="pig2",
        first_name="Pig",
        last_name="Two",
        pig_name="Anvil",
        now=now,
    )

    await queue_service.enter_battle_mode(
        telegram_group_id=-10003,
        telegram_user_id=333,
        now=now,
    )
    await queue_service.enter_battle_mode(
        telegram_group_id=-10003,
        telegram_user_id=444,
        now=now,
    )

    battles = await matchmaking_service.process_matchmaking_cycle(now=now + timedelta(minutes=1))

    assert len(battles) == 1
    pigs = list((await session.scalars(select(Pig).order_by(Pig.name))).all())
    assert all(pig.status.value == "idle" for pig in pigs)
    assert sum(pig.wins for pig in pigs) == 1
    assert sum(pig.losses for pig in pigs) == 1
    assert sorted(str(pig.weight_kg) for pig in pigs) != ["10.00", "10.00"]
