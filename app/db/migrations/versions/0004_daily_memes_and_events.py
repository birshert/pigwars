"""daily memes and events

Revision ID: 0004_daily_memes_and_events
Revises: 0003_normalize_enum_storage
Create Date: 2026-03-19 02:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0004_daily_memes_and_events"
down_revision = "0003_normalize_enum_storage"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pig_daily_actions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("pig_id", sa.Uuid(), nullable=False),
        sa.Column("action_type", sa.String(length=64), nullable=False),
        sa.Column("action_day", sa.Date(), nullable=False),
        sa.Column("result_key", sa.String(length=64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["pig_id"], ["pigs.id"], name="fk_pig_daily_actions_pig_id_pigs"),
        sa.PrimaryKeyConstraint("id", name="pk_pig_daily_actions"),
        sa.UniqueConstraint("pig_id", "action_type", "action_day", name="uq_pig_daily_actions_identity"),
    )
    op.create_index("ix_pig_daily_actions_pig_id", "pig_daily_actions", ["pig_id"], unique=False)
    op.create_index("ix_pig_daily_actions_action_type", "pig_daily_actions", ["action_type"], unique=False)
    op.create_index("ix_pig_daily_actions_action_day", "pig_daily_actions", ["action_day"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_pig_daily_actions_action_day", table_name="pig_daily_actions")
    op.drop_index("ix_pig_daily_actions_action_type", table_name="pig_daily_actions")
    op.drop_index("ix_pig_daily_actions_pig_id", table_name="pig_daily_actions")
    op.drop_table("pig_daily_actions")
