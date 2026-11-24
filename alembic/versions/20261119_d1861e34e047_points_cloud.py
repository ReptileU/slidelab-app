"""points + cloud

Revision ID: d1861e34e047
Revises: 4c7e2a9d1f63, c4a8e2b6d913
Create Date: 2026-11-19 17:41:03.335952
"""

from collections.abc import Sequence

revision: str = "d1861e34e047"
down_revision: str | tuple[str, ...] | None = ("4c7e2a9d1f63", "c4a8e2b6d913")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
