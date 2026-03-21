"""disease system

Revision ID: 0006_disease_system
Revises: 0005_daily_group_digest
Create Date: 2026-03-19 14:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0006_disease_system"
down_revision = "0005_daily_group_digest"
branch_labels = None
depends_on = None


old_pig_status_enum = sa.Enum(
    "idle",
    "battle_ready",
    "in_battle",
    "on_raid",
    name="pigstatus",
    native_enum=False,
    length=32,
)
new_pig_status_enum = sa.Enum(
    "idle",
    "battle_ready",
    "in_battle",
    "on_raid",
    "quarantined",
    name="pigstatus",
    native_enum=False,
    length=32,
)
disease_roll_status_enum = sa.Enum(
    "triggered",
    "skipped",
    name="diseaserollstatus",
    native_enum=False,
    length=16,
)


def upgrade() -> None:
    with op.batch_alter_table("pigs") as batch_op:
        batch_op.alter_column("status", type_=new_pig_status_enum, existing_type=old_pig_status_enum)
        batch_op.add_column(sa.Column("quarantine_until", sa.DateTime(timezone=True), nullable=True))
        batch_op.create_index("ix_pigs_quarantine_until", ["quarantine_until"], unique=False)

    op.create_table(
        "group_disease_rolls",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("group_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False),
        sa.Column("pig_id", sa.Uuid(), nullable=True),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", disease_roll_status_enum, nullable=False),
        sa.Column("disease_code", sa.String(length=64), nullable=True),
        sa.Column("narrative_text", sa.Text(), nullable=True),
        sa.Column("llm_model", sa.String(length=64), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["group_id"], ["telegram_groups.id"], name="fk_group_disease_rolls_group_id_telegram_groups"),
        sa.ForeignKeyConstraint(["pig_id"], ["pigs.id"], name="fk_group_disease_rolls_pig_id_pigs"),
        sa.PrimaryKeyConstraint("id", name="pk_group_disease_rolls"),
        sa.UniqueConstraint("group_id", "scheduled_for", name="uq_group_disease_rolls_group_slot"),
    )
    op.create_index("ix_group_disease_rolls_group_id", "group_disease_rolls", ["group_id"], unique=False)
    op.create_index("ix_group_disease_rolls_pig_id", "group_disease_rolls", ["pig_id"], unique=False)
    op.create_index("ix_group_disease_rolls_scheduled_for", "group_disease_rolls", ["scheduled_for"], unique=False)
    op.create_index("ix_group_disease_rolls_status", "group_disease_rolls", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_group_disease_rolls_status", table_name="group_disease_rolls")
    op.drop_index("ix_group_disease_rolls_scheduled_for", table_name="group_disease_rolls")
    op.drop_index("ix_group_disease_rolls_pig_id", table_name="group_disease_rolls")
    op.drop_index("ix_group_disease_rolls_group_id", table_name="group_disease_rolls")
    op.drop_table("group_disease_rolls")

    with op.batch_alter_table("pigs") as batch_op:
        batch_op.drop_index("ix_pigs_quarantine_until")
        batch_op.drop_column("quarantine_until")
        batch_op.alter_column("status", type_=old_pig_status_enum, existing_type=new_pig_status_enum)
