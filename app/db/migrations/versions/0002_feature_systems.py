"""feature systems schema

Revision ID: 0002_feature_systems
Revises: 0001_initial
Create Date: 2026-03-19 00:30:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0002_feature_systems"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


old_pig_status_enum = sa.Enum(
    "idle",
    "battle_ready",
    "in_battle",
    name="pigstatus",
    native_enum=False,
    length=32,
)
new_pig_status_enum = sa.Enum(
    "idle",
    "battle_ready",
    "in_battle",
    "on_raid",
    name="pigstatus",
    native_enum=False,
    length=32,
)
trait_enum = sa.Enum(
    "aggressive",
    "glutton",
    "cunning",
    "stubborn",
    "lucky",
    "phlegmatic",
    name="pigtrait",
    native_enum=False,
    length=32,
)
item_type_enum = sa.Enum(
    "equipment",
    "consumable",
    name="pigitemtype",
    native_enum=False,
    length=32,
)
raid_destination_enum = sa.Enum(
    "dump",
    "market",
    "woods",
    name="raiddestination",
    native_enum=False,
    length=32,
)
raid_status_enum = sa.Enum(
    "active",
    "resolved",
    "failed",
    name="pigraidstatus",
    native_enum=False,
    length=32,
)


def upgrade() -> None:
    with op.batch_alter_table("pigs") as batch_op:
        batch_op.alter_column("status", type_=new_pig_status_enum, existing_type=old_pig_status_enum)
        batch_op.add_column(sa.Column("trait", trait_enum, nullable=True, server_default="phlegmatic"))
        batch_op.add_column(sa.Column("mood_score", sa.Integer(), nullable=False, server_default="0"))
        batch_op.add_column(sa.Column("loyalty", sa.Integer(), nullable=False, server_default="50"))
        batch_op.add_column(sa.Column("last_sabotage_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("last_raid_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("raid_until", sa.DateTime(timezone=True), nullable=True))
        batch_op.create_index("ix_pigs_trait", ["trait"], unique=False)
        batch_op.create_index("ix_pigs_raid_until", ["raid_until"], unique=False)
        batch_op.create_check_constraint("mood_score_range", "mood_score >= -100 AND mood_score <= 100")
        batch_op.create_check_constraint("loyalty_range", "loyalty >= 0 AND loyalty <= 100")

    op.execute("UPDATE pigs SET trait = 'phlegmatic' WHERE trait IS NULL")

    with op.batch_alter_table("pigs") as batch_op:
        batch_op.alter_column("trait", nullable=False, server_default=None)

    op.create_table(
        "pig_items",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("pig_id", sa.Uuid(), nullable=False),
        sa.Column("group_id", sa.BigInteger(), nullable=False),
        sa.Column("item_code", sa.String(length=64), nullable=False),
        sa.Column("item_type", item_type_enum, nullable=False),
        sa.Column("is_equipped", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("durability", sa.Integer(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["pig_id"], ["pigs.id"], name="fk_pig_items_pig_id_pigs"),
        sa.ForeignKeyConstraint(["group_id"], ["telegram_groups.id"], name="fk_pig_items_group_id_telegram_groups"),
    )
    op.create_index("ix_pig_items_pig_id", "pig_items", ["pig_id"], unique=False)
    op.create_index("ix_pig_items_group_id", "pig_items", ["group_id"], unique=False)
    op.create_index("ix_pig_items_item_code", "pig_items", ["item_code"], unique=False)
    op.create_index("ix_pig_items_item_type", "pig_items", ["item_type"], unique=False)
    op.create_index("ix_pig_items_expires_at", "pig_items", ["expires_at"], unique=False)

    op.create_table(
        "pig_effects",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("pig_id", sa.Uuid(), nullable=False),
        sa.Column("group_id", sa.BigInteger(), nullable=False),
        sa.Column("effect_type", sa.String(length=64), nullable=False),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("source_id", sa.String(length=64), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["pig_id"], ["pigs.id"], name="fk_pig_effects_pig_id_pigs"),
        sa.ForeignKeyConstraint(["group_id"], ["telegram_groups.id"], name="fk_pig_effects_group_id_telegram_groups"),
    )
    op.create_index("ix_pig_effects_pig_id", "pig_effects", ["pig_id"], unique=False)
    op.create_index("ix_pig_effects_group_id", "pig_effects", ["group_id"], unique=False)
    op.create_index("ix_pig_effects_effect_type", "pig_effects", ["effect_type"], unique=False)
    op.create_index("ix_pig_effects_source_type", "pig_effects", ["source_type"], unique=False)
    op.create_index("ix_pig_effects_expires_at", "pig_effects", ["expires_at"], unique=False)
    op.create_index("ix_pig_effects_consumed_at", "pig_effects", ["consumed_at"], unique=False)

    op.create_table(
        "pig_raids",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("pig_id", sa.Uuid(), nullable=False),
        sa.Column("group_id", sa.BigInteger(), nullable=False),
        sa.Column("destination", raid_destination_enum, nullable=False),
        sa.Column("status", raid_status_enum, nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolve_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result_payload", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["pig_id"], ["pigs.id"], name="fk_pig_raids_pig_id_pigs"),
        sa.ForeignKeyConstraint(["group_id"], ["telegram_groups.id"], name="fk_pig_raids_group_id_telegram_groups"),
    )
    op.create_index("ix_pig_raids_pig_id", "pig_raids", ["pig_id"], unique=False)
    op.create_index("ix_pig_raids_group_id", "pig_raids", ["group_id"], unique=False)
    op.create_index("ix_pig_raids_destination", "pig_raids", ["destination"], unique=False)
    op.create_index("ix_pig_raids_status", "pig_raids", ["status"], unique=False)
    op.create_index("ix_pig_raids_resolve_at", "pig_raids", ["resolve_at"], unique=False)

    op.create_table(
        "world_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("event_code", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=128), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("modifiers", sa.JSON(), nullable=True),
        sa.Column("announced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_world_events_event_code", "world_events", ["event_code"], unique=False)
    op.create_index("ix_world_events_starts_at", "world_events", ["starts_at"], unique=False)
    op.create_index("ix_world_events_ends_at", "world_events", ["ends_at"], unique=False)
    op.create_index("ix_world_events_announced_at", "world_events", ["announced_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_world_events_announced_at", table_name="world_events")
    op.drop_index("ix_world_events_ends_at", table_name="world_events")
    op.drop_index("ix_world_events_starts_at", table_name="world_events")
    op.drop_index("ix_world_events_event_code", table_name="world_events")
    op.drop_table("world_events")

    op.drop_index("ix_pig_raids_resolve_at", table_name="pig_raids")
    op.drop_index("ix_pig_raids_status", table_name="pig_raids")
    op.drop_index("ix_pig_raids_destination", table_name="pig_raids")
    op.drop_index("ix_pig_raids_group_id", table_name="pig_raids")
    op.drop_index("ix_pig_raids_pig_id", table_name="pig_raids")
    op.drop_table("pig_raids")

    op.drop_index("ix_pig_effects_consumed_at", table_name="pig_effects")
    op.drop_index("ix_pig_effects_expires_at", table_name="pig_effects")
    op.drop_index("ix_pig_effects_source_type", table_name="pig_effects")
    op.drop_index("ix_pig_effects_effect_type", table_name="pig_effects")
    op.drop_index("ix_pig_effects_group_id", table_name="pig_effects")
    op.drop_index("ix_pig_effects_pig_id", table_name="pig_effects")
    op.drop_table("pig_effects")

    op.drop_index("ix_pig_items_expires_at", table_name="pig_items")
    op.drop_index("ix_pig_items_item_type", table_name="pig_items")
    op.drop_index("ix_pig_items_item_code", table_name="pig_items")
    op.drop_index("ix_pig_items_group_id", table_name="pig_items")
    op.drop_index("ix_pig_items_pig_id", table_name="pig_items")
    op.drop_table("pig_items")

    with op.batch_alter_table("pigs") as batch_op:
        batch_op.drop_constraint("ck_pigs_loyalty_range", type_="check")
        batch_op.drop_constraint("ck_pigs_mood_score_range", type_="check")
        batch_op.drop_index("ix_pigs_raid_until")
        batch_op.drop_index("ix_pigs_trait")
        batch_op.drop_column("raid_until")
        batch_op.drop_column("last_raid_at")
        batch_op.drop_column("last_sabotage_at")
        batch_op.drop_column("loyalty")
        batch_op.drop_column("mood_score")
        batch_op.drop_column("trait")
        batch_op.alter_column("status", type_=old_pig_status_enum, existing_type=new_pig_status_enum)
