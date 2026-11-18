"""Облако: копии файлов конвейера и служебных файлов в базе (диск сервера временный)

Revision ID: c4a8e2b6d913
Revises: 7d1e4f2a9c35
Create Date: 2026-11-19 03:30:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c4a8e2b6d913"
down_revision: str | None = "7d1e4f2a9c35"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "stored_files",
        sa.Column("path", sa.String(512), primary_key=True),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        sa.Column("size", sa.BigInteger(), nullable=False),
        sa.Column("mtime", sa.Float(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("stored_files")
