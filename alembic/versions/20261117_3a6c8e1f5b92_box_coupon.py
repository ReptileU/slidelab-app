"""Бонус-пакет: «1 презентация» выпадает купоном (без пакета) — user_package_id может быть пустым

Revision ID: 3a6c8e1f5b92
Revises: 9b2f6d4e8c13
Create Date: 2026-11-17 20:30:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "3a6c8e1f5b92"
down_revision: str | None = "9b2f6d4e8c13"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("package_boxes", schema=None) as batch_op:
        batch_op.alter_column("user_package_id", existing_type=sa.Integer(), nullable=True)
        batch_op.add_column(sa.Column("coupon_id", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("package_boxes", schema=None) as batch_op:
        batch_op.drop_column("coupon_id")
        batch_op.alter_column("user_package_id", existing_type=sa.Integer(), nullable=False)
