from collections.abc import Callable
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from conftest import FakeClock
from slidelab.core.enums import (
    Deadline,
    Design,
    Lang,
    OrderStatus,
    PaidFrom,
    PlanCode,
    SlideTier,
    Stage,
)
from slidelab.core.errors import ForbiddenError, InvalidTransitionError, PaymentRequiredError
from slidelab.core.models import Order, OrderEvent, UserPackage
from slidelab.core.models.base import as_utc
from slidelab.core.schemas.order import OrderDraft
from slidelab.core.services.orders import OrderService
from slidelab.core.services.packages import PackageService

S = OrderStatus


def draft(**kwargs: Any) -> OrderDraft:
    data: dict[str, Any] = {
        "topic": "Экономика Японии после 1990 года",
        "slides": SlideTier.S20,
        "deadline": Deadline.NORMAL,
        "pres_lang": Lang.RU,
        "design": Design.OURS,
    }
    data.update(kwargs)
    return OrderDraft(**data)


@pytest.fixture
def orders(session: AsyncSession, clock: FakeClock) -> OrderService:
    return OrderService(session, clock)


@pytest.fixture
def packages(session: AsyncSession, clock: FakeClock) -> PackageService:
    return PackageService(session, clock)


async def to_cover(orders: OrderService, order: Order) -> None:
    await orders.cover_sent(order, actor_id=None)


async def to_work(orders: OrderService, order: Order) -> None:
    """Обложка → оплата → одобрение — заказ в работе."""
    await to_cover(orders, order)
    await orders.mark_paid(order, actor_id=None)


# --- создание ---------------------------------------------------------------


async def test_first_order_gets_discount_only_once(orders: OrderService, make_user: Callable[..., Any]) -> None:
    user = await make_user()
    first = await orders.create(user.id, draft(slides=SlideTier.S10))
    second = await orders.create(user.id, draft(slides=SlideTier.S10))
    assert (first.price, second.price) == (9_900, 19_000)
    assert (first.status, first.stage, first.is_paid) == (S.NEW, Stage.COVER_TODO, False)


async def test_cancelled_order_does_not_count_as_previous(orders: OrderService, make_user: Callable[..., Any]) -> None:
    user = await make_user()
    first = await orders.create(user.id, draft(slides=SlideTier.S10))
    await orders.transition(first.id, S.CANCELLED, actor_id=None)
    again = await orders.create(user.id, draft(slides=SlideTier.S10))
    assert again.price == 9_900


async def test_idempotency_key_returns_same_order(
    orders: OrderService, session: AsyncSession, make_user: Callable[..., Any]
) -> None:
    user = await make_user()
    a = await orders.create(user.id, draft(), idempotency_key="key-12345678")
    b = await orders.create(user.id, draft(), idempotency_key="key-12345678")
    assert a.id == b.id
    assert len((await session.scalars(select(Order))).all()) == 1


async def test_creation_is_logged(orders: OrderService, session: AsyncSession, make_user: Callable[..., Any]) -> None:
    user = await make_user()
    order = await orders.create(user.id, draft())
    events = (await session.scalars(select(OrderEvent).where(OrderEvent.order_id == order.id))).all()
    assert [(e.from_status, e.to_status, e.actor_id) for e in events] == [(None, S.NEW, user.id)]


def test_template_url_only_for_own_design() -> None:
    with pytest.raises(ValueError, match="template_url"):
        draft(design=Design.OURS, template_url="https://canva.com/x")
    assert draft(design=Design.OWN, template_url="https://canva.com/x").template_url


# --- обложка и оплата ---------------------------------------------------------


async def test_cannot_skip_cover(orders: OrderService, make_user: Callable[..., Any]) -> None:
    user = await make_user()
    order = await orders.create(user.id, draft())
    with pytest.raises(InvalidTransitionError):
        await orders.transition(order.id, S.WORK, actor_id=None)


