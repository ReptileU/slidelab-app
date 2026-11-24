"""Баллы за покупки и пакеты за баллы."""

import random
from collections.abc import Callable
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from conftest import FakeClock
from slidelab.core import repositories as repo
from slidelab.core.enums import BoxPrize, CouponOrigin, OrderStatus, PaymentProvider, PlanCode, PointsReason, SlideTier
from slidelab.core.models import Coupon, PackageBox, PointsLedger, User
from slidelab.core.services import lucky, points
from slidelab.core.services.payments import PaymentService
from slidelab.core.services.points import NotEnoughPointsError, PointsService
from test_orders import draft
from test_payments import buy_lucky


class Pick(random.Random):
    """Розыгрыш с заранее известным призом (код + значение)."""

    def __init__(self, code: BoxPrize, value: int) -> None:
        super().__init__()
        self.code, self.value = code, value

    def choices(self, population: Any, weights: Any = None, *, cum_weights: Any = None, k: int = 1) -> list[Any]:
        return [next(p for p in population if p.code is self.code and p.value == self.value)]


@pytest.fixture
def payments(session: AsyncSession, clock: FakeClock) -> PaymentService:
    return PaymentService(session, clock)


async def pay_order(payments: PaymentService, user_id: int, **kwargs: Any) -> Any:
    order = await payments.orders.create(user_id, draft(**kwargs))
    payment = await payments.for_order(order, PaymentProvider.MANUAL_CARD)
    return await payments.mark_paid(payment.id)


def test_boxes_are_fair() -> None:
    for box in points.BOXES.values():
        assert sum(p.weight for p in box.prizes) == 1000
        assert all(p.value > 0 for p in box.prizes)  # пустых призов нет
    prices = [b.price for b in points.BOXES.values()]
    assert prices == sorted(prices)


async def test_points_for_paid_order(payments: PaymentService, make_user: Callable[..., Any]) -> None:
    user = await make_user()
    result = await pay_order(payments, user.id)
    assert result.points == points.PER_PRESENTATION
    big = await pay_order(payments, user.id, slides=SlideTier.S30)
    assert big.points == 2 * points.PER_PRESENTATION  # 21–30 слайдов — как две презентации
    assert user.points == 3 * points.PER_PRESENTATION
    assert user.points_expire_at is not None


async def test_points_for_plan_and_lucky(payments: PaymentService, make_user: Callable[..., Any]) -> None:
    user = await make_user()
    plan = await repo.get_plan(payments.session, PlanCode.MONTH)
    payment = await payments.for_plan(user.id, PlanCode.MONTH, PaymentProvider.MANUAL_CARD)
    assert (await payments.mark_paid(payment.id)).points == plan.count * points.PER_PRESENTATION
    assert (await buy_lucky(payments, user.id, BoxPrize.ONE)).points == points.PER_PRESENTATION


async def test_no_points_for_coupon_order(
    payments: PaymentService, session: AsyncSession, make_user: Callable[..., Any]
) -> None:
    """Презентация по купону куплена не деньгами — баллов нет (даже если доплатил за срочность)."""
    user = await make_user()
    session.add(Coupon(user_id=user.id, slides=SlideTier.S20, origin=CouponOrigin.BONUS))
    await session.flush()
    order = await payments.orders.create(user.id, draft())
    assert order.coupon_id is not None
    if not order.is_paid:
        payment = await payments.for_order(order, PaymentProvider.MANUAL_CARD)
        assert (await payments.mark_paid(payment.id)).points == 0
    assert user.points == 0


async def test_points_expire_and_purchase_extends(
    session: AsyncSession, clock: FakeClock, make_user: Callable[..., Any]
) -> None:
    user = await make_user()
    service = PointsService(session, clock)
    await service.earn(user, 1, PointsReason.ORDER)
    clock.advance(days=points.EXPIRE_DAYS - 1)
    await service.earn(user, 1, PointsReason.ORDER)  # покупка продлевает срок всех баллов
    clock.advance(days=points.EXPIRE_DAYS - 1)
    assert await service.balance(user) == 2 * points.PER_PRESENTATION
    clock.advance(days=2)
    assert await service.balance(user) == 0
    burned = await session.scalar(
        select(func.sum(PointsLedger.delta)).where(PointsLedger.reason == PointsReason.EXPIRED)
    )
    assert burned == -2 * points.PER_PRESENTATION


