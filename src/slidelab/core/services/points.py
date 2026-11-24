"""Баллы за покупки и кейсы за баллы.

Правила (цифры — здесь, в одном месте):
- баллы дают только за деньги: оплаченный заказ, пакет (за каждую презентацию в нём), бонус-пакет, пакет в подарок;
  за заказы из пакета, по купону или из пакета за баллы — ничего, иначе получился бы бесконечный круг;
- баллы сгорают, если EXPIRE_DAYS не было ни одной покупки за деньги (каждая покупка продлевает срок);
- три кейса за баллы: чем больше накопил, тем выгоднее каждый балл. Пустых исходов нет;
- денежный бонус-пакет снят с продажи — шанс на 10 презентаций (VIP) теперь в золотом кейсе.
"""

import random
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from slidelab.core.enums import BoxPrize, CouponOrigin, LedgerReason, PlanCode, PointsReason, SlideTier
from slidelab.core.errors import DomainError
from slidelab.core.models import Coupon, PackageBox, PointsLedger, User
from slidelab.core.models.base import as_utc, utcnow

PER_PRESENTATION = 50
EXPIRE_DAYS = 180


@dataclass(frozen=True, slots=True)
class PointsPrize:
    code: BoxPrize
    value: int  # презентаций; для DISCOUNT — процент скидки; для POINTS — сколько баллов вернётся
    weight: int  # шанс в десятых долях процента (сумма — 1000)

    @property
    def percent(self) -> float:
        return self.weight / 10


@dataclass(frozen=True, slots=True)
class PointsBox:
    key: str
    price: int
    prizes: tuple[PointsPrize, ...]


# Призы: ONE — 1 купон, COUPONS — несколько купонов (без срока), TWO — пакет «Неделя», FOUR — пакет «Месяц»,
# DISCOUNT — скидка % на следующий заказ, POINTS — часть баллов обратно.
# Скидка — самый частый приз: купон — это целая презентация, а со скидкой клиент всё равно платит.
# В пересчёте на 100 баллов (скидка N% ≈ N/100 презентации): малый ≈ 0,44, средний ≈ 0,47, большой ≈ 0,58 —
# копить выгоднее, чем открывать сразу.
# пакет, который выпадает в кейсе
PRIZE_PLAN = {BoxPrize.TWO: PlanCode.WEEK, BoxPrize.FOUR: PlanCode.MONTH, BoxPrize.VIP: PlanCode.VIP}

DISCOUNT_MAX = 70  # потолок сложенных карт скидки, %

BOXES: dict[str, PointsBox] = {
    "small": PointsBox(
        "small",
        100,
        (
            PointsPrize(BoxPrize.DISCOUNT, 20, 450),
            PointsPrize(BoxPrize.DISCOUNT, 30, 250),
            PointsPrize(BoxPrize.ONE, 1, 150),
            PointsPrize(BoxPrize.POINTS, 60, 100),
            PointsPrize(BoxPrize.TWO, 2, 50),
        ),
    ),
    "medium": PointsBox(
        "medium",
        250,
        (
            PointsPrize(BoxPrize.DISCOUNT, 30, 300),
            PointsPrize(BoxPrize.DISCOUNT, 50, 250),
            PointsPrize(BoxPrize.COUPONS, 2, 250),
            PointsPrize(BoxPrize.TWO, 2, 150),
            PointsPrize(BoxPrize.COUPONS, 3, 50),
        ),
    ),
    "large": PointsBox(
        "large",
        500,
        (
            PointsPrize(BoxPrize.DISCOUNT, 50, 350),
            PointsPrize(BoxPrize.COUPONS, 3, 200),
            PointsPrize(BoxPrize.FOUR, 4, 250),
            PointsPrize(BoxPrize.COUPONS, 5, 140),
            PointsPrize(BoxPrize.COUPONS, 6, 45),
            PointsPrize(BoxPrize.VIP, 10, 15),  # пакет VIP на 10 презентаций — 1,5%
        ),
    ),
}
for _box in BOXES.values():
    assert sum(p.weight for p in _box.prizes) == 1000, _box.key


