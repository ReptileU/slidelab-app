"""Короткая заявка «бесплатная обложка»: только тема и стиль, остальное — когда обложка понравится.

Revision ID: 9e4b2c7a6d15
Revises: 5d2c9e7f1b38
Create Date: 2026-11-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "9e4b2c7a6d15"
down_revision: str | None = "5d2c9e7f1b38"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("orders") as b:
        b.add_column(sa.Column("quick", sa.Boolean(), server_default=sa.false(), nullable=False))


def downgrade() -> None:
    with op.batch_alter_table("orders") as b:
        b.drop_column("quick")
