"""welcome + cloud

Revision ID: 6d14a1564dc4
Revises: 4477320e8f0f, 5d2c9e7f1b38
Create Date: 2026-11-24 11:18:28.636046
"""

from collections.abc import Sequence

revision: str = "6d14a1564dc4"
down_revision: str | tuple[str, ...] | None = ("4477320e8f0f", "5d2c9e7f1b38")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
