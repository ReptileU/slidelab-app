"""Напоминание о пакете: когда отправили

Revision ID: 7c3e9b1d4f20
Revises: 5f1c2a7d9e01
Create Date: 2026-11-13 11:50:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "7c3e9b1d4f20"
down_revision: str | None = "5f1c2a7d9e01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("user_packages", schema=None) as batch_op:
        batch_op.add_column(sa.Column("reminded_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("user_packages", schema=None) as batch_op:
        batch_op.drop_column("reminded_at")
