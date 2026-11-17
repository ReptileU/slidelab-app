"""Заказ: «сразу всю презентацию» без бесплатной обложки

Revision ID: 6d2a9c4e1b57
Revises: 4b8e1f2a6c90
Create Date: 2026-11-17 15:30:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "6d2a9c4e1b57"
down_revision: str | None = "4b8e1f2a6c90"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("orders", schema=None) as batch_op:
        batch_op.add_column(sa.Column("skip_cover", sa.Boolean(), server_default="0", nullable=False))


def downgrade() -> None:
    with op.batch_alter_table("orders", schema=None) as batch_op:
        batch_op.drop_column("skip_cover")
