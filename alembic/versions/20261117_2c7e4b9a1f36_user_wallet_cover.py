"""Кошелёк в профиле: обложка из фото клиента

Revision ID: 2c7e4b9a1f36
Revises: 8f1c3a5e7d24
Create Date: 2026-11-17 17:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "2c7e4b9a1f36"
down_revision: str | None = "8f1c3a5e7d24"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(sa.Column("wallet_cover", sa.String(length=64), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_column("wallet_cover")
