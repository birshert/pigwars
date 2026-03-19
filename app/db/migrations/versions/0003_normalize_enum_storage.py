"""normalize enum storage

Revision ID: 0003_normalize_enum_storage
Revises: 0002_feature_systems
Create Date: 2026-03-19 01:00:00
"""

from __future__ import annotations

from alembic import op


revision = "0003_normalize_enum_storage"
down_revision = "0002_feature_systems"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("UPDATE pigs SET status = lower(status) WHERE status IS NOT NULL")
    op.execute("UPDATE pigs SET trait = lower(trait) WHERE trait IS NOT NULL")
    op.execute("UPDATE pig_items SET item_type = lower(item_type) WHERE item_type IS NOT NULL")
    op.execute("UPDATE pig_raids SET destination = lower(destination) WHERE destination IS NOT NULL")
    op.execute("UPDATE pig_raids SET status = lower(status) WHERE status IS NOT NULL")


def downgrade() -> None:
    op.execute("UPDATE pigs SET status = upper(status) WHERE status IS NOT NULL")
    op.execute("UPDATE pigs SET trait = upper(trait) WHERE trait IS NOT NULL")
    op.execute("UPDATE pig_items SET item_type = upper(item_type) WHERE item_type IS NOT NULL")
    op.execute("UPDATE pig_raids SET destination = upper(destination) WHERE destination IS NOT NULL")
    op.execute("UPDATE pig_raids SET status = upper(status) WHERE status IS NOT NULL")
