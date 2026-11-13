"""Бонус-пакет: что выпало и открыл ли клиент

Revision ID: 9a4d2c6e8b31
Revises: 7c3e9b1d4f20
Create Date: 2026-11-13 23:10:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "9a4d2c6e8b31"
down_revision: str | None = "7c3e9b1d4f20"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "package_boxes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("user_package_id", sa.Integer(), nullable=False),
        sa.Column("prize", sa.String(length=32), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.Column("opened_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["user_package_id"], ["user_packages.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_package_boxes_user_id", "package_boxes", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_package_boxes_user_id", table_name="package_boxes")
    op.drop_table("package_boxes")
