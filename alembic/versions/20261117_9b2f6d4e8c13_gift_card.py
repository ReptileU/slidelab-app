"""Подарок: открытка (фото), которую пересылают другу

Revision ID: 9b2f6d4e8c13
Revises: 5e9d1c3b7a48
Create Date: 2026-11-17 19:50:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "9b2f6d4e8c13"
down_revision: str | None = "5e9d1c3b7a48"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("gifts", schema=None) as batch_op:
        batch_op.add_column(sa.Column("card_file_id", sa.String(length=256), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("gifts", schema=None) as batch_op:
        batch_op.drop_column("card_file_id")
