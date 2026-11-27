"""Кредиты конструктора: ими платят за действия ИИ. Ручная работа в конструкторе — бесплатно.

Правила (цифры — здесь, в одном месте):
- новичок при первом входе получает WELCOME;
- раз в сутки баланс пополняется до DAILY_CAP, если он ниже (не копится: расходы предсказуемы);
- за оплаченную деньгами презентацию — PER_ORDER, за друга — PER_REFERRAL;
- списание — до вызова ИИ; если ИИ не справился, кредиты возвращаются (refund).
"""

from collections.abc import Callable
from datetime import date, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from slidelab.core.enums import CreditReason
from slidelab.core.errors import DomainError
from slidelab.core.models import CreditsLedger, User
from slidelab.core.models.base import as_utc, utcnow

WELCOME = 50
DAILY_CAP = 20
PER_ORDER = 100
PER_REFERRAL = 30

# Стоимость действий ИИ
COSTS: dict[str, int] = {
    "draft": 10,  # черновик всей презентации
    "slide_redo": 2,  # переделать один слайд целиком
    "suggest": 1,  # 3 варианта для слайда
    "images": 1,  # подобрать картинки по теме
    "image_gen": 4,  # сгенерировать картинку
}

# Сутки считаем по Ташкенту: пополнение — после полуночи у клиента, а не по UTC
TZ_OFFSET = timedelta(hours=5)


class NotEnoughCreditsError(DomainError):
    code = "not_enough_credits"
    client_key = "not_enough_credits"


def _day(moment: datetime) -> date:
    return (as_utc(moment) + TZ_OFFSET).date()


class CreditsService:
    def __init__(self, session: AsyncSession, now: Callable[[], datetime] = utcnow) -> None:
        self.session = session
        self.now = now

    def _move(self, user: User, delta: int, reason: CreditReason, action: str | None, deck_id: int | None) -> None:
        user.credits += delta
        self.session.add(CreditsLedger(user_id=user.id, delta=delta, reason=reason, action=action, deck_id=deck_id))

    def _refill(self, user: User) -> None:
        now = self.now()
        if user.credits_refill_at is None:
            self._move(user, WELCOME, CreditReason.WELCOME, None, None)
            user.credits_refill_at = now
            return
        if _day(user.credits_refill_at) == _day(now):
            return
        user.credits_refill_at = now
        if user.credits < DAILY_CAP:
            self._move(user, DAILY_CAP - user.credits, CreditReason.DAILY, None, None)

    async def balance(self, user: User) -> int:
        """Баланс с учётом стартового подарка и дневного пополнения. Коммитит вызывающий."""
        self._refill(user)
        await self.session.flush()
        return user.credits

    async def spend(self, user: User, action: str, deck_id: int | None = None) -> int:
        cost = COSTS.get(action)
        if cost is None:
            raise DomainError(f"Нет действия «{action}»")
        self._refill(user)
        if user.credits < cost:
            raise NotEnoughCreditsError(f"Нужно {cost} кредитов, есть {user.credits}")
        self._move(user, -cost, CreditReason.SPEND, action, deck_id)
        await self.session.flush()
        return cost

    async def refund(self, user: User, action: str, deck_id: int | None = None) -> None:
        self._move(user, COSTS[action], CreditReason.REFUND, action, deck_id)
        await self.session.flush()

    async def earn(self, user: User, amount: int, reason: CreditReason) -> None:
        if amount <= 0:
            return
        self._refill(user)  # стартовый подарок не теряется, если первая встреча с кредитами — начисление
        self._move(user, amount, reason, None, None)
        await self.session.flush()
