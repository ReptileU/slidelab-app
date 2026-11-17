"""Заказ: к какому сроку нужна презентация

Revision ID: 4b8e1f2a6c90
Revises: 9a4d2c6e8b31
Create Date: 2026-11-17 15:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "4b8e1f2a6c90"
down_revision: str | None = "9a4d2c6e8b31"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("orders", schema=None) as batch_op:
        batch_op.add_column(sa.Column("due_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("orders", schema=None) as batch_op:
        batch_op.drop_column("due_at")
