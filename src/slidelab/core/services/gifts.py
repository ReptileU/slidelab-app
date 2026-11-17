"""Подарки: купон или несколько презентаций из пакета — по ссылке t.me/<бот>?start=gift_<code>.

Подаренное сразу уходит от дарителя (купон блокируется, презентации списываются из пакета), а получатель
забирает его по ссылке. Пока не забрали — даритель может отменить, и всё вернётся.
Презентации не пропадают: если срок пакета вышел, получатель (или даритель при отмене) получает купоны.
"""

import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from slidelab.core import repositories as repo
from slidelab.core.enums import CouponOrigin, GiftKind, GiftStatus, LedgerReason, SlideTier
from slidelab.core.errors import DomainError, ForbiddenError, NotFoundError
from slidelab.core.models import Coupon, Gift
from slidelab.core.models.base import as_utc, utcnow
from slidelab.core.services.packages import PackageService

PACK_COUPON_SLIDES = SlideTier.S20  # презентация из пакета (до 20 слайдов) → купон этого объёма
MAX_PENDING = 10  # неотданных подарков у одного человека


class GiftError(DomainError):
    pass


@dataclass(frozen=True, slots=True)
class Claimed:
    gift: Gift
    coupons: int  # сколько купонов получил (пакет истёк — презентации пришли купонами)


class GiftService:
    """Сервис не коммитит — транзакцией управляет вызывающий код."""

    def __init__(self, session: AsyncSession, clock: Callable[[], datetime] = utcnow) -> None:
        self.session = session
        self.clock = clock
        self.packages = PackageService(session, clock)

    async def pending(self, user_id: int) -> list[Gift]:
        stmt = (
            select(Gift).where(Gift.from_user_id == user_id, Gift.status == GiftStatus.PENDING).order_by(Gift.id.desc())
        )
        return list((await self.session.scalars(stmt)).all())

    async def _check_limit(self, user_id: int) -> None:
        if len(await self.pending(user_id)) >= MAX_PENDING:
            raise GiftError("Слишком много неотданных подарков — дождитесь, пока их заберут, или отмените лишние")

    def _new(self, user_id: int, kind: GiftKind, **kw: object) -> Gift:
        gift = Gift(code=secrets.token_urlsafe(9), from_user_id=user_id, kind=kind, **kw)
        self.session.add(gift)
        return gift

    async def gift_coupon(self, user_id: int, coupon_id: int) -> Gift:
        await self._check_limit(user_id)
        coupon = await self.session.get(Coupon, coupon_id, with_for_update=True)
        if coupon is None or coupon.user_id != user_id:
            raise NotFoundError("Купон не найден")
        if coupon.used_order_id is not None or coupon.gift_id is not None:
            raise GiftError("Этот купон уже потрачен или подарен")
        gift = self._new(user_id, GiftKind.COUPON, coupon_id=coupon.id, count=1)
        await self.session.flush()
        coupon.gift_id = gift.id  # пока в подарке — им не заплатить
        await self.session.flush()
        return gift

    async def gift_pack(self, user_id: int, count: int) -> Gift:
        await self._check_limit(user_id)
        if count < 1:
            raise GiftError("Сколько презентаций подарить?")
        package = await repo.get_active_package(self.session, user_id, self.clock(), for_update=True)
        if package is None or package.left < count:
            raise GiftError("В пакете не хватает презентаций")
        gift = self._new(
            user_id, GiftKind.PACK, plan_code=package.plan_code, count=count, expires_at=package.expires_at
        )
        package.left -= count
        self.packages._ledger(package, -count, LedgerReason.GIFT)
        await self.session.flush()
        return gift

    async def get_by_code(self, code: str) -> Gift:
        gift = await self.session.scalar(select(Gift).where(Gift.code == code).with_for_update())
        if gift is None:
            raise NotFoundError("Подарок не найден")
        return gift

    async def claim(self, code: str, user_id: int) -> Claimed:
        gift = await self.get_by_code(code)
        if gift.status is GiftStatus.CLAIMED:
            raise GiftError("own" if gift.to_user_id == user_id else "taken")
        if gift.status is GiftStatus.REVOKED:
            raise GiftError("revoked")
        if gift.from_user_id == user_id:
            raise GiftError("self")
        coupons = await self._hand_over(gift, user_id, LedgerReason.GIFT, CouponOrigin.GIFT)
        gift.status = GiftStatus.CLAIMED
        gift.to_user_id = user_id
        gift.done_at = self.clock()
        await self.session.flush()
        return Claimed(gift, coupons)

    async def revoke(self, gift_id: int, user_id: int) -> Gift:
        gift = await self.session.get(Gift, gift_id, with_for_update=True)
        if gift is None:
            raise NotFoundError("Подарок не найден")
        if gift.from_user_id != user_id:
            raise ForbiddenError("Это чужой подарок")
        if gift.status is not GiftStatus.PENDING:
            raise GiftError("Подарок уже забрали")
        await self._hand_over(gift, user_id, LedgerReason.REFUND, CouponOrigin.CANCEL)
        gift.status = GiftStatus.REVOKED
        gift.done_at = self.clock()
        await self.session.flush()
        return gift

    async def _hand_over(self, gift: Gift, to_user: int, reason: LedgerReason, origin: CouponOrigin) -> int:
        """Отдать содержимое подарка: получателю или назад дарителю. Возвращает число выданных купонов."""
        if gift.kind is GiftKind.COUPON:
            coupon = await self.session.get(Coupon, gift.coupon_id, with_for_update=True)
            assert coupon is not None
            coupon.gift_id = None
            if coupon.user_id != to_user:
                coupon.from_user_id, coupon.user_id = coupon.user_id, to_user
            return 0
        assert gift.plan_code is not None
        if gift.expires_at is not None and as_utc(gift.expires_at) > self.clock():
            if to_user == gift.from_user_id:
                # отмена: назад в действующий пакет дарителя
                package = await repo.get_active_package(self.session, to_user, self.clock(), for_update=True)
                if package is not None:
                    package.left += gift.count
                    self.packages._ledger(package, gift.count, reason)
                    return 0
            else:
                await self.packages.activate(
                    to_user, gift.plan_code, reason, count=gift.count, expires_at=gift.expires_at
                )
                return 0
        # срок пакета вышел — презентации не пропадают: купоны
        for _ in range(gift.count):
            self.session.add(
                Coupon(
                    user_id=to_user,
                    slides=PACK_COUPON_SLIDES,
                    origin=origin,
                    from_user_id=gift.from_user_id if to_user != gift.from_user_id else None,
                )
            )
        return gift.count


def link(bot_username: str, gift: Gift) -> str:
    return f"https://t.me/{bot_username}?start=gift_{gift.code}"
