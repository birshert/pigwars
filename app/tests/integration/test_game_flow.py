from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.db.models import Pig, PigDailyAction, PigEffect, PigEvent
from app.domain.exceptions import FeedCooldownError, PigAlreadyExistsError
from app.domain.feature_catalog import EFFECT_WET_NEWSPAPER_CURSE, ITEM_WET_NEWSPAPER, WORLD_EVENT_DIVINE_OINK, get_world_event_definition
from app.domain.models.pig import PigTrait, RaidDestination
from app.domain.services.battle_service import BattleQueueService
from app.domain.services.daily_feature_service import DailyFeatureService
from app.domain.services.feeding_service import FeedingService
from app.domain.services.item_service import ItemService
from app.domain.services.matchmaking_service import MatchmakingService
from app.domain.services.pig_service import PigService
from app.domain.services.raid_service import RaidService
from app.domain.services.sabotage_service import SabotageService
from app.domain.services import world_event_service as world_event_service_module
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
async def test_rename_pig_updates_name_and_logs_event(session, settings, rng) -> None:
    service = PigService(
        session,
        feed_cooldown=settings.feed_cooldown,
        battle_cooldown=settings.battle_cooldown,
        sabotage_cooldown=settings.sabotage_cooldown,
        raid_cooldown=settings.raid_cooldown,
        rng=rng,
    )
    now = datetime(2026, 3, 19, 10, 0, tzinfo=timezone.utc)

    await service.create_pig(
        telegram_group_id=-10009,
        group_title="Rename Group",
        telegram_user_id=3333,
        username="renamer",
        first_name="Rename",
        last_name=None,
        pig_name="Old Chunk",
        now=now,
    )

    result = await service.rename_pig(
        telegram_group_id=-10009,
        telegram_user_id=3333,
        new_name="  New   Chunk  ",
        now=now + timedelta(minutes=5),
    )

    pig = await session.scalar(select(Pig).where(Pig.name == "New Chunk"))
    assert pig is not None
    assert result.old_name == "Old Chunk"
    assert result.new_name == "New Chunk"
    assert result.changed is True

    rename_events = list((await session.scalars(select(PigEvent).where(PigEvent.event_type == "pig_renamed"))).all())
    assert len(rename_events) == 1
    assert rename_events[0].payload == {
        "old_name": "Old Chunk",
        "new_name": "New Chunk",
        "renamed_at": (now + timedelta(minutes=5)).isoformat(),
    }


@pytest.mark.asyncio
async def test_rename_pig_noop_when_name_is_unchanged(session, settings, rng) -> None:
    service = PigService(
        session,
        feed_cooldown=settings.feed_cooldown,
        battle_cooldown=settings.battle_cooldown,
        sabotage_cooldown=settings.sabotage_cooldown,
        raid_cooldown=settings.raid_cooldown,
        rng=rng,
    )
    now = datetime(2026, 3, 19, 10, 0, tzinfo=timezone.utc)

    await service.create_pig(
        telegram_group_id=-10010,
        group_title="Rename Same Group",
        telegram_user_id=4444,
        username="samepig",
        first_name="Same",
        last_name=None,
        pig_name="Steady",
        now=now,
    )

    result = await service.rename_pig(
        telegram_group_id=-10010,
        telegram_user_id=4444,
        new_name="  Steady ",
        now=now + timedelta(minutes=1),
    )

    assert result.changed is False
    rename_events = list((await session.scalars(select(PigEvent).where(PigEvent.event_type == "pig_renamed"))).all())
    assert rename_events == []


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
        rng=rng,
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
    assert results[0].owner_telegram_user_id == 555
    assert results[0].owner_mention_label == "@raider"

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


@pytest.mark.asyncio
async def test_daily_actions_assign_horoscope_and_are_idempotent(session, settings, rng) -> None:
    pig_service = PigService(
        session,
        feed_cooldown=settings.feed_cooldown,
        battle_cooldown=settings.battle_cooldown,
        sabotage_cooldown=settings.sabotage_cooldown,
        raid_cooldown=settings.raid_cooldown,
        rng=rng,
    )
    daily_service = DailyFeatureService(session, rng=random.Random(11))
    now = datetime(2026, 3, 19, 9, 0, tzinfo=timezone.utc)

    await pig_service.create_pig(
        telegram_group_id=-10006,
        group_title="Daily Group",
        telegram_user_id=999,
        username="dailypig",
        first_name="Daily",
        last_name=None,
        pig_name="Forecast",
        now=now,
    )

    overview = await daily_service.get_daily_view(
        telegram_group_id=-10006,
        telegram_user_id=999,
        now=now,
    )
    assert overview.horoscope_title
    assert overview.trough.available is True
    assert overview.wheel.available is True

    trough = await daily_service.use_trough(
        telegram_group_id=-10006,
        telegram_user_id=999,
        now=now,
    )
    repeat_trough = await daily_service.use_trough(
        telegram_group_id=-10006,
        telegram_user_id=999,
        now=now,
    )
    wheel = await daily_service.spin_shame_wheel(
        telegram_group_id=-10006,
        telegram_user_id=999,
        now=now,
    )

    actions = list((await session.scalars(select(PigDailyAction).order_by(PigDailyAction.id))).all())

    assert trough.result_title
    assert repeat_trough.already_used is True
    assert wheel.result_title
    assert sorted(action.action_type for action in actions) == [
        "daily_horoscope",
        "daily_shame_wheel",
        "daily_trough",
    ]


