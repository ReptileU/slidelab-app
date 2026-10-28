from collections.abc import Callable
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from conftest import FakeClock
from slidelab.core.enums import OrderStatus, PaymentProvider, PaymentStatus, PlanCode, SlideTier
from slidelab.core.errors import InvalidTransitionError
from slidelab.core.models import Order
from slidelab.core.services.packages import PackageService
from slidelab.core.services.payments import PaymentService
from slidelab.core.services.pricing import to_stars
from test_orders import draft

S = OrderStatus


@pytest.fixture
def payments(session: AsyncSession, clock: FakeClock) -> PaymentService:
    return PaymentService(session, clock)


async def with_cover(payments: PaymentService, user_id: int, **kwargs: Any) -> Order:
    order = await payments.orders.create(user_id, draft(**kwargs))
    await payments.orders.cover_sent(order, actor_id=None)
    return order


def test_stars_rounded_up_to_five() -> None:
    assert to_stars(29_000, 155) == 190  # 187.1 → 190
    assert to_stars(1, 155) == 5
    assert to_stars(775, 155) == 5


async def test_pay_with_stars_before_cover(payments: PaymentService, make_user: Callable[..., Any]) -> None:
    user = await make_user()
    order = await payments.orders.create(user.id, draft())
    payment = await payments.for_order(order, PaymentProvider.STARS)
    assert (payment.amount, payment.currency) == (190, "XTR")

    await payments.check_pending(payment.id, 190, "XTR")
    with pytest.raises(InvalidTransitionError):
        await payments.check_pending(payment.id, 100, "XTR")

    result = await payments.mark_paid(payment.id, external_id="charge-1")
    assert not result.started  # обложки ещё нет — начнём после её одобрения
    assert (order.status, order.is_paid) == (S.NEW, True)
    assert (await payments.mark_paid(payment.id, external_id="charge-1")).already_paid  # повтор от Telegram

    with pytest.raises(InvalidTransitionError):
        await payments.for_order(order, PaymentProvider.STARS)  # дважды не платят


async def test_payment_after_cover_starts_work(payments: PaymentService, make_user: Callable[..., Any]) -> None:
    user = await make_user()
    order = await with_cover(payments, user.id)
    payment = await payments.for_order(order, PaymentProvider.STARS)
    result = await payments.mark_paid(payment.id, external_id="c")
    assert result.started and order.status is S.WORK


async def test_cannot_pay_cancelled(payments: PaymentService, make_user: Callable[..., Any]) -> None:
    user = await make_user()
    order = await payments.orders.create(user.id, draft())
    payment = await payments.for_order(order, PaymentProvider.STARS)
    await payments.orders.transition(order.id, S.CANCELLED, actor_id=None)
    with pytest.raises(InvalidTransitionError):
        await payments.check_pending(payment.id, payment.amount, "XTR")


async def test_manager_confirms_card_transfer(payments: PaymentService, make_user: Callable[..., Any]) -> None:
    user, manager = await make_user(), await make_user(is_manager=True)
    order = await with_cover(payments, user.id, slides=SlideTier.S30)
    await payments.orders.approve_cover(order.id, user.id)
    pending = await payments.for_order(order, PaymentProvider.MANUAL_CARD)
    result = await payments.confirm_manual(order.id, manager.id)
    assert result.payment.id == pending.id and result.payment.status is PaymentStatus.PAID
    assert order.status is S.WORK


async def test_rejected_receipt(payments: PaymentService, make_user: Callable[..., Any]) -> None:
    user = await make_user()
    order = await with_cover(payments, user.id)
    payment = await payments.for_order(order, PaymentProvider.MANUAL_CARD)
    await payments.mark_failed(payment.id)
    assert payment.status is PaymentStatus.FAILED
    with pytest.raises(InvalidTransitionError):
        await payments.mark_paid(payment.id)
    assert not order.is_paid


async def test_package_purchase_activates_package(
    payments: PaymentService, session: AsyncSession, clock: FakeClock, make_user: Callable[..., Any]
) -> None:
    user = await make_user()
    payment = await payments.for_plan(user.id, PlanCode.VIP, PaymentProvider.STARS)
    assert payment.amount == 940  # 145 000 / 155 → вверх до 5
    result = await payments.mark_paid(payment.id, external_id="charge-2")
    assert result.package is not None and result.package.left == 10
    balance = await PackageService(session, clock).balance(user.id)
    assert balance is not None and balance.notes_free


async def test_package_with_order_credit(payments: PaymentService, make_user: Callable[..., Any]) -> None:
    """Сдали оплаченный заказ за 29 000 → пакет «4 презентации» за 64 000 − 29 000, и в нём на одну меньше."""
    user, stranger = await make_user(), await make_user()
    order = await with_cover(payments, user.id)
    await payments.orders.mark_paid(order, actor_id=None)
    await payments.orders.deliver(order, None)
    assert payments.packages.offer_credit(order, days=3)

    assert (await payments.plan_quote(PlanCode.MONTH, order.id, stranger.id)).amount == 64_000  # чужой
    q = await payments.plan_quote(PlanCode.MONTH, order.id, user.id)
    assert q.amount == 35_000

    payment = await payments.for_plan(user.id, PlanCode.MONTH, PaymentProvider.MANUAL_CARD, order.id)
    assert (payment.amount, payment.credit_order_id) == (35_000, order.id)
    result = await payments.mark_paid(payment.id)
    assert result.package is not None and result.package.total == 3
    assert order.credit_used
    assert (await payments.plan_quote(PlanCode.MONTH, order.id, user.id)).amount == 64_000  # второй раз нельзя


async def test_set_price_only_before_payment(payments: PaymentService, make_user: Callable[..., Any]) -> None:
    user = await make_user()
    order = await with_cover(payments, user.id)
    await payments.orders.set_price(order.id, 35_000, actor_id=None)
    assert order.price == 35_000
    await payments.confirm_manual(order.id, user.id)
    with pytest.raises(InvalidTransitionError):
        await payments.orders.set_price(order.id, 1, actor_id=None)
