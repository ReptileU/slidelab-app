"""Купоны отдельной таблицей и подарки (купон или презентации из пакета по ссылке)

Revision ID: 5e9d1c3b7a48
Revises: 2c7e4b9a1f36
Create Date: 2026-11-17 17:30:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "5e9d1c3b7a48"
down_revision: str | None = "2c7e4b9a1f36"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "gifts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(32), nullable=False, unique=True),
        sa.Column("from_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("coupon_id", sa.Integer(), nullable=True),
        sa.Column("plan_code", sa.String(32), nullable=True),
        sa.Column("count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("to_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("done_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "coupons",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("slides", sa.String(32), nullable=False),
        sa.Column("origin", sa.String(32), nullable=False),
        sa.Column("order_id", sa.Integer(), sa.ForeignKey("orders.id"), nullable=True),
        sa.Column("used_order_id", sa.Integer(), sa.ForeignKey("orders.id"), nullable=True),
        sa.Column("gift_id", sa.Integer(), sa.ForeignKey("gifts.id"), nullable=True),
        sa.Column("from_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    with op.batch_alter_table("orders", schema=None) as batch_op:
        batch_op.add_column(sa.Column("coupon_id", sa.Integer(), nullable=True))

    # Перенос: отменённые оплаченные заказы → купоны; заказы, оплаченные ими, → ссылка на купон
    conn = op.get_bind()
    for oid, uid, slides in conn.execute(
        sa.text("SELECT id, user_id, slides FROM orders WHERE voucher_open = 1")
    ).fetchall():
        conn.execute(
            sa.text("INSERT INTO coupons (user_id, slides, origin, order_id) VALUES (:u, :s, 'cancel', :o)"),
            {"u": uid, "s": slides, "o": oid},
        )
    for oid, uid, src in conn.execute(
        sa.text("SELECT id, user_id, voucher_from_id FROM orders WHERE voucher_from_id IS NOT NULL")
    ).fetchall():
        slides = conn.execute(sa.text("SELECT slides FROM orders WHERE id = :i"), {"i": src}).scalar()
        cid = conn.execute(
            sa.text(
                "INSERT INTO coupons (user_id, slides, origin, order_id, used_order_id)"
                " VALUES (:u, :s, 'cancel', :src, :o)"
            ),
            {"u": uid, "s": slides, "src": src, "o": oid},
        ).lastrowid
        conn.execute(sa.text("UPDATE orders SET coupon_id = :c WHERE id = :o"), {"c": cid, "o": oid})

    with op.batch_alter_table("orders", schema=None) as batch_op:
        batch_op.drop_column("voucher_from_id")
        batch_op.drop_column("voucher_open")


def downgrade() -> None:
    with op.batch_alter_table("orders", schema=None) as batch_op:
        batch_op.add_column(sa.Column("voucher_open", sa.Boolean(), server_default="0", nullable=False))
        batch_op.add_column(sa.Column("voucher_from_id", sa.Integer(), nullable=True))
        batch_op.drop_column("coupon_id")
    op.drop_table("coupons")
    op.drop_table("gifts")
