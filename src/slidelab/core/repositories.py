"""Доступ к БД без бизнес-правил. Сервисы решают, репозитории только читают и пишут."""

from collections.abc import Iterable
from datetime import datetime

from sqlalchemy import exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from slidelab.core.enums import OrderStatus, PaymentStatus, PlanCode, SlideTier, Stage
from slidelab.core.errors import NotFoundError
from slidelab.core.models import (
    Order,
    PackageLedger,
    PackagePlan,
    Payment,
    PriceRule,
    ShowcaseStyle,
    User,
    UserPackage,
)
from slidelab.core.services.pricing import PriceRules


async def get_price_rules(session: AsyncSession) -> PriceRules:
    row = await get_price_rule_row(session)
    return PriceRules(
        base={SlideTier.S10: row.s10, SlideTier.S20: row.s20, SlideTier.S30: row.s30},
        urgent_pct=row.urgent_pct,
        extra_text=row.extra_text,
        extra_notes=row.extra_notes,
        first_order_s10=row.first_order_s10,
    )


async def get_plan(session: AsyncSession, code: PlanCode) -> PackagePlan:
    plan = await session.get(PackagePlan, code)
    if plan is None or not plan.is_active:
        raise NotFoundError(f"Тариф {code} не найден")
    return plan


async def get_style_id(session: AsyncSession, key: str) -> int:
    style_id = await session.scalar(select(ShowcaseStyle.id).where(ShowcaseStyle.key == key))
    if style_id is None:
        raise NotFoundError(f"Стиль {key} не найден")
    return style_id


async def get_user(session: AsyncSession, user_id: int) -> User:
    user = await session.get(User, user_id)
    if user is None:
        raise NotFoundError(f"Пользователь {user_id} не найден")
    return user


async def get_order(session: AsyncSession, order_id: int, *, for_update: bool = False) -> Order:
    stmt = select(Order).where(Order.id == order_id)
    if for_update:  # свежие данные, даже если заказ уже загружен в сессию
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    order = await session.scalar(stmt)
    if order is None:
        raise NotFoundError(f"Заказ #{order_id} не найден")
    return order


async def get_order_by_idempotency_key(session: AsyncSession, user_id: int, key: str) -> Order | None:
    return await session.scalar(select(Order).where(Order.user_id == user_id, Order.idempotency_key == key))


async def has_orders(session: AsyncSession, user_id: int) -> bool:
    """Был ли у клиента хоть один не отменённый заказ (иначе он новый)."""
    stmt = select(exists().where(Order.user_id == user_id, Order.status != OrderStatus.CANCELLED))
    return bool(await session.scalar(stmt))


async def count_package_orders_in_work(session: AsyncSession, user_id: int, exclude_id: int) -> int:
    stmt = select(func.count(Order.id)).where(
        Order.user_id == user_id,
        Order.package_cost > 0,
        Order.status.in_([OrderStatus.WORK, OrderStatus.REVISION]),
        Order.id != exclude_id,
    )
    return int(await session.scalar(stmt) or 0)


async def is_order_paid(session: AsyncSession, order_id: int) -> bool:
    stmt = select(exists().where(Payment.order_id == order_id, Payment.status == PaymentStatus.PAID))
    return bool(await session.scalar(stmt))


async def order_package_debits(session: AsyncSession, order_id: int) -> list[PackageLedger]:
    stmt = select(PackageLedger).where(PackageLedger.order_id == order_id).order_by(PackageLedger.id)
    return list((await session.scalars(stmt)).all())


async def get_active_package(
    session: AsyncSession, user_id: int, now: datetime, *, for_update: bool = False
) -> UserPackage | None:
    """Последний купленный пакет, если он ещё действует."""
    stmt = (
        select(UserPackage)
        .where(UserPackage.user_id == user_id, UserPackage.expires_at > now)
        .order_by(UserPackage.id.desc())
        .limit(1)
    )
    if for_update:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    return await session.scalar(stmt)


ACTIVE_STATUSES = (
    OrderStatus.NEW,
    OrderStatus.COVER,
    OrderStatus.AWAITING_PAYMENT,
    OrderStatus.WORK,
    OrderStatus.REVISION,
)


async def list_user_orders(session: AsyncSession, user_id: int, limit: int = 20) -> list[Order]:
    stmt = select(Order).where(Order.user_id == user_id).order_by(Order.id.desc()).limit(limit)
    return list((await session.scalars(stmt)).all())


async def latest_active_order(session: AsyncSession, user_id: int) -> Order | None:
    stmt = (
        select(Order)
        .where(Order.user_id == user_id, Order.status.in_(ACTIVE_STATUSES))
        .order_by(Order.id.desc())
        .limit(1)
    )
    return await session.scalar(stmt)


async def get_user_by_tg(session: AsyncSession, tg_id: int) -> User | None:
    return await session.scalar(select(User).where(User.tg_id == tg_id))


async def get_user_by_topic(session: AsyncSession, topic_id: int) -> User | None:
    return await session.scalar(select(User).where(User.forum_topic_id == topic_id))


async def get_payment(session: AsyncSession, payment_id: int, *, for_update: bool = False) -> Payment:
    stmt = select(Payment).where(Payment.id == payment_id)
    if for_update:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    payment = await session.scalar(stmt)
    if payment is None:
        raise NotFoundError(f"Платёж {payment_id} не найден")
    return payment


async def latest_payment(session: AsyncSession, order_id: int, status: PaymentStatus | None = None) -> Payment | None:
    stmt = select(Payment).where(Payment.order_id == order_id)
    if status is not None:
        stmt = stmt.where(Payment.status == status)
    return await session.scalar(stmt.order_by(Payment.id.desc()).limit(1))


async def get_price_rule_row(session: AsyncSession) -> PriceRule:
    row = await session.get(PriceRule, 1)
    if row is None:
        raise NotFoundError("Прайс не заполнен: запустите python -m slidelab.core.seed")
    return row


async def orders_in_stages(session: AsyncSession, stages: Iterable[Stage]) -> dict[int, Order]:
    stmt = select(Order).where(Order.stage.in_(list(stages)), Order.status.in_(ACTIVE_STATUSES))
    return {o.id: o for o in (await session.scalars(stmt)).all()}


async def orders_to_watch(session: AsyncSession) -> list[Order]:
    """Незавершённые заказы для сторожа."""
    stmt = select(Order).where(Order.status.in_(ACTIVE_STATUSES), Order.hidden.is_(False), Order.no_alert.is_(False))
    return list((await session.scalars(stmt)).all())
