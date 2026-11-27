from collections.abc import Callable
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from conftest import FakeClock
from slidelab.core.enums import CreditReason
from slidelab.core.models import CreditsLedger, User
from slidelab.core.services import credits as cr
from slidelab.core.services.credits import CreditsService, NotEnoughCreditsError


async def test_welcome_once_then_daily_refill(
    session: AsyncSession, make_user: Callable[..., Any], clock: FakeClock
) -> None:
    user: User = await make_user()
    svc = CreditsService(session, now=clock)
    assert await svc.balance(user) == cr.WELCOME
    assert await svc.balance(user) == cr.WELCOME  # подарок один раз

    # потратил почти всё — на следующий день пополнится до потолка
    for _ in range(4):
        await svc.spend(user, "draft")
    assert user.credits == cr.WELCOME - 40
    assert await svc.balance(user) == 10  # в тот же день пополнения нет
    clock.advance(days=1)
    assert await svc.balance(user) == cr.DAILY_CAP

    # выше потолка пополнение не срезает и не добавляет
    await svc.earn(user, cr.PER_ORDER, CreditReason.ORDER)
    clock.advance(days=1)
    assert await svc.balance(user) == cr.DAILY_CAP + cr.PER_ORDER

    total = sum((await session.scalars(select(CreditsLedger.delta).where(CreditsLedger.user_id == user.id))).all())
    assert total == user.credits


async def test_day_boundary_is_tashkent(session: AsyncSession, make_user: Callable[..., Any], clock: FakeClock) -> None:
    user: User = await make_user()
    svc = CreditsService(session, now=clock)
    clock.now = clock.now.replace(hour=18, minute=30)  # 23:30 в Ташкенте
    await svc.balance(user)
    user.credits = 0
    clock.advance(minutes=45)  # 00:15 по Ташкенту, ещё тот же день по UTC
    assert await svc.balance(user) == cr.DAILY_CAP


async def test_not_enough_and_refund(session: AsyncSession, make_user: Callable[..., Any], clock: FakeClock) -> None:
    user: User = await make_user()
    svc = CreditsService(session, now=clock)
    await svc.balance(user)
    user.credits = 3
    with pytest.raises(NotEnoughCreditsError):
        await svc.spend(user, "draft")
    assert user.credits == 3
    await svc.spend(user, "slide_redo")
    await svc.refund(user, "slide_redo")
    assert user.credits == 3
