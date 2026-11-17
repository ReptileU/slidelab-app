from collections.abc import Callable
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from conftest import FakeClock
from slidelab.core import repositories as repo
from slidelab.core.enums import CouponOrigin, Deadline, Design, GiftStatus, Lang, PlanCode, SlideTier
from slidelab.core.models import Coupon
from slidelab.core.models.base import as_utc
from slidelab.core.schemas.order import OrderDraft
from slidelab.core.services.gifts import GiftError, GiftService
from slidelab.core.services.orders import OrderService
from slidelab.core.services.packages import PackageService


def draft() -> OrderDraft:
    return OrderDraft(
        topic="Тема", slides=SlideTier.S20, deadline=Deadline.NORMAL, pres_lang=Lang.RU, design=Design.OURS
    )


@pytest.fixture
def gifts(session: AsyncSession, clock: FakeClock) -> GiftService:
    return GiftService(session, clock)


async def coupon_for(session: AsyncSession, user_id: int) -> Coupon:
    c = Coupon(user_id=user_id, slides=SlideTier.S20, origin=CouponOrigin.CANCEL)
    session.add(c)
    await session.flush()
    return c


async def test_coupon_gift_claimed_by_friend(
    gifts: GiftService, session: AsyncSession, clock: FakeClock, make_user: Callable[..., Any]
) -> None:
    me, friend = await make_user(), await make_user()
    coupon = await coupon_for(session, me.id)
    gift = await gifts.gift_coupon(me.id, coupon.id)
    assert await repo.open_coupons(session, me.id) == []  # пока в подарке — им не заплатить
    with pytest.raises(GiftError, match="self"):
        await gifts.claim(gift.code, me.id)
    got = await gifts.claim(gift.code, friend.id)
    assert got.gift.status is GiftStatus.CLAIMED
    (mine,) = await repo.open_coupons(session, friend.id)
    assert mine.id == coupon.id and mine.from_user_id == me.id
    with pytest.raises(GiftError, match="own"):
        await gifts.claim(gift.code, friend.id)
    # подаренным купоном друг платит за презентацию
    order = await OrderService(session, clock).create(friend.id, draft())
    assert order.is_paid and order.price == 0 and order.coupon_id == coupon.id


async def test_coupon_gift_revoked_returns(
    gifts: GiftService, session: AsyncSession, make_user: Callable[..., Any]
) -> None:
    me, friend = await make_user(), await make_user()
    coupon = await coupon_for(session, me.id)
    gift = await gifts.gift_coupon(me.id, coupon.id)
    await gifts.revoke(gift.id, me.id)
    assert [c.id for c in await repo.open_coupons(session, me.id)] == [coupon.id]
    with pytest.raises(GiftError, match="revoked"):
        await gifts.claim(gift.code, friend.id)


async def test_pack_is_gifted_only_whole_with_senders_plan_and_expiry(
    gifts: GiftService, session: AsyncSession, clock: FakeClock, make_user: Callable[..., Any]
) -> None:
    me, friend = await make_user(), await make_user()
    mine = await PackageService(session, clock).activate(me.id, PlanCode.MONTH)  # 4 презентации
    expires = mine.expires_at
    gift = await gifts.gift_pack(me.id)
    assert gift.count == 4 and mine.left == 0
    assert await repo.get_active_package(session, me.id, clock()) is None  # карта ушла из кошелька целиком
    with pytest.raises(GiftError):
        await gifts.gift_pack(me.id)  # дарить больше нечего
    await gifts.claim(gift.code, friend.id)
    theirs = await repo.get_active_package(session, friend.id, clock())
    assert theirs is not None and theirs.left == 4
    assert as_utc(theirs.expires_at) == as_utc(expires)
    assert theirs.plan_code is PlanCode.MONTH


async def test_pack_gift_after_expiry_becomes_coupons(
    gifts: GiftService, session: AsyncSession, clock: FakeClock, make_user: Callable[..., Any]
) -> None:
    me, friend = await make_user(), await make_user()
    await PackageService(session, clock).activate(me.id, PlanCode.WEEK)  # 2 презентации
    gift = await gifts.gift_pack(me.id)
    clock.advance(days=60)  # друг открыл ссылку, когда срок пакета уже вышел
    got = await gifts.claim(gift.code, friend.id)
    assert got.coupons == 2 and len(await repo.open_coupons(session, friend.id)) == 2


async def test_pack_gift_revoke_gives_the_package_back(
    gifts: GiftService, session: AsyncSession, clock: FakeClock, make_user: Callable[..., Any]
) -> None:
    me, other = await make_user(), await make_user()
    await PackageService(session, clock).activate(me.id, PlanCode.MONTH)
    gift = await gifts.gift_pack(me.id)
    with pytest.raises(Exception):  # noqa: B017 — чужой подарок не отменить
        await gifts.revoke(gift.id, other.id)
    await gifts.revoke(gift.id, me.id)
    back = await repo.get_active_package(session, me.id, clock())
    assert back is not None and back.left == 4 and back.plan_code is PlanCode.MONTH


async def test_bought_gift_starts_its_term_when_claimed(
    session: AsyncSession, clock: FakeClock, make_user: Callable[..., Any]
) -> None:
    from slidelab.core.enums import PaymentProvider
    from slidelab.core.services.payments import PaymentService

    me, friend = await make_user(), await make_user()
    payments = PaymentService(session, clock)
    payment = await payments.for_plan(me.id, PlanCode.MONTH, PaymentProvider.STARS, as_gift=True)
    paid = await payments.mark_paid(payment.id, external_id="x1")
    assert paid.gift is not None and paid.package is None
    assert await repo.get_active_package(session, me.id, clock()) is None  # покупателю пакет не включился
    clock.advance(days=20)
    await GiftService(session, clock).claim(paid.gift.code, friend.id)
    theirs = await repo.get_active_package(session, friend.id, clock())
    assert theirs is not None and theirs.left == 4
    assert (theirs.expires_at.replace(tzinfo=None) - clock().replace(tzinfo=None)).days >= 29  # срок — с получения
