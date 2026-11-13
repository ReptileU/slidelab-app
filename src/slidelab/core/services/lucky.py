"""Бонус-пакет: покупатель платит цену одной презентации из стартового пакета и получает минимум одну.

Правила честности, которые здесь зашиты:
- в минусе остаться нельзя: худший исход — одна презентация по цене стартового пакета (дешевле разового заказа);
- шансы открыты и показываются в приложении рядом с кнопкой покупки — те же числа, по которым идёт розыгрыш;
- не чаще LIMIT раз за WINDOW, чтобы никто не «догонялся».
"""

import random
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from slidelab.core.enums import BoxPrize, PlanCode
from slidelab.core.errors import DomainError
from slidelab.core.models import PackageBox
from slidelab.core.models.base import utcnow


@dataclass(frozen=True, slots=True)
class Prize:
    code: BoxPrize
    count: int  # сколько презентаций
    plan: PlanCode  # по какому пакету считаются срок и статус
    weight: int  # шанс в десятых долях процента (сумма — 1000)

    @property
    def percent(self) -> float:
        return self.weight / 10


PRIZES: tuple[Prize, ...] = (
    Prize(BoxPrize.ONE, 1, PlanCode.WEEK, 880),
    Prize(BoxPrize.TWO, 2, PlanCode.WEEK, 90),
    Prize(BoxPrize.FOUR, 4, PlanCode.MONTH, 25),
    Prize(BoxPrize.VIP, 10, PlanCode.VIP, 5),
)
assert sum(p.weight for p in PRIZES) == 1000

LIMIT = 2
WINDOW = timedelta(days=7)


class LuckyLimitError(DomainError):
    code = "lucky_limit"


class LuckyService:
    def __init__(
        self,
        session: AsyncSession,
        clock: Callable[[], datetime] = utcnow,
        rng: random.Random | None = None,
    ) -> None:
        self.session = session
        self.clock = clock
        self.rng = rng or random.SystemRandom()

    def roll(self) -> Prize:
        return self.rng.choices(PRIZES, weights=[p.weight for p in PRIZES], k=1)[0]

    async def bought_recently(self, user_id: int) -> int:
        since = self.clock() - WINDOW
        stmt = select(func.count(PackageBox.id)).where(PackageBox.user_id == user_id, PackageBox.created_at > since)
        return int(await self.session.scalar(stmt) or 0)

    async def ensure_can_buy(self, user_id: int) -> None:
        if await self.bought_recently(user_id) >= LIMIT:
            raise LuckyLimitError(f"Бонус-пакет можно купить не чаще {LIMIT} раз в неделю")

    async def pending(self, user_id: int) -> PackageBox | None:
        """Купленный, но ещё не открытый бонус-пакет (самый старый)."""
        stmt = (
            select(PackageBox)
            .where(PackageBox.user_id == user_id, PackageBox.opened_at.is_(None))
            .order_by(PackageBox.id)
            .limit(1)
        )
        return await self.session.scalar(stmt)

    async def open(self, user_id: int) -> PackageBox | None:
        box = await self.pending(user_id)
        if box is not None:
            box.opened_at = self.clock()
            await self.session.flush()
        return box
