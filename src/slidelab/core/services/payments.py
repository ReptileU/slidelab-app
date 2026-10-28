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
from slidelab.core.enums import OrderStatus, PaymentProvider, PaymentStatus, PlanCode
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
    attention: str | None = None  # деньги пришли, но что-то не так — владелец должен разобраться


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

    async def best_credit(self, user_id: int, plan_code: PlanCode) -> int | None:
        """Сданный заказ клиента, который ещё можно засчитать в этот пакет (самый свежий)."""
        ids = await self.session.scalars(
            select(Order.id)
            .where(
                Order.user_id == user_id,
                Order.credit_until > self.orders.clock(),
                Order.credit_used.is_(False),
                Order.is_paid.is_(True),
            )
            .order_by(Order.id.desc())
        )
        for order_id in ids.all():
            if await self.packages.credit_for(order_id, plan_code) is not None:
                return order_id
        return None

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
            why = {PaymentStatus.REFUNDED: "возвращён", PaymentStatus.FAILED: "закрыт — уже оплачено другим способом"}
            raise InvalidTransitionError(f"Счёт {payment.id} {why.get(payment.status, str(payment.status))}")

        payment.status = PaymentStatus.PAID
        payment.external_id = external_id
        payment.raw = raw
        await self._close_siblings(payment)
        await self.session.flush()

        package = None
        credit = None
        attention = None
        if payment.plan_code is not None:
            if payment.credit_order_id is not None:
                credit = await self.packages.credit_for(payment.credit_order_id, payment.plan_code, at_payment=True)
                if credit is None:
                    attention = (
                        f"Пакет оплачен со скидкой за заказ #{payment.credit_order_id}, но этот заказ уже засчитан "
                        "или возвращён. Пакет включён полностью — проверьте доплату."
                    )
            package = await self.packages.activate(payment.user_id, payment.plan_code, credit=credit)
            payment.user_package_id = package.id

        order = None
        started = False
        if payment.order_id is not None:
            order = await repo.get_order(self.session, payment.order_id, for_update=True)
            if order.status is OrderStatus.CANCELLED:
                attention = f"Пришла оплата за отменённый заказ #{order.id} — верните деньги клиенту."
            elif order.is_paid:
                attention = f"Заказ #{order.id} уже был оплачен — это второй платёж, верните его клиенту."
            else:
                started = await self.orders.mark_paid(order, actor_id=None)
        await self.session.flush()
        return PaidResult(
            payment=payment, order=order, package=package, started=started, credit=credit, attention=attention
        )

    async def confirm_manual(self, order_id: int, manager_id: int) -> PaidResult:
        """Менеджер увидел перевод на карту по заказу (с чеком или без)."""
        order = await repo.get_order(self.session, order_id, for_update=True)
        if order.is_paid:
            raise InvalidTransitionError(f"Заказ #{order.id} уже оплачен")
        if order.status is OrderStatus.CANCELLED:
            raise InvalidTransitionError(f"Заказ #{order.id} отменён")
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
            order = await repo.get_order(self.session, payment.order_id, for_update=True)
            order.is_paid = False
            order.credit_until = None  # возвращённые деньги в пакет не засчитываются
        await self.session.flush()
        return payment

    async def _close_siblings(self, paid: Payment) -> None:
        """Остальные неоплаченные счета за то же самое закрываем: оплатили звёздами — кнопка «Деньги пришли»
        по переводу уже не включит пакет второй раз."""
        stmt = select(Payment).where(
            Payment.user_id == paid.user_id, Payment.status == PaymentStatus.PENDING, Payment.id != paid.id
        )
        if paid.order_id is not None:
            stmt = stmt.where(Payment.order_id == paid.order_id)
        elif paid.plan_code is not None:
            stmt = stmt.where(Payment.plan_code == paid.plan_code, Payment.order_id.is_(None))
        else:
            return
        for other in (await self.session.scalars(stmt)).all():
            other.status = PaymentStatus.FAILED

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
        # Тот же неоплаченный счёт уже есть — отдаём его: каждое «Оплатить» не плодит новые платежи,
        # а владелец не подтвердит одну оплату дважды
        existing = await self.session.scalar(
            select(Payment)
            .where(
                Payment.user_id == user_id,
                Payment.provider == provider,
                Payment.status == PaymentStatus.PENDING,
                Payment.amount == amount,
                Payment.currency == currency,
                Payment.order_id == order_id if order_id is not None else Payment.order_id.is_(None),
                Payment.plan_code == plan_code if plan_code is not None else Payment.plan_code.is_(None),
                Payment.credit_order_id == credit_order_id
                if credit_order_id is not None
                else Payment.credit_order_id.is_(None),
            )
            .order_by(Payment.id.desc())
            .limit(1)
        )
        if existing is not None:
            return existing
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
