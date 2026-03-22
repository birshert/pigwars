"""dead pig status

Revision ID: 0007_dead_pig_status
Revises: 0006_disease_system
Create Date: 2026-03-22 14:45:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0007_dead_pig_status"
down_revision = "0006_disease_system"
branch_labels = None
depends_on = None


old_pig_status_enum = sa.Enum(
    "idle",
    "battle_ready",
    "in_battle",
    "on_raid",
    "quarantined",
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
    "dead",
    name="pigstatus",
    native_enum=False,
    length=32,
)


def upgrade() -> None:
    with op.batch_alter_table("pigs") as batch_op:
        batch_op.alter_column("status", type_=new_pig_status_enum, existing_type=old_pig_status_enum)


def downgrade() -> None:
    with op.batch_alter_table("pigs") as batch_op:
        batch_op.alter_column("status", type_=old_pig_status_enum, existing_type=new_pig_status_enum)
