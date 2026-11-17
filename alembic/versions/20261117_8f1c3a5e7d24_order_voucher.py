"""Заказ: отменённый оплаченный заказ даёт оплаченную презентацию на следующий

Revision ID: 8f1c3a5e7d24
Revises: 6d2a9c4e1b57
Create Date: 2026-11-17 16:10:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "8f1c3a5e7d24"
down_revision: str | None = "6d2a9c4e1b57"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("orders", schema=None) as batch_op:
        batch_op.add_column(sa.Column("voucher_open", sa.Boolean(), server_default="0", nullable=False))
        batch_op.add_column(sa.Column("voucher_from_id", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("orders", schema=None) as batch_op:
        batch_op.drop_column("voucher_from_id")
        batch_op.drop_column("voucher_open")
