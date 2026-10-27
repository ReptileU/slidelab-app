from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from slidelab.core.enums import LedgerReason, PaymentProvider, PaymentStatus, PlanCode
from slidelab.core.models.base import Base, CreatedAtMixin, str_enum


class PriceRule(Base):
    """Прайс одной строкой (id = 1). Менеджер меняет цены без деплоя."""

    __tablename__ = "price_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    s10: Mapped[int]
    s20: Mapped[int]
    s30: Mapped[int]
    urgent_pct: Mapped[int]  # надбавка за срочность, %
    extra_text: Mapped[int]  # «текст под ключ»
    extra_notes: Mapped[int]  # «конспект для выступления»
    first_order_s10: Mapped[int]  # цена первого заказа «Мини» для нового клиента
    uzs_per_star: Mapped[int] = mapped_column(server_default="155")  # курс для оплаты звёздами


class PackagePlan(Base):
    __tablename__ = "package_plans"

    code: Mapped[PlanCode] = mapped_column(str_enum(PlanCode), primary_key=True)
    count: Mapped[int]  # сколько презентаций
    price: Mapped[int]
    days: Mapped[int]  # срок действия
    notes_free: Mapped[bool] = mapped_column(default=False)
    priority: Mapped[bool] = mapped_column(default=False)
    max_parallel: Mapped[int | None]  # сколько заказов из пакета одновременно в работе
    sort: Mapped[int] = mapped_column(default=0)
    is_active: Mapped[bool] = mapped_column(default=True)


class UserPackage(CreatedAtMixin, Base):
    __tablename__ = "user_packages"
    __table_args__ = (CheckConstraint("left_count >= 0", name="left_non_negative"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    plan_code: Mapped[PlanCode] = mapped_column(str_enum(PlanCode), ForeignKey("package_plans.code"))
    total: Mapped[int]
    left: Mapped[int] = mapped_column("left_count")  # LEFT — ключевое слово SQL
    expires_at: Mapped[datetime]


class PackageLedger(CreatedAtMixin, Base):
    """Каждое движение по пакету отдельной строкой — остаток всегда можно пересчитать."""

    __tablename__ = "package_ledger"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_package_id: Mapped[int] = mapped_column(ForeignKey("user_packages.id"), index=True)
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"), index=True)
    delta: Mapped[int]
    reason: Mapped[LedgerReason] = mapped_column(str_enum(LedgerReason))


class Payment(CreatedAtMixin, Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"), index=True)
    plan_code: Mapped[PlanCode | None] = mapped_column(str_enum(PlanCode))  # покупка пакета
    user_package_id: Mapped[int | None] = mapped_column(ForeignKey("user_packages.id"))
    # покупка пакета с зачётом сданного заказа
    credit_order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"))
    provider: Mapped[PaymentProvider] = mapped_column(str_enum(PaymentProvider))
    amount: Mapped[int]
    currency: Mapped[str] = mapped_column(String(3))  # UZS или XTR (звёзды)
    status: Mapped[PaymentStatus] = mapped_column(str_enum(PaymentStatus), default=PaymentStatus.PENDING)
    external_id: Mapped[str | None] = mapped_column(String(128), unique=True)  # charge_id и т.п.
    raw: Mapped[dict[str, Any] | None]


class Promo(Base):
    """Акция «подарок за пакет»: какой Telegram Gift получает покупатель каждого тарифа."""

    __tablename__ = "promos"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True)
    starts_at: Mapped[datetime]
    ends_at: Mapped[datetime]
    gifts: Mapped[dict[str, Any]]  # {"week": "<gift_id>", ...}
    texts: Mapped[dict[str, Any]]  # {"ru": {"week": "🧸 мишка в подарок"}, ...}
    is_active: Mapped[bool] = mapped_column(default=True)
