"""Короткая заявка на бесплатную обложку и её дооформление во всю презентацию."""

from collections.abc import Callable
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from conftest import FakeClock
from slidelab.core import repositories as repo
from slidelab.core.enums import (
    CouponOrigin,
    Deadline,
    Lang,
    OrderStatus,
    SlideTier,
)
from slidelab.core.errors import InvalidTransitionError
from slidelab.core.models import Coupon
from slidelab.core.schemas.order import QuickCoverDraft
from slidelab.core.services.orders import OrderService
from test_orders import draft


def quick() -> QuickCoverDraft:
    return QuickCoverDraft(topic="Экономика Японии", pres_lang=Lang.RU, title_author="Азиз")


async def to_cover(service: OrderService, order_id: int) -> None:
    order = await repo.get_order(service.session, order_id)
    await service.cover_sent(order, None)
    await service.session.flush()


async def test_quick_takes_nothing(session: AsyncSession, clock: FakeClock, make_user: Callable[..., Any]) -> None:
    """Заявка на обложку: ничего не оплачено и не списано; купон и скидка первого заказа за клиентом."""
    user = await make_user()
    session.add(Coupon(user_id=user.id, slides=SlideTier.S20, origin=CouponOrigin.BONUS))
    await session.flush()
    service = OrderService(session, clock)
    order = await service.create(user.id, quick().as_draft(), quick=True)
    assert order.quick and not order.is_paid and order.coupon_id is None and order.package_cost == 0
    assert order.title_author == "Азиз"
    assert len(await repo.open_coupons(session, user.id)) == 1
    assert not await repo.has_orders(session, user.id)  # заявка не съела скидку первого заказа


async def test_complete_after_cover(session: AsyncSession, clock: FakeClock, make_user: Callable[..., Any]) -> None:
    user = await make_user()
    service = OrderService(session, clock)
    order = await service.create(user.id, quick().as_draft(), quick=True)
    with pytest.raises(InvalidTransitionError):  # обложки ещё нет
        await service.complete_quick(order.id, user.id, draft(slides=SlideTier.S20))
    await to_cover(service, order.id)
    full = draft(topic="Экономика Японии", slides=SlideTier.S20, deadline=Deadline.NORMAL)
    done = await service.complete_quick(order.id, user.id, full)
    assert not done.quick and done.slides is SlideTier.S20
    assert done.status is OrderStatus.AWAITING_PAYMENT and done.price > 0
    assert done.title_author == "Азиз"  # с короткой заявки не потерялось
    again = await service.complete_quick(order.id, user.id, full)  # повторное нажатие — без изменений
    assert again.id == done.id and again.status is OrderStatus.AWAITING_PAYMENT


async def test_complete_uses_coupon(session: AsyncSession, clock: FakeClock, make_user: Callable[..., Any]) -> None:
    """Купон списывается только при дооформлении — и заказ сразу уходит в работу."""
    user = await make_user()
    session.add(Coupon(user_id=user.id, slides=SlideTier.S20, origin=CouponOrigin.BONUS))
    await session.flush()
    service = OrderService(session, clock)
    order = await service.create(user.id, quick().as_draft(), quick=True)
    await to_cover(service, order.id)
    done = await service.complete_quick(order.id, user.id, draft(slides=SlideTier.S20))
    assert done.coupon_id is not None and done.is_paid and done.price == 0
    assert done.status is OrderStatus.WORK


async def test_quick_respects_free_cover_limit(
    session: AsyncSession, clock: FakeClock, make_user: Callable[..., Any]
) -> None:
    """Короткие заявки тоже не больше FREE_COVERS_MAX без ответа — защита от спама обложками."""
    from slidelab.core.errors import CoverLimitError
    from slidelab.core.services.orders import FREE_COVERS_MAX

    user = await make_user()
    service = OrderService(session, clock)
    for _ in range(FREE_COVERS_MAX):
        await service.create(user.id, quick().as_draft(), quick=True)
    with pytest.raises(CoverLimitError):
        await service.create(user.id, quick().as_draft(), quick=True)
