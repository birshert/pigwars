from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Enum, ForeignKey, Integer, JSON, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.domain.models.pig import PigStatus


SQLBigInt = BigInteger().with_variant(Integer, "sqlite")
WEIGHT_NUMERIC = Numeric(10, 2)
SCORE_NUMERIC = Numeric(12, 2)


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
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    group_id: Mapped[int] = mapped_column(ForeignKey("telegram_groups.id"), index=True)
    owner_user_id: Mapped[int] = mapped_column(ForeignKey("telegram_users.id"), index=True)
    name: Mapped[str] = mapped_column(String(40), nullable=False)
    weight_kg: Mapped[Decimal] = mapped_column(WEIGHT_NUMERIC, nullable=False)
    status: Mapped[PigStatus] = mapped_column(
        Enum(PigStatus, native_enum=False, length=32),
        default=PigStatus.IDLE,
        nullable=False,
        index=True,
    )
    wins: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    losses: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_feed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_battle_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    battle_ready_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
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
