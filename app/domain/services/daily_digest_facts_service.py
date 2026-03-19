from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.db.models import Battle, Pig, PigEvent, PigRaid, WorldEvent
from app.db.repositories.group_repo import GroupRepository
from app.db.repositories.pig_repo import PigRepository
from app.domain.models.pig import PigRaidStatus
from app.domain.rules.timezones import get_game_day_bounds
from app.schemas.digest import (
    DailyDigestCounts,
    DailyDigestFacts,
    DailyDigestHighlight,
    DailyDigestLeaderboardEntry,
    DailyDigestWorldEvent,
)


TRACKED_EVENT_TYPES = (
    "battle_lost",
    "battle_won",
    "item_found",
    "item_used",
    "pig_created",
    "pig_fed",
    "raid_finished",
    "sabotage_failed",
    "sabotage_success",
)


class DailyDigestFactsService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._groups = GroupRepository(session)
        self._pigs = PigRepository(session)

    async def build_for_group(
        self,
        *,
        group_id: int,
        digest_day: date,
        now: datetime,
    ) -> DailyDigestFacts:
        group = await self._groups.get_by_id(group_id)
        if group is None:
            raise ValueError(f"Group {group_id} does not exist")

        day_start, day_end = get_game_day_bounds(digest_day)
        events = await self._list_events(group_id=group_id, start_at=day_start, end_at=day_end)
        battles = await self._list_battles(group_id=group_id, start_at=day_start, end_at=day_end)
        raids = await self._list_raids(group_id=group_id, start_at=day_start, end_at=day_end)
        world_event = await self._get_world_event(start_at=day_start, end_at=day_end, now=now)
        leaderboard_rows = await self._pigs.list_weight_leaderboard(group_id=group_id, limit=3)

        counts = self._build_counts(events=events, battles=battles, raids=raids)
        highlights = self._build_highlights(
            counts=counts,
            events=events,
            battles=battles,
            raids=raids,
            world_event=world_event,
        )
        leaderboard = [
            DailyDigestLeaderboardEntry(place=index, pig_name=pig.name, weight_kg=pig.weight_kg)
            for index, (pig, _user) in enumerate(leaderboard_rows, start=1)
        ]

        return DailyDigestFacts(
            group_id=group.id,
            telegram_group_id=group.telegram_group_id,
            group_title=group.title,
            digest_day=digest_day,
            counts=counts,
            highlights=highlights,
            leaderboard=leaderboard,
            world_event=world_event,
        )

    async def _list_events(
        self,
        *,
        group_id: int,
        start_at: datetime,
        end_at: datetime,
    ) -> list[tuple[PigEvent, str]]:
        stmt = (
            select(PigEvent, Pig.name)
            .join(Pig, PigEvent.pig_id == Pig.id)
            .where(
                PigEvent.group_id == group_id,
                PigEvent.created_at >= start_at,
                PigEvent.created_at < end_at,
                PigEvent.event_type.in_(TRACKED_EVENT_TYPES),
            )
            .order_by(PigEvent.created_at.asc(), PigEvent.id.asc())
        )
        result = await self._session.execute(stmt)
        return list(result.all())

    async def _list_battles(
        self,
        *,
        group_id: int,
        start_at: datetime,
        end_at: datetime,
    ) -> list[tuple[Battle, str, str]]:
        winner = aliased(Pig)
        loser = aliased(Pig)
        stmt = (
            select(Battle, winner.name, loser.name)
            .join(winner, Battle.winner_pig_id == winner.id)
            .join(loser, Battle.loser_pig_id == loser.id)
            .where(
                Battle.group_id == group_id,
                Battle.created_at >= start_at,
                Battle.created_at < end_at,
            )
            .order_by(Battle.created_at.asc(), Battle.id.asc())
        )
        result = await self._session.execute(stmt)
        return list(result.all())

    async def _list_raids(
        self,
        *,
        group_id: int,
        start_at: datetime,
        end_at: datetime,
    ) -> list[tuple[PigRaid, str]]:
        stmt = (
            select(PigRaid, Pig.name)
            .join(Pig, PigRaid.pig_id == Pig.id)
            .where(
                PigRaid.group_id == group_id,
                PigRaid.status == PigRaidStatus.RESOLVED,
                PigRaid.resolved_at.is_not(None),
                PigRaid.resolved_at >= start_at,
                PigRaid.resolved_at < end_at,
            )
            .order_by(PigRaid.resolved_at.asc(), PigRaid.id.asc())
        )
        result = await self._session.execute(stmt)
        return list(result.all())

    async def _get_world_event(
        self,
        *,
        start_at: datetime,
        end_at: datetime,
        now: datetime,
    ) -> DailyDigestWorldEvent | None:
        stmt = (
            select(WorldEvent)
            .where(WorldEvent.starts_at < end_at, WorldEvent.ends_at > start_at)
            .order_by(WorldEvent.starts_at.desc(), WorldEvent.id.desc())
        )
        event = await self._session.scalar(stmt)
        if event is None:
            return None
        return DailyDigestWorldEvent(title=event.title, active=event.starts_at <= now < event.ends_at)

    def _build_counts(
        self,
        *,
        events: Iterable[tuple[PigEvent, str]],
        battles: list[tuple[Battle, str, str]],
        raids: list[tuple[PigRaid, str]],
    ) -> DailyDigestCounts:
        event_counts = defaultdict(int)
        for event, _pig_name in events:
            event_counts[event.event_type] += 1

        raids_good = 0
        raids_bad = 0
        for raid, _pig_name in raids:
            outcome = str((raid.result_payload or {}).get("outcome", ""))
            if outcome == "good":
                raids_good += 1
            elif outcome == "bad":
                raids_bad += 1

        return DailyDigestCounts(
            battles=len(battles),
            raids_total=len(raids),
            raids_good=raids_good,
            raids_bad=raids_bad,
            feeds=event_counts["pig_fed"],
            sabotage_total=event_counts["sabotage_success"] + event_counts["sabotage_failed"],
            sabotage_success=event_counts["sabotage_success"],
            items_found=event_counts["item_found"],
            items_used=event_counts["item_used"],
            new_pigs=event_counts["pig_created"],
        )

    def _build_highlights(
        self,
        *,
        counts: DailyDigestCounts,
        events: list[tuple[PigEvent, str]],
        battles: list[tuple[Battle, str, str]],
        raids: list[tuple[PigRaid, str]],
        world_event: DailyDigestWorldEvent | None,
    ) -> list[DailyDigestHighlight]:
        highlights: list[DailyDigestHighlight] = []
        weight_deltas = self._collect_weight_deltas(events)

        top_gain = max(weight_deltas.items(), key=lambda item: item[1][1], default=None)
        if top_gain is not None and top_gain[1][1] > Decimal("0.00"):
            pig_name, weight_delta = top_gain[1]
            highlights.append(
                DailyDigestHighlight(
                    type="top_gain",
                    pig_name=pig_name,
                    weight_delta=weight_delta,
                    text=f"{pig_name}: +{weight_delta} кг за день.",
                )
            )

        raid_loot = self._pick_raid_loot(raids)
        if raid_loot is not None:
            pig_name, item_title = raid_loot
            highlights.append(
                DailyDigestHighlight(
                    type="raid_loot",
                    pig_name=pig_name,
                    item_title=item_title,
                    text=f"{pig_name} притащила из рейда «{item_title}».",
                )
            )

        new_pigs = self._pick_new_pigs(events)
        if new_pigs:
            first_name = new_pigs[0]
            if len(new_pigs) == 1:
                text = f"В группе появилась новая свинья: {first_name}."
            else:
                text = f"В группе прибыло {len(new_pigs)} {self._pluralize(len(new_pigs), 'новая свинья', 'новые свиньи', 'новых свиней')}, первой отметилась {first_name}."
            highlights.append(
                DailyDigestHighlight(
                    type="new_pig",
                    pig_name=first_name,
                    count=len(new_pigs),
                    text=text,
                )
            )

        if counts.sabotage_success > 0:
            highlights.append(
                DailyDigestHighlight(
                    type="sabotage_success",
                    count=counts.sabotage_success,
                    text=f"Удачных диверсий за день: {counts.sabotage_success}.",
                )
            )

        bad_raid = self._pick_bad_raid(raids)
        if bad_raid is not None:
            highlights.append(
                DailyDigestHighlight(
                    type="raid_bad",
                    pig_name=bad_raid[0],
                    text=bad_raid[1],
                )
            )

        if world_event is not None:
            world_text = (
                f"Мировое событие всё ещё активно: «{world_event.title}»."
                if world_event.active
                else f"Вчера на фон дня влияло мировое событие: «{world_event.title}»."
            )
            highlights.append(
                DailyDigestHighlight(
                    type="world_event",
                    item_title=world_event.title,
                    text=world_text,
                )
            )

        biggest_battle = self._pick_biggest_battle(battles)
        if biggest_battle is not None:
            winner_name, loser_name, swing = biggest_battle
            highlights.append(
                DailyDigestHighlight(
                    type="battle_swing",
                    text=f"Самая громкая драка: {winner_name} выбила у {loser_name} суммарно {swing} кг.",
                )
            )

        if counts.items_found > 0 and raid_loot is None:
            highlights.append(
                DailyDigestHighlight(
                    type="items_found",
                    count=counts.items_found,
                    text=f"За день в загоне нашли {counts.items_found} {self._pluralize(counts.items_found, 'предмет', 'предмета', 'предметов')}.",
                )
            )

        if counts.items_used > 0:
            highlights.append(
                DailyDigestHighlight(
                    type="items_used",
                    count=counts.items_used,
                    text=f"Игроки активировали {counts.items_used} {self._pluralize(counts.items_used, 'предмет', 'предмета', 'предметов')} за день.",
                )
            )

        return highlights[:4]

    def _collect_weight_deltas(
        self,
        events: Iterable[tuple[PigEvent, str]],
    ) -> dict[str, tuple[str, Decimal]]:
        deltas: dict[str, Decimal] = defaultdict(lambda: Decimal("0.00"))
        names: dict[str, str] = {}

        for event, pig_name in events:
            names[str(event.pig_id)] = pig_name
            payload = event.payload or {}
            if event.event_type == "pig_fed":
                deltas[str(event.pig_id)] += self._parse_decimal(payload.get("weight_gain"))
            elif event.event_type == "battle_won":
                deltas[str(event.pig_id)] += self._parse_decimal(payload.get("weight_gain"))
            elif event.event_type == "battle_lost":
                deltas[str(event.pig_id)] -= self._parse_decimal(payload.get("weight_loss"))
            elif event.event_type == "raid_finished":
                deltas[str(event.pig_id)] += self._parse_decimal(payload.get("weight_change"))

        return {
            pig_id: (names[pig_id], weight_delta)
            for pig_id, weight_delta in deltas.items()
        }

    def _pick_raid_loot(self, raids: list[tuple[PigRaid, str]]) -> tuple[str, str] | None:
        for raid, pig_name in raids:
            found_item_title = str((raid.result_payload or {}).get("found_item_title") or "").strip()
            if found_item_title:
                return pig_name, found_item_title
        return None

    def _pick_new_pigs(self, events: list[tuple[PigEvent, str]]) -> list[str]:
        names: list[str] = []
        for event, pig_name in events:
            if event.event_type != "pig_created":
                continue
            names.append(str((event.payload or {}).get("name") or pig_name))
        return names

    def _pick_bad_raid(self, raids: list[tuple[PigRaid, str]]) -> tuple[str, str] | None:
        for raid, pig_name in raids:
            payload = raid.result_payload or {}
            if payload.get("outcome") != "bad":
                continue
            effect_title = str(payload.get("granted_effect_title") or "").strip()
            if effect_title:
                return pig_name, f"{pig_name} вернулась из рейда с эффектом «{effect_title}»."
            return pig_name, f"{pig_name} сходила в рейд неудачно и вернулась без славы."
        return None

    def _pick_biggest_battle(
        self,
        battles: list[tuple[Battle, str, str]],
    ) -> tuple[str, str, Decimal] | None:
        biggest: tuple[str, str, Decimal] | None = None
        for battle, winner_name, loser_name in battles:
            swing = battle.weight_delta_winner + battle.weight_delta_loser
            if biggest is None or swing > biggest[2]:
                biggest = (winner_name, loser_name, swing)
        return biggest

    def _parse_decimal(self, raw: Any) -> Decimal:
        if raw in (None, ""):
            return Decimal("0.00")
        return Decimal(str(raw))

    def _pluralize(self, value: int, singular: str, paucal: str, plural: str) -> str:
        mod100 = value % 100
        mod10 = value % 10
        if 11 <= mod100 <= 14:
            return plural
        if mod10 == 1:
            return singular
        if 2 <= mod10 <= 4:
            return paucal
        return plural
