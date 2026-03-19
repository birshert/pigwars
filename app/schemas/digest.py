from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any


@dataclass(slots=True)
class DailyDigestCounts:
    battles: int
    raids_total: int
    raids_good: int
    raids_bad: int
    feeds: int
    sabotage_total: int
    sabotage_success: int
    items_found: int
    items_used: int
    new_pigs: int

    def to_payload(self) -> dict[str, int]:
        return {
            "battles": self.battles,
            "raids_total": self.raids_total,
            "raids_good": self.raids_good,
            "raids_bad": self.raids_bad,
            "feeds": self.feeds,
            "sabotage_total": self.sabotage_total,
            "sabotage_success": self.sabotage_success,
            "items_found": self.items_found,
            "items_used": self.items_used,
            "new_pigs": self.new_pigs,
        }

    @property
    def activity_total(self) -> int:
        return (
            self.battles
            + self.raids_total
            + self.feeds
            + self.sabotage_total
            + self.items_found
            + self.items_used
            + self.new_pigs
        )


@dataclass(slots=True)
class DailyDigestHighlight:
    type: str
    text: str
    pig_name: str | None = None
    weight_delta: Decimal | None = None
    item_title: str | None = None
    count: int | None = None

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "type": self.type,
            "text": self.text,
        }
        if self.pig_name is not None:
            payload["pig_name"] = self.pig_name
        if self.weight_delta is not None:
            payload["weight_delta"] = str(self.weight_delta)
        if self.item_title is not None:
            payload["item_title"] = self.item_title
        if self.count is not None:
            payload["count"] = self.count
        return payload


@dataclass(slots=True)
class DailyDigestLeaderboardEntry:
    place: int
    pig_name: str
    weight_kg: Decimal

    def to_payload(self) -> dict[str, Any]:
        return {
            "place": self.place,
            "pig_name": self.pig_name,
            "weight_kg": str(self.weight_kg),
        }


@dataclass(slots=True)
class DailyDigestWorldEvent:
    title: str
    active: bool

    def to_payload(self) -> dict[str, Any]:
        return {"title": self.title, "active": self.active}


@dataclass(slots=True)
class DailyDigestFacts:
    group_id: int
    telegram_group_id: int
    group_title: str
    digest_day: date
    counts: DailyDigestCounts
    highlights: list[DailyDigestHighlight]
    leaderboard: list[DailyDigestLeaderboardEntry]
    world_event: DailyDigestWorldEvent | None

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "digest_day": self.digest_day.isoformat(),
            "group_title": self.group_title,
            "counts": self.counts.to_payload(),
            "highlights": [highlight.to_payload() for highlight in self.highlights],
            "leaderboard": [entry.to_payload() for entry in self.leaderboard],
        }
        if self.world_event is not None:
            payload["world_event"] = self.world_event.to_payload()
        return payload


@dataclass(slots=True)
class DailyDigestSummaryResult:
    text: str
    llm_model: str | None
    used_llm: bool
