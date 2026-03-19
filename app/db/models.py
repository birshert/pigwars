from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, Boolean, CheckConstraint, Date, DateTime, Enum, ForeignKey, Integer, JSON, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.domain.models.pig import PigItemType, PigRaidStatus, PigStatus, PigTrait, RaidDestination


SQLBigInt = BigInteger().with_variant(Integer, "sqlite")
WEIGHT_NUMERIC = Numeric(10, 2)
SCORE_NUMERIC = Numeric(12, 2)


def enum_value_column(enum_cls, *, length: int = 32) -> Enum:
    return Enum(
        enum_cls,
        native_enum=False,
        length=length,
        values_callable=lambda members: [member.value for member in members],
    )


class TelegramGroup(Base):
    __tablename__ = "telegram_groups"

    id: Mapped[int] = mapped_column(SQLBigInt, primary_key=True, autoincrement=True)
    telegram_group_id: Mapped[int] = mapped_column(SQLBigInt, unique=True, index=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    pigs: Mapped[list["Pig"]] = relationship(back_populates="group")
    battles: Mapped[list["Battle"]] = relationship(back_populates="group")


class TelegramUser(Base):
    __tablename__ = "telegram_users"

    id: Mapped[int] = mapped_column(SQLBigInt, primary_key=True, autoincrement=True)
    telegram_user_id: Mapped[int] = mapped_column(SQLBigInt, unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String, nullable=True)
    first_name: Mapped[str] = mapped_column(String, nullable=False)
    last_name: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    pigs: Mapped[list["Pig"]] = relationship(back_populates="owner")


class Pig(Base):
    __tablename__ = "pigs"
    __table_args__ = (
        UniqueConstraint("group_id", "owner_user_id", name="uq_pigs_group_owner"),
        CheckConstraint("weight_kg >= 3.0", name="weight_kg_min"),
        CheckConstraint("mood_score >= -100 AND mood_score <= 100", name="mood_score_range"),
        CheckConstraint("loyalty >= 0 AND loyalty <= 100", name="loyalty_range"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    group_id: Mapped[int] = mapped_column(ForeignKey("telegram_groups.id"), index=True)
    owner_user_id: Mapped[int] = mapped_column(ForeignKey("telegram_users.id"), index=True)
    name: Mapped[str] = mapped_column(String(40), nullable=False)
    weight_kg: Mapped[Decimal] = mapped_column(WEIGHT_NUMERIC, nullable=False)
    status: Mapped[PigStatus] = mapped_column(
        enum_value_column(PigStatus),
        default=PigStatus.IDLE,
        nullable=False,
        index=True,
    )
    trait: Mapped[PigTrait] = mapped_column(
        enum_value_column(PigTrait),
        nullable=False,
        index=True,
    )
    mood_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    loyalty: Mapped[int] = mapped_column(Integer, default=50, nullable=False)
    wins: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    losses: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_feed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_battle_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_sabotage_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_raid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    battle_ready_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    raid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    group: Mapped[TelegramGroup] = relationship(back_populates="pigs")
    owner: Mapped[TelegramUser] = relationship(back_populates="pigs")
    items: Mapped[list["PigItem"]] = relationship(back_populates="pig")
    effects: Mapped[list["PigEffect"]] = relationship(back_populates="pig")
    raids: Mapped[list["PigRaid"]] = relationship(back_populates="pig")
    daily_actions: Mapped[list["PigDailyAction"]] = relationship(back_populates="pig")


class Battle(Base):
    __tablename__ = "battles"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    group_id: Mapped[int] = mapped_column(ForeignKey("telegram_groups.id"), index=True)
    pig1_id: Mapped[UUID] = mapped_column(ForeignKey("pigs.id"), index=True)
    pig2_id: Mapped[UUID] = mapped_column(ForeignKey("pigs.id"), index=True)
    winner_pig_id: Mapped[UUID | None] = mapped_column(ForeignKey("pigs.id"), nullable=True)
    loser_pig_id: Mapped[UUID | None] = mapped_column(ForeignKey("pigs.id"), nullable=True)
    pig1_score: Mapped[Decimal] = mapped_column(SCORE_NUMERIC, nullable=False)
    pig2_score: Mapped[Decimal] = mapped_column(SCORE_NUMERIC, nullable=False)
    weight_delta_winner: Mapped[Decimal] = mapped_column(WEIGHT_NUMERIC, nullable=False)
    weight_delta_loser: Mapped[Decimal] = mapped_column(WEIGHT_NUMERIC, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    group: Mapped[TelegramGroup] = relationship(back_populates="battles")


class PigEvent(Base):
    __tablename__ = "pig_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pig_id: Mapped[UUID] = mapped_column(ForeignKey("pigs.id"), index=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("telegram_groups.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class PigDailyAction(Base):
    __tablename__ = "pig_daily_actions"
    __table_args__ = (
        UniqueConstraint("pig_id", "action_type", "action_day", name="uq_pig_daily_actions_identity"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pig_id: Mapped[UUID] = mapped_column(ForeignKey("pigs.id"), index=True)
    action_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    action_day: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    result_key: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    pig: Mapped[Pig] = relationship(back_populates="daily_actions")


class PigItem(Base):
    __tablename__ = "pig_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pig_id: Mapped[UUID] = mapped_column(ForeignKey("pigs.id"), index=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("telegram_groups.id"), index=True)
    item_code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    item_type: Mapped[PigItemType] = mapped_column(
        enum_value_column(PigItemType),
        nullable=False,
        index=True,
    )
    is_equipped: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    durability: Mapped[int | None] = mapped_column(Integer, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    pig: Mapped[Pig] = relationship(back_populates="items")


class PigEffect(Base):
    __tablename__ = "pig_effects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pig_id: Mapped[UUID] = mapped_column(ForeignKey("pigs.id"), index=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("telegram_groups.id"), index=True)
    effect_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    source_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    pig: Mapped[Pig] = relationship(back_populates="effects")


class PigRaid(Base):
    __tablename__ = "pig_raids"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    pig_id: Mapped[UUID] = mapped_column(ForeignKey("pigs.id"), index=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("telegram_groups.id"), index=True)
    destination: Mapped[RaidDestination] = mapped_column(
        enum_value_column(RaidDestination),
        nullable=False,
        index=True,
    )
    status: Mapped[PigRaidStatus] = mapped_column(
        enum_value_column(PigRaidStatus),
        nullable=False,
        index=True,
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolve_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    result_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    pig: Mapped[Pig] = relationship(back_populates="raids")


class WorldEvent(Base):
    __tablename__ = "world_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    modifiers: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    announced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