class NotEnoughPointsError(DomainError):
    code = "not_enough_points"


class PointsService:
    def __init__(
        self, session: AsyncSession, clock: Callable[[], datetime] = utcnow, rng: random.Random | None = None
    ) -> None:
        self.session = session
        self.clock = clock
        self.rng = rng or random.SystemRandom()

    def _expire(self, user: User) -> None:
        """Сгоревшие баллы списываются при первом обращении после срока."""
        if user.points and user.points_expire_at and as_utc(user.points_expire_at) <= as_utc(self.clock()):
            self.session.add(PointsLedger(user_id=user.id, delta=-user.points, reason=PointsReason.EXPIRED))
            user.points = 0
            user.points_expire_at = None

    async def balance(self, user: User) -> int:
        self._expire(user)
        return user.points

    async def earn(
        self,
        user: User,
        presentations: int,
        reason: PointsReason,
        *,
        order_id: int | None = None,
        payment_id: int | None = None,
    ) -> int:
        """Начислить за покупку деньгами: PER_PRESENTATION за каждую презентацию, срок — заново."""
        return await self.grant(
            user, PER_PRESENTATION * presentations, reason, order_id=order_id, payment_id=payment_id
        )

    async def grant(
        self,
        user: User,
        amount: int,
        reason: PointsReason,
        *,
        order_id: int | None = None,
        payment_id: int | None = None,
    ) -> int:
        """Начислить сколько-то баллов (приглашения, бонусы); срок всех баллов — заново."""
        self._expire(user)
        if amount <= 0:
            return 0
        user.points += amount
        user.points_expire_at = self.clock() + timedelta(days=EXPIRE_DAYS)
        self.session.add(
            PointsLedger(user_id=user.id, delta=amount, reason=reason, order_id=order_id, payment_id=payment_id)
        )
        return amount

    def roll(self, box: PointsBox) -> PointsPrize:
        return self.rng.choices(box.prizes, weights=[p.weight for p in box.prizes], k=1)[0]

    async def open_box(self, user: User, key: str) -> PackageBox:
        """Купить пакет за баллы и сразу разыграть приз (коробка сразу открыта — показываем анимацию)."""
        from slidelab.core.services.packages import PackageService  # без цикла импортов

        box = BOXES.get(key)
        if box is None:
            raise DomainError(f"Нет пакета «{key}»")
        self._expire(user)
        if user.points < box.price:
            raise NotEnoughPointsError(f"Нужно {box.price} баллов, у клиента {user.points}")
        user.points -= box.price
        self.session.add(PointsLedger(user_id=user.id, delta=-box.price, reason=PointsReason.BOX))
        prize = self.roll(box)
        record = PackageBox(
            user_id=user.id,
            prize=prize.code,
            count=prize.value,
            created_at=self.clock(),
            opened_at=self.clock(),
            for_points=True,
        )
        if prize.code in (BoxPrize.ONE, BoxPrize.COUPONS):
            coupons = [
                Coupon(user_id=user.id, slides=SlideTier.S20, origin=CouponOrigin.BONUS) for _ in range(prize.value)
            ]
            self.session.add_all(coupons)
            await self.session.flush()
            record.coupon_id = coupons[0].id
        elif prize.code in PRIZE_PLAN:
            plan = PRIZE_PLAN[prize.code]
            package = await PackageService(self.session, self.clock).activate(user.id, plan, LedgerReason.BONUS)
            record.user_package_id = package.id
        elif prize.code is BoxPrize.DISCOUNT:
            # карты скидки складываются (30% + 20% = 50%), но не больше DISCOUNT_MAX
            user.discount_pct = min((user.discount_pct or 0) + prize.value, DISCOUNT_MAX)
        elif prize.code is BoxPrize.POINTS:
            user.points += prize.value
            self.session.add(PointsLedger(user_id=user.id, delta=prize.value, reason=PointsReason.BOX_PRIZE))
        self.session.add(record)
        await self.session.flush()
        return record
