from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.db.models import Pig, PigEffect
from app.domain.exceptions import FeedCooldownError, PigAlreadyExistsError
from app.domain.models.pig import PigTrait, RaidDestination
from app.domain.services.battle_service import BattleQueueService
from app.domain.services.feeding_service import FeedingService
from app.domain.services.matchmaking_service import MatchmakingService
from app.domain.services.pig_service import PigService
from app.domain.services.raid_service import RaidService
from app.domain.services.sabotage_service import SabotageService
from app.domain.services.world_event_service import WorldEventService


@pytest.mark.asyncio
async def test_create_pig_rejects_duplicates(session, settings, rng) -> None:
    service = PigService(
        session,
        feed_cooldown=settings.feed_cooldown,
        battle_cooldown=settings.battle_cooldown,
        sabotage_cooldown=settings.sabotage_cooldown,
        raid_cooldown=settings.raid_cooldown,
        rng=rng,
    )
    now = datetime(2026, 3, 19, tzinfo=timezone.utc)

    profile = await service.create_pig(
        telegram_group_id=-10001,
        group_title="Pig Group",
        telegram_user_id=111,
        username="alpha",
        first_name="Alpha",
        last_name=None,
        pig_name="Baconator",
        now=now,
    )
    assert profile.trait_title

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
        sabotage_cooldown=settings.sabotage_cooldown,
        raid_cooldown=settings.raid_cooldown,
        rng=rng,
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


@pytest.mark.asyncio
async def test_raid_resolution_returns_pig_to_idle(session, settings, rng) -> None:
    pig_service = PigService(
        session,
        feed_cooldown=settings.feed_cooldown,
        battle_cooldown=settings.battle_cooldown,
        sabotage_cooldown=settings.sabotage_cooldown,
        raid_cooldown=settings.raid_cooldown,
        rng=rng,
    )
    raid_service = RaidService(session, settings=settings, rng=rng)
    now = datetime(2026, 3, 19, 12, 0, tzinfo=timezone.utc)

    await pig_service.create_pig(
        telegram_group_id=-10004,
        group_title="Raid Group",
        telegram_user_id=555,
        username="raider",
        first_name="Raid",
        last_name="Runner",
        pig_name="Scout",
        now=now,
    )

    start = await raid_service.start_raid(
        telegram_group_id=-10004,
        telegram_user_id=555,
        destination=RaidDestination.MARKET,
        now=now,
    )
    assert start.destination_title
    assert start.resolve_at == now + timedelta(minutes=10)

    results = await raid_service.resolve_due_raids(now=now + settings.raid_duration + timedelta(minutes=1))
    assert len(results) == 1

    pig = await session.scalar(select(Pig).where(Pig.name == "Scout"))
    assert pig is not None
    assert pig.status.value == "idle"
    assert pig.raid_until is None


@pytest.mark.asyncio
async def test_sabotage_applies_temporary_effect(session, settings, rng) -> None:
    pig_service = PigService(
        session,
        feed_cooldown=settings.feed_cooldown,
        battle_cooldown=settings.battle_cooldown,
        sabotage_cooldown=settings.sabotage_cooldown,
        raid_cooldown=settings.raid_cooldown,
        rng=rng,
    )
    now = datetime(2026, 3, 19, 12, 0, tzinfo=timezone.utc)

    await pig_service.create_pig(
        telegram_group_id=-10005,
        group_title="Sabotage Group",
        telegram_user_id=777,
        username="attacker",
        first_name="Attack",
        last_name=None,
        pig_name="Sneak",
        now=now,
    )
    await pig_service.create_pig(
        telegram_group_id=-10005,
        group_title="Sabotage Group",
        telegram_user_id=888,
        username="target",
        first_name="Target",
        last_name=None,
        pig_name="Brick",
        now=now,
    )

    pigs = list((await session.scalars(select(Pig).order_by(Pig.name))).all())
    by_name = {pig.name: pig for pig in pigs}
    by_name["Sneak"].trait = PigTrait.CUNNING
    by_name["Sneak"].mood_score = 100
    by_name["Brick"].loyalty = 0
    await session.commit()

    sabotage_service = SabotageService(session, settings=settings, rng=random.Random(1))
    result = await sabotage_service.sabotage(
        telegram_group_id=-10005,
        attacker_telegram_user_id=777,
        target_telegram_user_id=888,
        now=now,
    )

    assert result.success is True
    active_effects = list((await session.scalars(select(PigEffect))).all())
    assert active_effects


@pytest.mark.asyncio
async def test_world_event_is_created_and_visible(session, settings) -> None:
    service = WorldEventService(session, settings=settings, rng=random.Random(2))
    now = datetime(2026, 3, 19, 12, 0, tzinfo=timezone.utc)

    async with session.begin():
        view = await service.get_current_view(now=now)

    assert view.title
    assert view.effects
