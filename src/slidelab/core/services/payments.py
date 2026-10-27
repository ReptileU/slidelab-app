"""Оплата заказов и пакетов.

Звёзды Telegram подтверждаются автоматически (successful_payment), перевод на карту — менеджером.
Заказ можно оплатить сразу после оформления: работа начнётся, как только клиент одобрит обложку.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from slidelab.core import repositories as repo
from slidelab.core.enums import PaymentProvider, PaymentStatus, PlanCode
from slidelab.core.errors import InvalidTransitionError
from slidelab.core.models import Order, Payment, UserPackage
from slidelab.core.models.base import utcnow
from slidelab.core.services.orders import PAYABLE, OrderService
from slidelab.core.services.packages import Credit
from slidelab.core.services.pricing import to_stars

STARS = "XTR"
UZS = "UZS"


@dataclass(frozen=True, slots=True)
class PaidResult:
    payment: Payment
    order: Order | None = None
    package: UserPackage | None = None
    already_paid: bool = False
    started: bool = False  # заказ сразу ушёл в работу (обложка уже была у клиента)
    credit: Credit | None = None


@dataclass(frozen=True, slots=True)
class PlanQuote:
    amount: int  # к оплате, сум
    credit: Credit | None


class PaymentService:
    def __init__(self, session: AsyncSession, clock: Callable[[], datetime] = utcnow) -> None:
        self.session = session
        self.orders = OrderService(session, clock)
        self.packages = self.orders.packages

    async def stars_for(self, amount_uzs: int) -> int:
        rate = (await repo.get_price_rule_row(self.session)).uzs_per_star
        return to_stars(amount_uzs, rate)

    async def plan_quote(
        self, plan_code: PlanCode, credit_order_id: int | None = None, user_id: int | None = None
    ) -> PlanQuote:
        plan = await repo.get_plan(self.session, plan_code)
        credit = await self.packages.credit_for(credit_order_id, plan_code) if credit_order_id else None
        if credit is not None and user_id is not None:
            order = await repo.get_order(self.session, credit.order_id)
            if order.user_id != user_id:  # чужой заказ не засчитываем
                credit = None
        return PlanQuote(amount=plan.price - (credit.amount if credit else 0), credit=credit)

    async def for_order(self, order: Order, provider: PaymentProvider) -> Payment:
        if order.is_paid:
            raise InvalidTransitionError(f"Заказ #{order.id} уже оплачен")
        if order.status not in PAYABLE or order.price <= 0:
            raise InvalidTransitionError(f"Заказ #{order.id} сейчас не ждёт оплату")
        amount, currency = await self._amount(order.price, provider)
        return await self._create(order.user_id, provider, amount, currency, order_id=order.id)

    async def for_plan(
        self, user_id: int, plan_code: PlanCode, provider: PaymentProvider, credit_order_id: int | None = None
    ) -> Payment:
        q = await self.plan_quote(plan_code, credit_order_id, user_id)
        amount, currency = await self._amount(q.amount, provider)
        return await self._create(
            user_id,
            provider,
            amount,
            currency,
            plan_code=plan_code,
            credit_order_id=q.credit.order_id if q.credit else None,
        )

    async def check_pending(self, payment_id: int, amount: int, currency: str) -> Payment:
        """Проверка перед списанием звёзд (pre_checkout_query)."""
        payment = await repo.get_payment(self.session, payment_id)
        if payment.status is not PaymentStatus.PENDING:
            raise InvalidTransitionError("Счёт уже оплачен или отменён")
        if (payment.amount, payment.currency) != (amount, currency):
            raise InvalidTransitionError("Сумма счёта изменилась — запросите новый")
        if payment.order_id is not None:
            order = await repo.get_order(self.session, payment.order_id)
            if order.is_paid or order.status not in PAYABLE:
                raise InvalidTransitionError("Заказ уже оплачен или отменён")
        return payment

    async def mark_paid(
        self, payment_id: int, external_id: str | None = None, raw: dict[str, Any] | None = None
    ) -> PaidResult:
        payment = await repo.get_payment(self.session, payment_id, for_update=True)
        if payment.status is PaymentStatus.PAID:
            return PaidResult(payment=payment, already_paid=True)  # Telegram может прислать повтор
        if payment.status is not PaymentStatus.PENDING:
            raise InvalidTransitionError(f"Платёж {payment.id} уже {payment.status}")

        payment.status = PaymentStatus.PAID
        payment.external_id = external_id
        payment.raw = raw
        await self.session.flush()

        package = None
        credit = None
        if payment.plan_code is not None:
            if payment.credit_order_id is not None:
                credit = await self.packages.credit_for(payment.credit_order_id, payment.plan_code)
            package = await self.packages.activate(payment.user_id, payment.plan_code, credit=credit)
            payment.user_package_id = package.id

        order = None
        started = False
        if payment.order_id is not None:
            order = await repo.get_order(self.session, payment.order_id, for_update=True)
            if not order.is_paid:
                started = await self.orders.mark_paid(order, actor_id=None)
        await self.session.flush()
        return PaidResult(payment=payment, order=order, package=package, started=started, credit=credit)

    async def confirm_manual(self, order_id: int, manager_id: int) -> PaidResult:
        """Менеджер увидел перевод на карту по заказу (с чеком или без)."""
        order = await repo.get_order(self.session, order_id)
        if order.is_paid:
            raise InvalidTransitionError(f"Заказ #{order.id} уже оплачен")
        payment = await self.session.scalar(
            select(Payment)
            .where(
                Payment.order_id == order.id,
                Payment.provider == PaymentProvider.MANUAL_CARD,
                Payment.status == PaymentStatus.PENDING,
            )
            .order_by(Payment.id.desc())
            .limit(1)
        )
        if payment is None:
            payment = await self._create(
                order.user_id, PaymentProvider.MANUAL_CARD, order.price, UZS, order_id=order.id
            )
        return await self.mark_paid(payment.id, raw={"confirmed_by": manager_id})

    async def mark_failed(self, payment_id: int) -> Payment:
        """Менеджер не нашёл перевод по чеку."""
        payment = await repo.get_payment(self.session, payment_id, for_update=True)
        if payment.status is not PaymentStatus.PENDING:
            raise InvalidTransitionError(f"Платёж {payment.id} уже {payment.status}")
        payment.status = PaymentStatus.FAILED
        await self.session.flush()
        return payment

    async def mark_refunded(self, payment_id: int) -> Payment:
        payment = await repo.get_payment(self.session, payment_id, for_update=True)
        if payment.status is not PaymentStatus.PAID:
            raise InvalidTransitionError(f"Платёж {payment.id} не оплачен — возвращать нечего")
        payment.status = PaymentStatus.REFUNDED
        if payment.order_id is not None:
            order = await repo.get_order(self.session, payment.order_id)
            order.is_paid = False
        await self.session.flush()
        return payment

    async def _amount(self, amount_uzs: int, provider: PaymentProvider) -> tuple[int, str]:
        if provider is PaymentProvider.STARS:
            return await self.stars_for(amount_uzs), STARS
        return amount_uzs, UZS

    async def _create(
        self,
        user_id: int,
        provider: PaymentProvider,
        amount: int,
        currency: str,
        *,
        order_id: int | None = None,
        plan_code: PlanCode | None = None,
        credit_order_id: int | None = None,
    ) -> Payment:
        payment = Payment(
            user_id=user_id,
            order_id=order_id,
            plan_code=plan_code,
            credit_order_id=credit_order_id,
            provider=provider,
            amount=amount,
            currency=currency,
        )
        self.session.add(payment)
        await self.session.flush()
        return payment
