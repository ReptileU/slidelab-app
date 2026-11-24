"""referrals + cloud

Revision ID: 4477320e8f0f
Revises: d1861e34e047, 8b3f1d6e2a47
Create Date: 2026-11-24 10:59:19.893608
"""

from collections.abc import Sequence

revision: str = "4477320e8f0f"
down_revision: str | tuple[str, ...] | None = ("d1861e34e047", "8b3f1d6e2a47")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
