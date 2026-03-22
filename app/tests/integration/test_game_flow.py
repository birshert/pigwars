from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.db.models import GroupDiseaseRoll, Pig, PigDailyAction, PigEffect, PigEvent
from app.domain.disease_catalog import DISEASE_FEED_COLD, DISEASE_QUARANTINE_SCREAM, get_disease_definition
from app.domain.exceptions import FeedCooldownError, PigAlreadyExistsError, PigBusyError
from app.domain.feature_catalog import EFFECT_WET_NEWSPAPER_CURSE, ITEM_WET_NEWSPAPER, WORLD_EVENT_DIVINE_OINK, get_world_event_definition
from app.domain.models.pig import PigTrait, RaidDestination
from app.domain.services.battle_service import BattleQueueService
from app.domain.services.daily_feature_service import DailyFeatureService
from app.domain.services.disease_service import DiseaseService
from app.domain.services.feeding_service import FeedingService
from app.domain.services.item_service import ItemService
from app.domain.services.matchmaking_service import MatchmakingService
from app.domain.services.pig_service import PigService
from app.domain.services.raid_service import RaidService
from app.domain.services.sabotage_service import SabotageService
from app.domain.services import disease_service as disease_service_module
from app.domain.services import world_event_service as world_event_service_module
from app.domain.services.world_event_service import WorldEventService


async def _set_pig_weights(session, weights_by_name: dict[str, Decimal]) -> None:
    pigs = list((await session.scalars(select(Pig).where(Pig.name.in_(tuple(weights_by_name))))).all())
    assert len(pigs) == len(weights_by_name)
    for pig in pigs:
        pig.weight_kg = weights_by_name[pig.name]
    await session.commit()


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
async def test_matchmaking_prefers_nearest_weight_pairs(session, settings, lock_manager) -> None:
    pig_service = PigService(
        session,
        feed_cooldown=settings.feed_cooldown,
        battle_cooldown=settings.battle_cooldown,
        sabotage_cooldown=settings.sabotage_cooldown,
        raid_cooldown=settings.raid_cooldown,
        rng=random.Random(1),
    )
    queue_service = BattleQueueService(
        session,
        battle_cooldown=settings.battle_cooldown,
        battle_ready_ttl=settings.battle_ready_ttl,
        rng=random.Random(2),
        lock_manager=lock_manager,
    )
    matchmaking_service = MatchmakingService(
        session,
        settings=settings,
        rng=random.Random(3),
        lock_manager=lock_manager,
    )
    now = datetime(2026, 3, 19, 13, 0, tzinfo=timezone.utc)

    for telegram_user_id, pig_name in (
        (501, "Feather"),
        (502, "Fluff"),
        (503, "Brick"),
        (504, "Boulder"),
    ):
        await pig_service.create_pig(
            telegram_group_id=-10010,
            group_title="Matchmaking Group",
            telegram_user_id=telegram_user_id,
            username=f"user{telegram_user_id}",
            first_name=pig_name,
            last_name=None,
            pig_name=pig_name,
            now=now,
        )

    await _set_pig_weights(
        session,
        {
            "Feather": Decimal("10.00"),
            "Fluff": Decimal("11.20"),
            "Brick": Decimal("24.00"),
            "Boulder": Decimal("25.10"),
        },
    )

    for telegram_user_id in (501, 502, 503, 504):
        await queue_service.enter_battle_mode(
            telegram_group_id=-10010,
            telegram_user_id=telegram_user_id,
            now=now,
        )

    pigs = list((await session.scalars(select(Pig))).all())
    group_id = pigs[0].group_id
    pairs = await matchmaking_service.find_candidate_pairs(group_id=group_id, now=now + timedelta(minutes=1))
    pig_names = {pig.id: pig.name for pig in pigs}
    pair_names = {frozenset((pig_names[first], pig_names[second])) for first, second in pairs}

    assert pair_names == {
        frozenset(("Feather", "Fluff")),
        frozenset(("Brick", "Boulder")),
    }