async def test_open_box_needs_points(session: AsyncSession, clock: FakeClock, make_user: Callable[..., Any]) -> None:
    user = await make_user(points=99)
    with pytest.raises(NotEnoughPointsError):
        await PointsService(session, clock).open_box(user, "small")
    assert user.points == 99


async def test_box_coupons(session: AsyncSession, clock: FakeClock, make_user: Callable[..., Any]) -> None:
    user = await make_user(points=500)
    box = await PointsService(session, clock, Pick(BoxPrize.COUPONS, 5)).open_box(user, "large")
    assert user.points == 0
    assert box.for_points and box.opened_at is not None and box.count == 5
    coupons = await repo.open_coupons(session, user.id)
    assert len(coupons) == 5 and box.coupon_id == coupons[0].id


async def test_box_package_and_points(session: AsyncSession, clock: FakeClock, make_user: Callable[..., Any]) -> None:
    from slidelab.core.services.packages import PackageService

    user = await make_user(points=350)
    await PointsService(session, clock, Pick(BoxPrize.TWO, 2)).open_box(user, "medium")
    balance = await PackageService(session, clock).balance(user.id)
    assert balance is not None and balance.left == 2
    await PointsService(session, clock, Pick(BoxPrize.POINTS, 60)).open_box(user, "small")
    user.points += 500
    await PointsService(session, clock, Pick(BoxPrize.VIP, 10)).open_box(user, "large")
    vip = await PackageService(session, clock).balance(user.id)
    assert vip is not None and vip.plan is PlanCode.VIP
    assert user.points == 350 - 250 - 100 + 60


async def test_points_boxes_do_not_count_toward_lucky_limit(
    payments: PaymentService, session: AsyncSession, clock: FakeClock, make_user: Callable[..., Any]
) -> None:
    user = await make_user(points=100 * (lucky.LIMIT + 1))
    service = PointsService(session, clock, Pick(BoxPrize.ONE, 1))
    for _ in range(lucky.LIMIT + 1):
        await service.open_box(user, "small")
    await payments.for_plan(user.id, PlanCode.LUCKY, PaymentProvider.MANUAL_CARD)  # денежный пакет всё ещё можно
    pending = await session.scalar(select(func.count()).select_from(PackageBox))
    assert pending == lucky.LIMIT + 1


async def test_discount_card_applies_once_and_returns_on_cancel(
    payments: PaymentService, session: AsyncSession, clock: FakeClock, make_user: Callable[..., Any]
) -> None:
    user: User = await make_user(points=100)
    await pay_order(payments, user.id)  # первый заказ — у него своя скидка, наша на него не тратится
    user.points = 100
    await PointsService(session, clock, Pick(BoxPrize.DISCOUNT, 30)).open_box(user, "small")
    assert user.discount_pct == 30
    user.points = 200
    await PointsService(session, clock, Pick(BoxPrize.DISCOUNT, 20)).open_box(user, "small")
    assert user.discount_pct == 50  # карты складываются
    await PointsService(session, clock, Pick(BoxPrize.DISCOUNT, 30)).open_box(user, "small")
    assert user.discount_pct == points.DISCOUNT_MAX
    user.discount_pct = 30

    full = await payments.orders.quote(user.id, _req())
    order = await payments.orders.create(user.id, draft())
    assert order.discount_pct == 30 and user.discount_pct is None
    assert full.discount_pct == 30

    await payments.orders.transition(order.id, OrderStatus.CANCELLED, actor_id=None)
    assert user.discount_pct == 30  # не оплатил — скидка вернулась

    paid = await payments.orders.create(user.id, draft())
    payment = await payments.for_order(paid, PaymentProvider.MANUAL_CARD)
    await payments.mark_paid(payment.id)
    assert user.discount_pct is None


def _req() -> Any:
    from slidelab.core.services import pricing

    d = draft()
    return pricing.QuoteRequest(slides=d.slides, deadline=d.deadline)
