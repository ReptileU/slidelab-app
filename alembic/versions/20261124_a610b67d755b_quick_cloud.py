"""quick + cloud

Revision ID: a610b67d755b
Revises: 6d14a1564dc4, 9e4b2c7a6d15
Create Date: 2026-11-24 16:10:36.247071
"""

from collections.abc import Sequence

revision: str = "a610b67d755b"
down_revision: str | tuple[str, ...] | None = ("6d14a1564dc4", "9e4b2c7a6d15")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
