"""Плашка на титульном слайде: выполнил, группа, принял

Revision ID: 5f1c2a7d9e01
Revises: b48a1c2a4ae3
Create Date: 2026-11-02 01:50:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "5f1c2a7d9e01"
down_revision: str | None = "b48a1c2a4ae3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("orders", schema=None) as batch_op:
        batch_op.add_column(sa.Column("title_author", sa.String(length=120), nullable=True))
        batch_op.add_column(sa.Column("title_group", sa.String(length=60), nullable=True))
        batch_op.add_column(sa.Column("title_teacher", sa.String(length=120), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("orders", schema=None) as batch_op:
        batch_op.drop_column("title_teacher")
        batch_op.drop_column("title_group")
        batch_op.drop_column("title_author")