@pytest.mark.asyncio
async def test_matchmaking_waits_for_expanded_weight_corridor(session, settings, lock_manager) -> None:
    pig_service = PigService(
        session,
        feed_cooldown=settings.feed_cooldown,
        battle_cooldown=settings.battle_cooldown,
        sabotage_cooldown=settings.sabotage_cooldown,
        raid_cooldown=settings.raid_cooldown,
        rng=random.Random(4),
    )
    queue_service = BattleQueueService(
        session,
        battle_cooldown=settings.battle_cooldown,
        battle_ready_ttl=settings.battle_ready_ttl,
        rng=random.Random(5),
        lock_manager=lock_manager,
    )
    matchmaking_service = MatchmakingService(
        session,
        settings=settings,
        rng=random.Random(6),
        lock_manager=lock_manager,
    )
    now = datetime(2026, 3, 19, 14, 0, tzinfo=timezone.utc)

    for telegram_user_id, pig_name in ((601, "Small"), (602, "Large")):
        await pig_service.create_pig(
            telegram_group_id=-10011,
            group_title="Corridor Group",
            telegram_user_id=telegram_user_id,
            username=f"user{telegram_user_id}",
            first_name=pig_name,
            last_name=None,
            pig_name=pig_name,
            now=now,
        )

    await _set_pig_weights(
        session,
        {
            "Small": Decimal("10.00"),
            "Large": Decimal("20.00"),
        },
    )

    for telegram_user_id in (601, 602):
        await queue_service.enter_battle_mode(
            telegram_group_id=-10011,
            telegram_user_id=telegram_user_id,
            now=now,
        )

    pigs = list((await session.scalars(select(Pig))).all())
    group_id = pigs[0].group_id

    assert await matchmaking_service.find_candidate_pairs(group_id=group_id, now=now + timedelta(minutes=3)) == []

    pairs = await matchmaking_service.find_candidate_pairs(group_id=group_id, now=now + timedelta(minutes=5))
    assert len(pairs) == 1


@pytest.mark.asyncio
async def test_fallback_match_applies_new_transfer_rules_and_telemetry(session, settings, lock_manager) -> None:
    pig_service = PigService(
        session,
        feed_cooldown=settings.feed_cooldown,
        battle_cooldown=settings.battle_cooldown,
        sabotage_cooldown=settings.sabotage_cooldown,
        raid_cooldown=settings.raid_cooldown,
        rng=random.Random(7),
    )
    queue_service = BattleQueueService(
        session,
        battle_cooldown=settings.battle_cooldown,
        battle_ready_ttl=settings.battle_ready_ttl,
        rng=random.Random(8),
        lock_manager=lock_manager,
    )
    matchmaking_service = MatchmakingService(
        session,
        settings=settings,
        rng=random.Random(9),
        lock_manager=lock_manager,
    )
    now = datetime(2026, 3, 19, 15, 0, tzinfo=timezone.utc)

    for telegram_user_id, pig_name in ((701, "Tiny"), (702, "Titan")):
        await pig_service.create_pig(
            telegram_group_id=-10012,
            group_title="Fallback Group",
            telegram_user_id=telegram_user_id,
            username=f"user{telegram_user_id}",
            first_name=pig_name,
            last_name=None,
            pig_name=pig_name,
            now=now,
        )

    await _set_pig_weights(
        session,
        {
            "Tiny": Decimal("10.00"),
            "Titan": Decimal("20.00"),
        },
    )

    for telegram_user_id in (701, 702):
        await queue_service.enter_battle_mode(
            telegram_group_id=-10012,
            telegram_user_id=telegram_user_id,
            now=now,
        )

    battles = await matchmaking_service.process_matchmaking_cycle(now=now + timedelta(minutes=5))
    assert len(battles) == 1

    pigs = list((await session.scalars(select(Pig).order_by(Pig.name))).all())
    by_name = {pig.name: pig for pig in pigs}
    winner = by_name["Tiny"] if by_name["Tiny"].wins == 1 else by_name["Titan"]
    loser = by_name["Titan"] if winner.name == "Tiny" else by_name["Tiny"]

    if winner.name == "Titan":
        assert winner.weight_kg == Decimal("20.07")
        assert loser.weight_kg == Decimal("9.64")
        expected_transfer_multiplier = "0.1500"
        expected_winner_was_underdog = False
    else:
        assert winner.weight_kg == Decimal("10.75")
        assert loser.weight_kg == Decimal("19.31")
        expected_transfer_multiplier = "1.5525"
        expected_winner_was_underdog = True

    battle_events = list(
        (
            await session.scalars(
                select(PigEvent)
                .where(PigEvent.event_type.in_(("battle_won", "battle_lost")))
                .order_by(PigEvent.event_type.asc(), PigEvent.id.asc())
            )
        ).all()
    )
    assert len(battle_events) == 2

    for event in battle_events:
        assert event.payload is not None
        assert event.payload["matchup_class"] == "stomp"
        assert event.payload["weight_ratio"] == "2.00"
        assert event.payload["winner_was_underdog"] is expected_winner_was_underdog
        assert event.payload["transfer_multiplier"] == expected_transfer_multiplier


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


