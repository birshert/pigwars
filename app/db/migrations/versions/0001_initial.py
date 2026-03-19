"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-03-19 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    pig_status_enum = sa.Enum(
        "idle",
        "battle_ready",
        "in_battle",
        name="pigstatus",
        native_enum=False,
        length=32,
    )

    op.create_table(
        "telegram_groups",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("telegram_group_id", sa.BigInteger(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("telegram_group_id", name="uq_telegram_groups_telegram_group_id"),
    )
    op.create_index("ix_telegram_groups_telegram_group_id", "telegram_groups", ["telegram_group_id"], unique=False)

    op.create_table(
        "telegram_users",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.String(), nullable=True),
        sa.Column("first_name", sa.String(), nullable=False),
        sa.Column("last_name", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("telegram_user_id", name="uq_telegram_users_telegram_user_id"),
    )
    op.create_index("ix_telegram_users_telegram_user_id", "telegram_users", ["telegram_user_id"], unique=False)

    op.create_table(
        "pigs",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("group_id", sa.BigInteger(), nullable=False),
        sa.Column("owner_user_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(length=40), nullable=False),
        sa.Column("weight_kg", sa.Numeric(10, 2), nullable=False),
        sa.Column("status", pig_status_enum, nullable=False),
        sa.Column("wins", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("losses", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_feed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_battle_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("battle_ready_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("weight_kg >= 3.0", name="ck_pigs_weight_kg_min"),
        sa.ForeignKeyConstraint(["group_id"], ["telegram_groups.id"], name="fk_pigs_group_id_telegram_groups"),
        sa.ForeignKeyConstraint(["owner_user_id"], ["telegram_users.id"], name="fk_pigs_owner_user_id_telegram_users"),
        sa.UniqueConstraint("group_id", "owner_user_id", name="uq_pigs_group_owner"),
    )
    op.create_index("ix_pigs_group_id", "pigs", ["group_id"], unique=False)
    op.create_index("ix_pigs_owner_user_id", "pigs", ["owner_user_id"], unique=False)
    op.create_index("ix_pigs_status", "pigs", ["status"], unique=False)
    op.create_index("ix_pigs_battle_ready_until", "pigs", ["battle_ready_until"], unique=False)

    op.create_table(
        "battles",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("group_id", sa.BigInteger(), nullable=False),
        sa.Column("pig1_id", sa.Uuid(), nullable=False),
        sa.Column("pig2_id", sa.Uuid(), nullable=False),
        sa.Column("winner_pig_id", sa.Uuid(), nullable=True),
        sa.Column("loser_pig_id", sa.Uuid(), nullable=True),
        sa.Column("pig1_score", sa.Numeric(12, 2), nullable=False),
        sa.Column("pig2_score", sa.Numeric(12, 2), nullable=False),
        sa.Column("weight_delta_winner", sa.Numeric(10, 2), nullable=False),
        sa.Column("weight_delta_loser", sa.Numeric(10, 2), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["group_id"], ["telegram_groups.id"], name="fk_battles_group_id_telegram_groups"),
        sa.ForeignKeyConstraint(["loser_pig_id"], ["pigs.id"], name="fk_battles_loser_pig_id_pigs"),
        sa.ForeignKeyConstraint(["pig1_id"], ["pigs.id"], name="fk_battles_pig1_id_pigs"),
        sa.ForeignKeyConstraint(["pig2_id"], ["pigs.id"], name="fk_battles_pig2_id_pigs"),
        sa.ForeignKeyConstraint(["winner_pig_id"], ["pigs.id"], name="fk_battles_winner_pig_id_pigs"),
    )
    op.create_index("ix_battles_group_id", "battles", ["group_id"], unique=False)
    op.create_index("ix_battles_pig1_id", "battles", ["pig1_id"], unique=False)
    op.create_index("ix_battles_pig2_id", "battles", ["pig2_id"], unique=False)

    op.create_table(
        "pig_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("pig_id", sa.Uuid(), nullable=False),
        sa.Column("group_id", sa.BigInteger(), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["group_id"], ["telegram_groups.id"], name="fk_pig_events_group_id_telegram_groups"),
        sa.ForeignKeyConstraint(["pig_id"], ["pigs.id"], name="fk_pig_events_pig_id_pigs"),
    )
    op.create_index("ix_pig_events_pig_id", "pig_events", ["pig_id"], unique=False)
    op.create_index("ix_pig_events_group_id", "pig_events", ["group_id"], unique=False)
    op.create_index("ix_pig_events_event_type", "pig_events", ["event_type"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_pig_events_event_type", table_name="pig_events")
    op.drop_index("ix_pig_events_group_id", table_name="pig_events")
    op.drop_index("ix_pig_events_pig_id", table_name="pig_events")
    op.drop_table("pig_events")

    op.drop_index("ix_battles_pig2_id", table_name="battles")
    op.drop_index("ix_battles_pig1_id", table_name="battles")
    op.drop_index("ix_battles_group_id", table_name="battles")
    op.drop_table("battles")

    op.drop_index("ix_pigs_battle_ready_until", table_name="pigs")
    op.drop_index("ix_pigs_status", table_name="pigs")
    op.drop_index("ix_pigs_owner_user_id", table_name="pigs")
    op.drop_index("ix_pigs_group_id", table_name="pigs")
    op.drop_table("pigs")

    op.drop_index("ix_telegram_users_telegram_user_id", table_name="telegram_users")
    op.drop_table("telegram_users")

    op.drop_index("ix_telegram_groups_telegram_group_id", table_name="telegram_groups")
    op.drop_table("telegram_groups")
