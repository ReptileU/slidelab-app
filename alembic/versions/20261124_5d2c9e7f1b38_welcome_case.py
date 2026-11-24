"""Приветственный кейс для пришедшего по ссылке друга.

Revision ID: 5d2c9e7f1b38
Revises: 8b3f1d6e2a47
Create Date: 2026-11-24
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "5d2c9e7f1b38"
down_revision: str | None = "8b3f1d6e2a47"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("referrals") as b:
        b.add_column(sa.Column("welcome_opened_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("referrals") as b:
        b.drop_column("welcome_opened_at")