@pytest.mark.asyncio
async def test_wet_newspaper_applies_curse_and_loses_battle_charge(session, settings, rng, lock_manager) -> None:
    pig_service = PigService(
        session,
        feed_cooldown=settings.feed_cooldown,
        battle_cooldown=settings.battle_cooldown,
        sabotage_cooldown=settings.sabotage_cooldown,
        raid_cooldown=settings.raid_cooldown,
        rng=rng,
    )
    item_service = ItemService(session, rng=random.Random(13))
    queue_service = BattleQueueService(
        session,
        battle_cooldown=settings.battle_cooldown,
        battle_ready_ttl=settings.battle_ready_ttl,
        rng=random.Random(17),
        lock_manager=lock_manager,
    )
    matchmaking_service = MatchmakingService(
        session,
        settings=settings,
        rng=random.Random(19),
        lock_manager=lock_manager,
    )
    now = datetime(2026, 3, 19, 12, 0, tzinfo=timezone.utc)

    await pig_service.create_pig(
        telegram_group_id=-10007,
        group_title="Gazette Group",
        telegram_user_id=1010,
        username="paperboy",
        first_name="Paper",
        last_name=None,
        pig_name="Editor",
        now=now,
    )
    await pig_service.create_pig(
        telegram_group_id=-10007,
        group_title="Gazette Group",
        telegram_user_id=2020,
        username="victim",
        first_name="Victim",
        last_name=None,
        pig_name="Victimizer",
        now=now,
    )

    async with session.begin():
        attacker = await session.scalar(select(Pig).where(Pig.name == "Editor"))
        assert attacker is not None
        await item_service.award_item(
            pig=attacker,
            item_code=ITEM_WET_NEWSPAPER,
            now=now,
            source_type="test",
        )

    result = await item_service.use_item(
        telegram_group_id=-10007,
        telegram_user_id=1010,
        slot=1,
        target_telegram_user_id=2020,
        now=now,
    )
    assert "Victimizer" in result.outcome_text

    effect = await session.scalar(select(PigEffect).where(PigEffect.effect_type == EFFECT_WET_NEWSPAPER_CURSE))
    assert effect is not None
    assert effect.payload == {"remaining_battles": 3, "attacker_pig_id": str(attacker.id)}
    await session.commit()

    await queue_service.enter_battle_mode(
        telegram_group_id=-10007,
        telegram_user_id=1010,
        now=now,
    )
    await queue_service.enter_battle_mode(
        telegram_group_id=-10007,
        telegram_user_id=2020,
        now=now,
    )

    battles = await matchmaking_service.process_matchmaking_cycle(now=now + timedelta(minutes=1))
    assert len(battles) == 1

    updated = await session.scalar(select(PigEffect).where(PigEffect.effect_type == EFFECT_WET_NEWSPAPER_CURSE))
    assert updated is not None
    assert updated.payload["remaining_battles"] == 2


@pytest.mark.asyncio
async def test_divine_oink_uses_special_duration_and_announcement(session, settings, monkeypatch) -> None:
    definition = get_world_event_definition(WORLD_EVENT_DIVINE_OINK)
    service = WorldEventService(session, settings=settings, rng=random.Random(23))
    now = datetime(2026, 3, 19, 18, 0, tzinfo=timezone.utc)

    monkeypatch.setattr(
        world_event_service_module,
        "pick_next_world_event",
        lambda *, rng, previous_code=None: definition,
    )

    async with session.begin():
        event = await service.ensure_active_event(now=now)
        announcement = service.build_announcement(event)

    assert event.event_code == WORLD_EVENT_DIVINE_OINK
    assert event.ends_at == now + timedelta(hours=2)
    assert "Великая Свинья" in announcement
