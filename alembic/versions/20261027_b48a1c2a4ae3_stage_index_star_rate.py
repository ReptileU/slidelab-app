"""Индекс по стадии конвейера; курс звёзд 155 сум, как в прежнем боте (STAR_RATE)

Revision ID: b48a1c2a4ae3
Revises: 2d99410cbc0e
Create Date: 2026-10-27 05:43:25.566165
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b48a1c2a4ae3"
down_revision: str | None = "2d99410cbc0e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("orders", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_orders_stage"), ["stage"], unique=False)
    with op.batch_alter_table("price_rules", schema=None) as batch_op:
        batch_op.alter_column("uzs_per_star", server_default="155", existing_type=sa.BigInteger())
    # 170 — прежнее значение по умолчанию этой миграции; свой курс, если его меняли, не трогаем
    op.execute("UPDATE price_rules SET uzs_per_star = 155 WHERE uzs_per_star = 170")


def downgrade() -> None:
    with op.batch_alter_table("price_rules", schema=None) as batch_op:
        batch_op.alter_column("uzs_per_star", server_default="170", existing_type=sa.BigInteger())
    with op.batch_alter_table("orders", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_orders_stage"))
