"""Postgres: типы недавних таблиц и колонок — как в моделях (BIGINT, время с поясом), плюс внешние ключи

На SQLite ничего не меняет (там типы условные).

Revision ID: 7d1e4f2a9c35
Revises: 3a6c8e1f5b92
Create Date: 2026-11-19 03:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "7d1e4f2a9c35"
down_revision: str | None = "3a6c8e1f5b92"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

BIGINT = {
    "coupons": ["id", "user_id", "order_id", "used_order_id", "gift_id", "from_user_id"],
    "gifts": ["id", "from_user_id", "coupon_id", "count", "package_id", "to_user_id"],
    "orders": ["coupon_id"],
    "package_boxes": ["id", "user_id", "user_package_id", "coupon_id", "count"],
}
TZ = {
    "coupons": ["created_at"],
    "gifts": ["expires_at", "done_at", "created_at"],
    "orders": ["due_at"],
    "package_boxes": ["opened_at", "created_at"],
    "user_packages": ["reminded_at"],
    "users": ["work_refund_at"],
}
FKS = [
    ("fk_gifts_coupon_id_coupons", "gifts", "coupon_id"),
    ("fk_orders_coupon_id_coupons", "orders", "coupon_id"),
    ("fk_package_boxes_coupon_id_coupons", "package_boxes", "coupon_id"),
]


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    for table, cols in BIGINT.items():
        for col in cols:
            op.alter_column(table, col, type_=sa.BigInteger())
    for table, cols in TZ.items():
        for col in cols:
            # старые значения записаны в UTC без пояса
            op.alter_column(table, col, type_=sa.DateTime(timezone=True), postgresql_using=f"{col} AT TIME ZONE 'UTC'")
    for name, table, col in FKS:
        op.create_foreign_key(name, table, "coupons", [col], ["id"])


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    for name, table, _ in FKS:
        op.drop_constraint(name, table, type_="foreignkey")
