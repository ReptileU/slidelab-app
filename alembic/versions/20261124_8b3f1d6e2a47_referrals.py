"""Приглашения друзей: кто кого привёл и когда друг впервые заплатил.

Revision ID: 8b3f1d6e2a47
Revises: 4c7e2a9d1f63
Create Date: 2026-11-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "8b3f1d6e2a47"
down_revision: str | None = "4c7e2a9d1f63"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "referrals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "inviter_id", sa.Integer(), sa.ForeignKey("users.id", name="fk_referrals_inviter_id_users"), nullable=False
        ),
        sa.Column(
            "friend_id", sa.Integer(), sa.ForeignKey("users.id", name="fk_referrals_friend_id_users"), nullable=False
        ),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("points", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("friend_id", name="uq_referrals_friend_id"),
    )
    op.create_index("ix_referrals_inviter_id", "referrals", ["inviter_id"])


def downgrade() -> None:
    op.drop_index("ix_referrals_inviter_id", table_name="referrals")
    op.drop_table("referrals")