async def test_cover_approved_then_paid(orders: OrderService, make_user: Callable[..., Any]) -> None:
    user = await make_user()
    order = await orders.create(user.id, draft())
    await to_cover(orders, order)
    assert (order.status, order.stage) == (S.COVER, Stage.COVER_SENT)

    await orders.approve_cover(order.id, user.id)
    assert (order.status, order.stage) == (S.AWAITING_PAYMENT, Stage.COVER_OK)

    started = await orders.mark_paid(order, actor_id=None)
    assert started and (order.status, order.stage) == (S.WORK, Stage.DECK_TODO)


async def test_paid_early_starts_right_after_cover_approval(
    orders: OrderService, make_user: Callable[..., Any]
) -> None:
    user = await make_user()
    order = await orders.create(user.id, draft())
    assert not await orders.mark_paid(order, actor_id=None)  # обложки ещё нет — ждём
    assert (order.status, order.is_paid) == (S.NEW, True)

    await to_cover(orders, order)
    await orders.approve_cover(order.id, user.id)
    assert (order.status, order.stage) == (S.WORK, Stage.DECK_TODO)


async def test_work_requires_payment(orders: OrderService, make_user: Callable[..., Any]) -> None:
    user = await make_user()
    order = await orders.create(user.id, draft())
    await to_cover(orders, order)
    with pytest.raises(PaymentRequiredError):
        await orders.transition(order.id, S.WORK, actor_id=None)


async def test_cover_change_restarts_cover(orders: OrderService, make_user: Callable[..., Any]) -> None:
    user = await make_user()
    order = await orders.create(user.id, draft())
    await to_cover(orders, order)
    await orders.approve_cover(order.id, user.id)
    await orders.request_cover_change(order.id, user.id)
    assert (order.status, order.stage) == (S.COVER, Stage.COVER_TODO)

    await orders.mark_paid(order, actor_id=None)  # оплатил, пока переделываем — сразу в работу
    with pytest.raises(InvalidTransitionError):
        await orders.request_cover_change(order.id, user.id)


async def test_cancelled_is_final(orders: OrderService, make_user: Callable[..., Any]) -> None:
    user = await make_user()
    order = await orders.create(user.id, draft())
    await orders.transition(order.id, S.CANCELLED, actor_id=None)
    with pytest.raises(InvalidTransitionError):
        await orders.transition(order.id, S.COVER, actor_id=None)


async def test_deliver(orders: OrderService, make_user: Callable[..., Any]) -> None:
    user = await make_user()
    order = await orders.create(user.id, draft())
    await to_work(orders, order)
    await orders.deliver(order, None, deliver_dir="5/sent_deck", files=["a.pptx"], links={"canva": "https://c"})
    assert (order.status, order.stage, order.deliver_files) == (S.DONE, Stage.DONE, ["a.pptx"])


# --- пакеты -----------------------------------------------------------------


async def test_package_debited_at_order_and_refunded_on_cancel(
    orders: OrderService, packages: PackageService, make_user: Callable[..., Any]
) -> None:
    user = await make_user()
    pkg = await packages.activate(user.id, PlanCode.MONTH)
    order = await orders.create(user.id, draft())
    assert (order.paid_from, order.price, order.package_cost, order.is_paid) == (PaidFrom.PACKAGE, 0, 1, True)
    assert pkg.left == 3

    await orders.transition(order.id, S.CANCELLED, actor_id=None)
    assert pkg.left == 4


async def test_package_order_with_extras_is_not_paid_yet(
    orders: OrderService, packages: PackageService, make_user: Callable[..., Any]
) -> None:
    user = await make_user()
    await packages.activate(user.id, PlanCode.MONTH)
    order = await orders.create(user.id, draft(extra_text=True))
    assert (order.paid_from, order.price, order.is_paid) == (PaidFrom.PACKAGE, 5_000, False)


async def test_30_slides_take_two(
    orders: OrderService, packages: PackageService, make_user: Callable[..., Any]
) -> None:
    user = await make_user()
    pkg = await packages.activate(user.id, PlanCode.WEEK)
    await orders.create(user.id, draft(slides=SlideTier.S30))
    assert pkg.left == 0
    next_order = await orders.create(user.id, draft())
    assert next_order.paid_from is PaidFrom.CASH  # пакет кончился — обычная цена