@pytest.mark.asyncio
async def test_disease_slot_applies_effect_and_is_idempotent(session, settings, rng, monkeypatch) -> None:
    pig_service = PigService(
        session,
        feed_cooldown=settings.feed_cooldown,
        battle_cooldown=settings.battle_cooldown,
        sabotage_cooldown=settings.sabotage_cooldown,
        raid_cooldown=settings.raid_cooldown,
        rng=rng,
    )
    settings.disease_day_chance = 1.0
    settings.openai_api_key = None
    definition = get_disease_definition(DISEASE_FEED_COLD)
    now = datetime(2026, 3, 20, 6, 0, tzinfo=timezone.utc)

    monkeypatch.setattr(
        disease_service_module,
        "pick_disease_definition",
        lambda *, rng: definition,
    )

    await pig_service.create_pig(
        telegram_group_id=-10008,
        group_title="Disease Group",
        telegram_user_id=3030,
        username="sickpig",
        first_name="Sick",
        last_name=None,
        pig_name="Snort",
        now=now - timedelta(hours=1),
    )

    service = DiseaseService(session, settings=settings, rng=random.Random(31))
    announcements = await service.process_current_slot(now=now)
    repeated = await service.process_current_slot(now=now)

    pig = await session.scalar(select(Pig).where(Pig.name == "Snort"))
    effect = await session.scalar(select(PigEffect).where(PigEffect.effect_type == definition.effect_type))
    rolls = list((await session.scalars(select(GroupDiseaseRoll).order_by(GroupDiseaseRoll.id))).all())

    assert len(announcements) == 1
    assert repeated == []
    assert pig is not None
    assert pig.status.value == "idle"
    assert pig.weight_kg < 10
    assert effect is not None
    assert len(rolls) == 1
    assert rolls[0].disease_code == definition.code
    assert "Snort" in announcements[0].text
    assert definition.title in announcements[0].text


