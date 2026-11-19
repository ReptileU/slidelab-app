"""points: баллы за покупки, пакет за баллы, скидка из пакета

Revision ID: 4c7e2a9d1f63
Revises: 3a6c8e1f5b92
Create Date: 2026-11-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "4c7e2a9d1f63"
down_revision: str | None = "3a6c8e1f5b92"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("users") as b:
        b.add_column(sa.Column("points", sa.Integer(), nullable=False, server_default="0"))
        b.add_column(sa.Column("points_expire_at", sa.DateTime(timezone=True), nullable=True))
        b.add_column(sa.Column("discount_pct", sa.Integer(), nullable=True))
    with op.batch_alter_table("orders") as b:
        b.add_column(sa.Column("discount_pct", sa.Integer(), nullable=True))
    with op.batch_alter_table("package_boxes") as b:
        b.add_column(sa.Column("for_points", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_table(
        "points_ledger",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("delta", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(32), nullable=False),
        sa.Column("order_id", sa.Integer(), sa.ForeignKey("orders.id"), nullable=True),
        sa.Column("payment_id", sa.Integer(), sa.ForeignKey("payments.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("points_ledger")
    with op.batch_alter_table("package_boxes") as b:
        b.drop_column("for_points")
    with op.batch_alter_table("orders") as b:
        b.drop_column("discount_pct")
    with op.batch_alter_table("users") as b:
        b.drop_column("discount_pct")
        b.drop_column("points_expire_at")
        b.drop_column("points")