async def test_packages_stack(packages: PackageService, clock: FakeClock, make_user: Callable[..., Any]) -> None:
    user = await make_user()
    old = await packages.activate(user.id, PlanCode.MONTH)
    clock.advance(days=10)
    new = await packages.activate(user.id, PlanCode.WEEK)
    assert (old.left, new.left, new.total) == (0, 6, 6)
    # срок — самый дальний: месяц от прошлой покупки длиннее, чем 14 дней от сегодня
    assert as_utc(new.expires_at) == as_utc(old.expires_at)


async def test_vip_stays_vip(packages: PackageService, make_user: Callable[..., Any]) -> None:
    user = await make_user()
    await packages.activate(user.id, PlanCode.VIP)
    pkg = await packages.activate(user.id, PlanCode.WEEK)
    assert (pkg.plan_code, pkg.left) == (PlanCode.VIP, 12)


async def test_expired_package_is_not_used(
    orders: OrderService, packages: PackageService, clock: FakeClock, make_user: Callable[..., Any]
) -> None:
    user = await make_user()
    await packages.activate(user.id, PlanCode.WEEK)
    clock.advance(days=15)
    assert await packages.balance(user.id) is None
    order = await orders.create(user.id, draft())
    assert order.paid_from is PaidFrom.CASH


async def test_refund_goes_to_new_package_after_carry_over(
    orders: OrderService, packages: PackageService, session: AsyncSession, make_user: Callable[..., Any]
) -> None:
    user = await make_user()
    await packages.activate(user.id, PlanCode.WEEK)
    order = await orders.create(user.id, draft())
    new = await packages.activate(user.id, PlanCode.MONTH)  # перенесли 1
    assert new.left == 5
    await orders.transition(order.id, S.CANCELLED, actor_id=None)
    assert new.left == 6
    assert sum((await session.scalars(select(UserPackage.left))).all()) == 6


async def test_credit_offer_only_for_paid_cash_orders(
    orders: OrderService, packages: PackageService, clock: FakeClock, make_user: Callable[..., Any]
) -> None:
    user = await make_user()
    order = await orders.create(user.id, draft())
    assert not packages.offer_credit(order, days=3)  # не оплачен
    await to_work(orders, order)
    await orders.deliver(order, None)
    assert packages.offer_credit(order, days=3)
    credit = await packages.credit_for(order.id, PlanCode.MONTH)
    assert credit is not None and (credit.amount, credit.units) == (29_000, 1)
    clock.advance(days=4)
    assert await packages.credit_for(order.id, PlanCode.MONTH) is None


# --- правки -----------------------------------------------------------------


async def test_two_free_revisions_then_paid(orders: OrderService, make_user: Callable[..., Any]) -> None:
    user = await make_user()
    order = await orders.create(user.id, draft())
    await to_work(orders, order)
    await orders.deliver(order, None)

    flags = []
    for _ in range(3):
        rev = await orders.request_revision(order.id, user.id, "слайд 3 — заменить график")
        assert order.stage is Stage.EDIT_TODO
        flags.append(rev.is_paid)
        await orders.deliver(order, None)
    assert flags == [False, False, True]
    assert order.revisions_left == 0


async def test_more_edits_while_revising_do_not_spend_attempts(
    orders: OrderService, make_user: Callable[..., Any]
) -> None:
    user = await make_user()
    order = await orders.create(user.id, draft())
    await to_work(orders, order)
    await orders.deliver(order, None)
    await orders.request_revision(order.id, user.id, "слайд 3")
    await orders.request_revision(order.id, user.id, "и ещё слайд 5")
    assert order.revisions_left == 1


async def test_revision_only_for_owner_and_done(orders: OrderService, make_user: Callable[..., Any]) -> None:
    owner, stranger = await make_user(), await make_user()
    order = await orders.create(owner.id, draft())
    with pytest.raises(InvalidTransitionError):
        await orders.request_revision(order.id, owner.id, "правка")
    with pytest.raises(ForbiddenError):
        await orders.request_revision(order.id, stranger.id, "правка")


async def test_stage_change_resets_watch_alert(orders: OrderService, make_user: Callable[..., Any]) -> None:
    user = await make_user()
    order = await orders.create(user.id, draft())
    order.alerted = "cover_todo|late"
    await to_cover(orders, order)
    assert order.alerted is None
