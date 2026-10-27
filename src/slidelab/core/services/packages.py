from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from slidelab.core import repositories as repo
from slidelab.core.enums import LedgerReason, PaidFrom, PlanCode
from slidelab.core.errors import InsufficientPackageError
from slidelab.core.models import Order, PackageLedger, PackagePlan, UserPackage
from slidelab.core.models.base import as_utc, utcnow
from slidelab.core.services.pricing import PackageBalance, package_cost


@dataclass(frozen=True, slots=True)
class Credit:
    """Зачёт сданного заказа при покупке пакета: сколько сумов и презентаций засчитать."""

    order_id: int
    amount: int
    units: int


class PackageService:
    """Пакеты презентаций. Сервис не коммитит — транзакцией управляет вызывающий код."""

    def __init__(self, session: AsyncSession, clock: Callable[[], datetime] = utcnow) -> None:
        self.session = session
        self.clock = clock

    async def balance(self, user_id: int) -> PackageBalance | None:
        package = await repo.get_active_package(self.session, user_id, self.clock())
        if package is None:
            return None
        plan = await self.session.get(PackagePlan, package.plan_code)
        return PackageBalance(
            plan=package.plan_code,
            left=package.left,
            notes_free=bool(plan and plan.notes_free),
        )

    async def activate(
        self,
        user_id: int,
        plan_code: PlanCode,
        reason: LedgerReason = LedgerReason.PURCHASE,
        credit: Credit | None = None,
    ) -> UserPackage:
        """Пакет после оплаты (или выдача менеджером).

        Пакеты складываются: остаток действующего переносится в новый, срок — самый дальний,
        VIP остаётся VIP. Засчитанный заказ уменьшает число презентаций в новом пакете.
        """
        plan = await repo.get_plan(self.session, plan_code)
        now = self.clock()
        current = await repo.get_active_package(self.session, user_id, now, for_update=True)

        count = plan.count - (credit.units if credit else 0)
        expires = now + timedelta(days=plan.days)
        code = plan.code
        carried = 0
        if current is not None:
            carried = current.left
            expires = max(expires, as_utc(current.expires_at))
            if current.plan_code is PlanCode.VIP:
                code = PlanCode.VIP

        package = UserPackage(
            user_id=user_id, plan_code=code, total=count + carried, left=count + carried, expires_at=expires
        )
        self.session.add(package)
        await self.session.flush()
        self._ledger(package, count, reason)
        if current is not None and carried:
            current.left = 0
            self._ledger(current, -carried, LedgerReason.CARRY_OVER)
            self._ledger(package, carried, LedgerReason.CARRY_OVER)
        if credit is not None:
            order = await repo.get_order(self.session, credit.order_id, for_update=True)
            order.credit_used = True
        await self.session.flush()
        return package

    async def debit(self, order: Order) -> UserPackage:
        """Списать презентации за заказ — сразу при оформлении."""
        package = await repo.get_active_package(self.session, order.user_id, self.clock(), for_update=True)
        if package is None or package.left < order.package_cost:
            raise InsufficientPackageError(f"В пакете не хватает презентаций для заказа #{order.id}")
        package.left -= order.package_cost
        self._ledger(package, -order.package_cost, LedgerReason.ORDER, order)
        await self.session.flush()
        return package

    async def refund(self, order: Order) -> None:
        """Вернуть списанное за отменённый заказ. Если ничего не списывали — ничего не делает."""
        entries = await repo.order_package_debits(self.session, order.id)
        owed = -sum(e.delta for e in entries)
        if owed <= 0:
            return
        # Возвращаем в действующий пакет (старый мог уже перенестись в новый), иначе — туда, откуда списали
        target = await repo.get_active_package(self.session, order.user_id, self.clock(), for_update=True)
        if target is None:
            target = await self.session.get(UserPackage, entries[-1].user_package_id)
        assert target is not None
        target.left += owed
        self._ledger(target, owed, LedgerReason.REFUND, order)
        await self.session.flush()

    # --- зачёт заказа в пакет ---

    def offer_credit(self, order: Order, days: int) -> bool:
        """После сдачи оплаченного заказа: N дней можно купить пакет и засчитать этот заказ."""
        if days <= 0 or order.credit_until is not None:
            return False
        if order.paid_from is not PaidFrom.CASH or not order.is_paid or order.price <= 0:
            return False
        order.credit_until = self.clock() + timedelta(days=days)
        return True

    async def credit_for(self, order_id: int, plan_code: PlanCode) -> Credit | None:
        order = await repo.get_order(self.session, order_id)
        if order.credit_until is None or order.credit_used or self.clock() > as_utc(order.credit_until):
            return None
        plan = await repo.get_plan(self.session, plan_code)
        units = package_cost(order.slides)
        if order.price >= plan.price or units >= plan.count:
            return None
        return Credit(order_id=order.id, amount=order.price, units=units)

    def _ledger(self, package: UserPackage, delta: int, reason: LedgerReason, order: Order | None = None) -> None:
        self.session.add(
            PackageLedger(
                user_package_id=package.id,
                order_id=order.id if order else None,
                delta=delta,
                reason=reason,
            )
        )
