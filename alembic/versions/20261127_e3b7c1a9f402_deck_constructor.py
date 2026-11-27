"""Конструктор презентаций: decks, deck_assets, кредиты конструктора.

Revision ID: e3b7c1a9f402
Revises: a610b67d755b
Create Date: 2026-11-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e3b7c1a9f402"
down_revision: str | None = "a610b67d755b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

BigInt = sa.BigInteger().with_variant(sa.Integer(), "sqlite")
Json = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
TS = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "decks",
        sa.Column("id", BigInt, primary_key=True),
        sa.Column("user_id", BigInt, sa.ForeignKey("users.id", name="fk_decks_user_id_users"), nullable=False),
        sa.Column("title", sa.String(120), nullable=False),
        sa.Column("lang", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("version", BigInt, server_default="1", nullable=False),
        sa.Column("body", Json, nullable=False),
        sa.Column("updated_at", TS, nullable=False),
        sa.Column("created_at", TS, server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_decks"),
    )
    op.create_index("ix_decks_user_updated", "decks", ["user_id", "updated_at"])
    op.create_table(
        "deck_assets",
        sa.Column("id", BigInt, primary_key=True),
        sa.Column(
            "deck_id",
            BigInt,
            sa.ForeignKey("decks.id", ondelete="CASCADE", name="fk_deck_assets_deck_id_decks"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("storage_key", sa.String(256), nullable=False),
        sa.Column("width", BigInt, nullable=False),
        sa.Column("height", BigInt, nullable=False),
        sa.Column("bytes", BigInt, nullable=False),
        sa.Column("created_at", TS, server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_deck_assets"),
    )
    op.create_index("ix_deck_assets_deck_id", "deck_assets", ["deck_id"])
    op.create_table(
        "credits_ledger",
        sa.Column("id", BigInt, primary_key=True),
        sa.Column(
            "user_id", BigInt, sa.ForeignKey("users.id", name="fk_credits_ledger_user_id_users"), nullable=False
        ),
        sa.Column("delta", BigInt, nullable=False),
        sa.Column("reason", sa.String(32), nullable=False),
        sa.Column("action", sa.String(32), nullable=True),
        sa.Column(
            "deck_id",
            BigInt,
            sa.ForeignKey("decks.id", ondelete="SET NULL", name="fk_credits_ledger_deck_id_decks"),
            nullable=True,
        ),
        sa.Column("created_at", TS, server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_credits_ledger"),
    )
    op.create_index("ix_credits_ledger_user_id", "credits_ledger", ["user_id"])
    with op.batch_alter_table("users") as b:
        b.add_column(sa.Column("credits", BigInt, server_default="0", nullable=False))
        b.add_column(sa.Column("credits_refill_at", TS, nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("users") as b:
        b.drop_column("credits_refill_at")
        b.drop_column("credits")
    op.drop_index("ix_credits_ledger_user_id", "credits_ledger")
    op.drop_table("credits_ledger")
    op.drop_index("ix_deck_assets_deck_id", "deck_assets")
    op.drop_table("deck_assets")
    op.drop_index("ix_decks_user_updated", "decks")
    op.drop_table("decks")
