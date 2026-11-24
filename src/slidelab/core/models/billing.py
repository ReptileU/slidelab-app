from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from slidelab.core.enums import (
    BoxPrize,
    CouponOrigin,
    GiftKind,
    GiftStatus,
    LedgerReason,
    PaymentProvider,
    PaymentStatus,
    PlanCode,
    PointsReason,
    SlideTier,
)
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
    reminded_at: Mapped[datetime | None]  # напоминание «осталась одна / скоро истекает» — один раз на пакет


class PackageBox(CreatedAtMixin, Base):
    """Купленный бонус-пакет. Приз разыгран и начислен при оплате; opened_at — клиент посмотрел, что выпало."""

    __tablename__ = "package_boxes"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    user_package_id: Mapped[int | None] = mapped_column(ForeignKey("user_packages.id"))  # выпал пакет
    coupon_id: Mapped[int | None] = mapped_column(ForeignKey("coupons.id", use_alter=True))  # выпал купон
    prize: Mapped[BoxPrize] = mapped_column(str_enum(BoxPrize))
    count: Mapped[int]  # сколько презентаций начислено (для скидки — процент, для баллов — сколько баллов)
    opened_at: Mapped[datetime | None]
    for_points: Mapped[bool] = mapped_column(default=False, server_default="0")  # пакет за баллы, а не за деньги


class PointsLedger(CreatedAtMixin, Base):
    """Каждое движение баллов отдельной строкой — баланс всегда можно проверить."""

    __tablename__ = "points_ledger"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    delta: Mapped[int]
    reason: Mapped[PointsReason] = mapped_column(str_enum(PointsReason))
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"))
    payment_id: Mapped[int | None] = mapped_column(ForeignKey("payments.id"))


class Referral(CreatedAtMixin, Base):
    """Друг пришёл по ссылке. Награда пригласившему — когда друг впервые заплатит деньгами (paid_at)."""

    __tablename__ = "referrals"

    id: Mapped[int] = mapped_column(primary_key=True)
    inviter_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    friend_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True)  # у человека один пригласивший
    paid_at: Mapped[datetime | None]
    points: Mapped[int] = mapped_column(default=0, server_default="0")  # сколько получил пригласивший


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
    as_gift: Mapped[bool] = mapped_column(default=False, server_default="0")  # пакет покупают в подарок
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


class Coupon(CreatedAtMixin, Base):
    """Одна оплаченная презентация без срока: от отменённого заказа или подарок.

    Покрывает базу заказа до своего объёма (больше слайдов — доплата разницы). Пока купон в подарке
    (gift_id), им нельзя заплатить.
    """

    __tablename__ = "coupons"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    slides: Mapped[SlideTier] = mapped_column(str_enum(SlideTier))
    origin: Mapped[CouponOrigin] = mapped_column(str_enum(CouponOrigin))
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"))  # отменённый заказ, из которого купон
    used_order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"))  # каким заказом потрачен
    gift_id: Mapped[int | None] = mapped_column(ForeignKey("gifts.id"))  # сейчас в подарке, ждёт получателя
    from_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))  # кто подарил


class Gift(CreatedAtMixin, Base):
    """Подарок по ссылке t.me/<бот>?start=gift_<code>: купон, пакет из кошелька целиком или купленный в подарок."""

    __tablename__ = "gifts"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True)
    from_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    kind: Mapped[GiftKind] = mapped_column(str_enum(GiftKind))
    coupon_id: Mapped[int | None] = mapped_column(ForeignKey("coupons.id", use_alter=True))
    plan_code: Mapped[PlanCode | None] = mapped_column(str_enum(PlanCode))  # пакет: какой тариф получит друг
    count: Mapped[int] = mapped_column(default=1)
    package_id: Mapped[int | None] = mapped_column(ForeignKey("user_packages.id"))  # пакет дарителя (отдан целиком)
    expires_at: Mapped[datetime | None]  # срок пакета дарителя; None — куплен в подарок, срок пойдёт с получения
    status: Mapped[GiftStatus] = mapped_column(str_enum(GiftStatus), default=GiftStatus.PENDING)
    to_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    done_at: Mapped[datetime | None]  # когда забрали или отменили
    card_file_id: Mapped[str | None] = mapped_column(String(256))  # открытка в Telegram — для пересылки другу