@pytest.mark.asyncio
async def test_disease_quarantine_blocks_actions_and_expires(session, settings, rng, lock_manager, monkeypatch) -> None:
    pig_service = PigService(
        session,
        feed_cooldown=settings.feed_cooldown,
        battle_cooldown=settings.battle_cooldown,
        sabotage_cooldown=settings.sabotage_cooldown,
        raid_cooldown=settings.raid_cooldown,
        rng=rng,
    )
    settings.disease_day_chance = 1.0
    settings.openai_api_key = None
    definition = get_disease_definition(DISEASE_QUARANTINE_SCREAM)
    now = datetime(2026, 3, 20, 6, 0, tzinfo=timezone.utc)

    monkeypatch.setattr(
        disease_service_module,
        "pick_disease_definition",
        lambda *, rng: definition,
    )

    await pig_service.create_pig(
        telegram_group_id=-10011,
        group_title="Quarantine Group",
        telegram_user_id=4040,
        username="quarantine",
        first_name="Quarantine",
        last_name=None,
        pig_name="Isolate",
        now=now - timedelta(hours=2),
    )

    disease_service = DiseaseService(session, settings=settings, rng=random.Random(33))
    await disease_service.process_current_slot(now=now)

    pig = await session.scalar(select(Pig).where(Pig.name == "Isolate"))
    assert pig is not None
    assert pig.status.value == "quarantined"
    assert pig.quarantine_until is not None
    weight_after_disease = pig.weight_kg
    quarantine_until = pig.quarantine_until
    await session.commit()

    feed_service = FeedingService(
        session,
        feed_cooldown=settings.feed_cooldown,
        rng=random.Random(35),
        lock_manager=lock_manager,
    )
    with pytest.raises(PigBusyError):
        await feed_service.feed_pig(
            telegram_group_id=-10011,
            telegram_user_id=4040,
            now=now + timedelta(minutes=15),
        )

    released = await disease_service.expire_quarantines(now=quarantine_until + timedelta(minutes=1))
    assert released == 1

    fed = await feed_service.feed_pig(
        telegram_group_id=-10011,
        telegram_user_id=4040,
        now=quarantine_until + timedelta(minutes=1),
    )
    assert fed.current_weight > weight_after_disease


@pytest.mark.asyncio
async def test_disease_service_skips_non_slot_hours(session, settings, rng) -> None:
    pig_service = PigService(
        session,
        feed_cooldown=settings.feed_cooldown,
        battle_cooldown=settings.battle_cooldown,
        sabotage_cooldown=settings.sabotage_cooldown,
        raid_cooldown=settings.raid_cooldown,
        rng=rng,
    )
    settings.disease_day_chance = 1.0
    settings.openai_api_key = None
    now = datetime(2026, 3, 20, 7, 0, tzinfo=timezone.utc)

    await pig_service.create_pig(
        telegram_group_id=-10012,
        group_title="Quiet Group",
        telegram_user_id=5050,
        username="quietpig",
        first_name="Quiet",
        last_name=None,
        pig_name="Calm",
        now=now - timedelta(hours=1),
    )

    service = DiseaseService(session, settings=settings, rng=random.Random(37))
    announcements = await service.process_current_slot(now=now)
    rolls = list((await session.scalars(select(GroupDiseaseRoll))).all())

    assert announcements == []
    assert rolls == []


@pytest.mark.asyncio
async def test_manual_disease_trigger_works_outside_schedule(session, settings, rng, monkeypatch) -> None:
    pig_service = PigService(
        session,
        feed_cooldown=settings.feed_cooldown,
        battle_cooldown=settings.battle_cooldown,
        sabotage_cooldown=settings.sabotage_cooldown,
        raid_cooldown=settings.raid_cooldown,
        rng=rng,
    )
    settings.openai_api_key = None
    definition = get_disease_definition(DISEASE_FEED_COLD)
    now = datetime(2026, 3, 20, 7, 0, tzinfo=timezone.utc)

    monkeypatch.setattr(
        disease_service_module,
        "pick_disease_definition",
        lambda *, rng: definition,
    )

    await pig_service.create_pig(
        telegram_group_id=-10013,
        group_title="Manual Disease Group",
        telegram_user_id=6060,
        username="manualpig",
        first_name="Manual",
        last_name=None,
        pig_name="Trigger",
        now=now - timedelta(hours=1),
    )

    service = DiseaseService(session, settings=settings, rng=random.Random(39))
    result = await service.trigger_manual_disease(now=now)

    pig = await session.scalar(select(Pig).where(Pig.name == "Trigger"))
    roll = await session.scalar(select(GroupDiseaseRoll).where(GroupDiseaseRoll.pig_id == pig.id))

    assert result is not None
    assert result.telegram_group_id == -10013
    assert result.group_title == "Manual Disease Group"
    assert result.owner_telegram_user_id == 6060
    assert result.owner_mention_label == "@manualpig"
    assert pig is not None
    assert pig.weight_kg < 10
    assert roll is not None
    assert roll.payload["slot_kind"] == "manual"
    assert roll.payload["trigger_mode"] == "manual"
