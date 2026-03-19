"""daily group digest

Revision ID: 0005_daily_group_digest
Revises: 0004_daily_memes_and_events
Create Date: 2026-03-19 10:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0005_daily_group_digest"
down_revision = "0004_daily_memes_and_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "group_daily_digests",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("group_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False),
        sa.Column("digest_day", sa.Date(), nullable=False),
        sa.Column("status", sa.Enum("pending", "sent", "failed", "skipped", length=16, native_enum=False), nullable=False),
        sa.Column("source_payload", sa.JSON(), nullable=True),
        sa.Column("summary_text", sa.Text(), nullable=True),
        sa.Column("llm_model", sa.String(length=64), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("telegram_message_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=True),
        sa.Column("error_text", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["group_id"], ["telegram_groups.id"], name="fk_group_daily_digests_group_id_telegram_groups"),
        sa.PrimaryKeyConstraint("id", name="pk_group_daily_digests"),
        sa.UniqueConstraint("group_id", "digest_day", name="uq_group_daily_digests_group_day"),
    )
    op.create_index("ix_group_daily_digests_group_id", "group_daily_digests", ["group_id"], unique=False)
    op.create_index("ix_group_daily_digests_digest_day", "group_daily_digests", ["digest_day"], unique=False)
    op.create_index("ix_group_daily_digests_status", "group_daily_digests", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_group_daily_digests_status", table_name="group_daily_digests")
    op.drop_index("ix_group_daily_digests_digest_day", table_name="group_daily_digests")
    op.drop_index("ix_group_daily_digests_group_id", table_name="group_daily_digests")
    op.drop_table("group_daily_digests")
