"""Приглашения друзей: кто засчитывается и когда начисляются баллы."""

from collections.abc import Callable
from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from conftest import FakeClock
from slidelab.core import repositories as repo
from slidelab.core.enums import CouponOrigin, PaymentProvider, SlideTier
from slidelab.core.models import Coupon, User
from slidelab.core.services import points, referrals
from slidelab.core.services.payments import PaymentService
from slidelab.core.services.referrals import ReferralService, code_for, parse_code
from test_orders import draft


@pytest.fixture
def payments(session: AsyncSession, clock: FakeClock) -> PaymentService:
    return PaymentService(session, clock)


async def pay_order(payments: PaymentService, user_id: int) -> Any:
    order = await payments.orders.create(user_id, draft())
    payment = await payments.for_order(order, PaymentProvider.MANUAL_CARD)
    return await payments.mark_paid(payment.id)


async def invite(session: AsyncSession, clock: FakeClock, make_user: Callable[..., Any], inviter: User) -> User:
    friend = await make_user(created_at=clock.now)
    assert await ReferralService(session, clock).attach(friend, code_for(inviter.id)) is not None
    return friend


def test_code_roundtrip() -> None:
    for n in (1, 35, 36, 1000, 987654):
        assert parse_code(code_for(n)) == n
    assert parse_code("") is None and parse_code("!!") is None


async def test_who_counts(
    session: AsyncSession, clock: FakeClock, make_user: Callable[..., Any], payments: PaymentService
) -> None:
    service = ReferralService(session, clock)
    inviter = await make_user(created_at=clock.now - timedelta(days=30))
    assert await service.attach(inviter, code_for(inviter.id)) is None  # себя нельзя
    old = await make_user(created_at=clock.now - timedelta(days=2))
    assert await service.attach(old, code_for(inviter.id)) is None  # давно пользуется ботом
    buyer = await make_user(created_at=clock.now)
    await pay_order(payments, buyer.id)
    assert await service.attach(buyer, code_for(inviter.id)) is None  # уже покупал
    assert await service.attach(await make_user(created_at=clock.now), "zzzzzz") is None  # нет такого
    friend = await make_user(created_at=clock.now)
    assert await service.attach(friend, code_for(inviter.id)) is not None
    other = await make_user()
    assert await service.attach(friend, code_for(other.id)) is None  # пригласивший один
    assert await service.pending_for(friend)


async def test_points_when_friend_pays(
    session: AsyncSession, clock: FakeClock, make_user: Callable[..., Any], payments: PaymentService
) -> None:
    inviter = await make_user()
    friend = await invite(session, clock, make_user, inviter)
    assert inviter.points == 0  # за регистрацию — ничего

    result = await pay_order(payments, friend.id)
    assert result.points == points.PER_PRESENTATION + referrals.FRIEND_BONUS  # другу — сразу на бронзовый кейс
    assert friend.points == 100
    assert result.referral is not None and result.referral.inviter.id == inviter.id
    assert inviter.points == referrals.INVITER_POINTS

    again = await pay_order(payments, friend.id)  # вторая покупка — только обычные баллы
    assert again.referral is None and again.points == points.PER_PRESENTATION
    assert inviter.points == referrals.INVITER_POINTS
    assert not await ReferralService(session, clock).pending_for(friend)


async def test_coupon_order_does_not_count(
    session: AsyncSession, clock: FakeClock, make_user: Callable[..., Any], payments: PaymentService
) -> None:
    inviter = await make_user()
    friend = await invite(session, clock, make_user, inviter)
    session.add(Coupon(user_id=friend.id, slides=SlideTier.S20, origin=CouponOrigin.BONUS))
    await session.flush()
    order = await payments.orders.create(friend.id, draft())
    if not order.is_paid:
        payment = await payments.for_order(order, PaymentProvider.MANUAL_CARD)
        assert (await payments.mark_paid(payment.id)).referral is None
    assert inviter.points == 0


async def test_milestone_bonus(
    session: AsyncSession, clock: FakeClock, make_user: Callable[..., Any], payments: PaymentService
) -> None:
    inviter = await make_user()
    rewards = []
    for _ in range(3):
        friend = await invite(session, clock, make_user, inviter)
        rewards.append((await pay_order(payments, friend.id)).referral)
    assert [r.milestone for r in rewards] == [None, None, 3]
    assert [r.coupon for r in rewards] == [False, False, True]  # третий друг — бесплатная презентация
    assert inviter.points == 3 * referrals.INVITER_POINTS
    assert len(await repo.open_coupons(session, inviter.id)) == 1
    summary = await ReferralService(session, clock).summary(inviter)
    assert summary.paid == 3 and summary.earned == inviter.points and len(summary.friends) == 3


async def test_welcome_case_once(session: AsyncSession, clock: FakeClock, make_user: Callable[..., Any]) -> None:
    """Приветственный кейс: только у пришедшего по ссылке, один раз; бесплатная презентация — купон до 15 слайдов."""
    import random

    from slidelab.core.enums import BoxPrize
    from slidelab.core.services.referrals import NoWelcomeError

    service = ReferralService(session, clock)
    stranger = await make_user(created_at=clock.now)
    assert not await service.welcome_available(stranger)
    with pytest.raises(NoWelcomeError):
        await service.open_welcome(stranger)

    inviter = await make_user()
    friend = await invite(session, clock, make_user, inviter)
    assert await service.welcome_available(friend)

    class FreeOne(random.Random):
        def choices(self, population: Any, weights: Any = None, *, cum_weights: Any = None, k: int = 1) -> list[Any]:
            return [next(p for p in population if p.code is BoxPrize.ONE)]

    box = await service.open_welcome(friend, FreeOne())
    assert box.prize is BoxPrize.ONE
    coupons = await repo.open_coupons(session, friend.id)
    assert len(coupons) == 1 and coupons[0].slides is SlideTier.S10
    assert not await service.welcome_available(friend)
    with pytest.raises(NoWelcomeError):
        await service.open_welcome(friend)


def test_welcome_odds() -> None:
    assert sum(p.weight for p in points.WELCOME.prizes) == 1000
    assert points.WELCOME.price == 0 and "welcome" not in points.BOXES
