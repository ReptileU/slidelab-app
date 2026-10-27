"""Жизненный цикл заказа.

Статус (status) — то, что видит клиент: принят → обложка → оплата → в работе → готово.
Стадия (stage) — что делает конвейер Claude: обложка / презентация / правки, «сделать» или «на проверке».
"""

from collections.abc import Callable
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from slidelab.core import repositories as repo
from slidelab.core.enums import Lang, OrderSource, OrderStatus, PaidFrom, Stage
from slidelab.core.errors import ForbiddenError, InvalidTransitionError, PaymentRequiredError
from slidelab.core.models import Order, OrderEvent, Revision
from slidelab.core.models.base import utcnow
from slidelab.core.schemas.order import OrderDraft
from slidelab.core.services import pricing
from slidelab.core.services.packages import PackageService

S = OrderStatus

# Допустимые переходы. Отмена возможна на любом этапе до готовности.
TRANSITIONS: dict[OrderStatus, frozenset[OrderStatus]] = {
    S.NEW: frozenset({S.COVER, S.CANCELLED}),
    S.COVER: frozenset({S.AWAITING_PAYMENT, S.WORK, S.CANCELLED}),
    S.AWAITING_PAYMENT: frozenset({S.WORK, S.COVER, S.CANCELLED}),  # COVER — передумал по обложке
    S.WORK: frozenset({S.DONE, S.CANCELLED}),
    S.DONE: frozenset({S.REVISION}),
    S.REVISION: frozenset({S.DONE}),
    S.CANCELLED: frozenset(),
}

PRICE_EDITABLE = frozenset({S.NEW, S.COVER, S.AWAITING_PAYMENT})
# Оплату принимаем заранее — с момента заказа и до начала работы
PAYABLE = frozenset({S.NEW, S.COVER, S.AWAITING_PAYMENT})


class OrderService:
    """Сервис не коммитит — транзакцией управляет вызывающий код."""

    def __init__(self, session: AsyncSession, clock: Callable[[], datetime] = utcnow) -> None:
        self.session = session
        self.clock = clock
        self.packages = PackageService(session, clock)

    async def quote(self, user_id: int, req: pricing.QuoteRequest) -> pricing.Quote:
        rules = await repo.get_price_rules(self.session)
        first_order = not await repo.has_orders(self.session, user_id)
        balance = await self.packages.balance(user_id)
        return pricing.quote(req, rules, first_order=first_order, package=balance)

    async def create(
        self,
        user_id: int,
        draft: OrderDraft,
        idempotency_key: str | None = None,
        *,
        source: OrderSource = OrderSource.CHAT,
        ui_lang: Lang = Lang.RU,
    ) -> Order:
        if idempotency_key:
            existing = await repo.get_order_by_idempotency_key(self.session, user_id, idempotency_key)
            if existing is not None:
                return existing

        q = await self.quote(user_id, draft.quote_request())
        style_id = await repo.get_style_id(self.session, draft.style_key) if draft.style_key else None
        order = Order(
            user_id=user_id,
            topic=draft.topic,
            slides=draft.slides,
            deadline=draft.deadline,
            pres_lang=draft.pres_lang,
            design=draft.design,
            style_id=style_id,
            template_url=draft.template_url or None,
            extra_text=draft.extra_text,
            extra_notes=draft.extra_notes,
            need_humor=draft.need_humor,
            contact=draft.contact or None,
            comment=draft.comment or None,
            sources=draft.sources or None,
            has_source_files=draft.has_source_files,
            source=source,
            ui_lang=ui_lang,
            status=S.NEW,
            price=q.price,
            paid_from=q.paid_from,
            package_cost=q.package_cost,
            is_paid=q.price == 0,  # пакет без доплаты — уже оплачено
            stage=Stage.COVER_TODO,  # бесплатную обложку конвейер начинает сразу
            stage_at=self.clock(),
            idempotency_key=idempotency_key,
        )
        self.session.add(order)
        await self.session.flush()
        if order.paid_from is PaidFrom.PACKAGE:
            await self.packages.debit(order)
        self._event(order, None, S.NEW, actor_id=user_id)
        await self.session.flush()
        return order

    async def transition(
        self, order_id: int, to: OrderStatus, actor_id: int | None, comment: str | None = None
    ) -> Order:
        order = await repo.get_order(self.session, order_id, for_update=True)
        await self._apply(order, to, actor_id, comment)
        return order

    def set_stage(self, order: Order, stage: Stage) -> None:
        order.stage = stage
        order.stage_at = self.clock()
        order.alerted = None  # новая стадия — сторож считает заново

    async def cover_sent(self, order: Order, actor_id: int | None) -> None:
        """Обложка ушла клиенту."""
        if order.status is S.NEW:
            await self._apply(order, S.COVER, actor_id, comment="обложка отправлена")
        self.set_stage(order, Stage.COVER_SENT)

    async def approve_cover(self, order_id: int, user_id: int) -> Order:
        """Клиенту понравилась обложка: оплачено — сразу в работу, иначе ждём оплату."""
        order = await repo.get_order(self.session, order_id, for_update=True)
        self._own(order, user_id)
        if order.status is not S.COVER:
            return order  # повторное нажатие или уже в работе
        if order.is_paid:
            await self._apply(order, S.WORK, user_id, comment="обложка согласована")
        else:
            await self._apply(order, S.AWAITING_PAYMENT, user_id, comment="обложка согласована")
            self.set_stage(order, Stage.COVER_OK)
        return order

    async def request_cover_change(self, order_id: int, user_id: int) -> Order:
        """Клиент хочет другую обложку — конвейер делает её заново."""
        order = await repo.get_order(self.session, order_id, for_update=True)
        self._own(order, user_id)
        if order.status not in (S.NEW, S.COVER, S.AWAITING_PAYMENT):
            raise InvalidTransitionError("Обложку уже не поменять — презентация в работе")
        if order.status is S.AWAITING_PAYMENT:
            await self._apply(order, S.COVER, user_id, comment="клиент передумал по обложке")
        self.set_stage(order, Stage.COVER_TODO)
        return order

    async def mark_paid(self, order: Order, actor_id: int | None) -> bool:
        """Оплата получена. Если обложка уже у клиента или согласована — сразу в работу.

        Возвращает True, если работа началась.
        """
        order.is_paid = True
        if order.status in (S.COVER, S.AWAITING_PAYMENT):
            await self._apply(order, S.WORK, actor_id, comment="оплачено")
            return True
        await self.session.flush()
        return False

    async def deliver(
        self,
        order: Order,
        actor_id: int | None,
        *,
        deliver_dir: str | None = None,
        files: list[str] | None = None,
        links: dict[str, str] | None = None,
    ) -> None:
        """Готово: презентация (или исправленная версия) отправлена клиенту."""
        await self._apply(order, S.DONE, actor_id, comment="готово")
        self.set_stage(order, Stage.DONE)
        if deliver_dir is not None:
            order.deliver_dir = deliver_dir
            order.deliver_files = files or []
            order.deliver_links = links or {}

    async def set_price(self, order_id: int, price: int, actor_id: int | None) -> Order:
        """Менеджер меняет цену — только пока заказ не оплачен и не в работе."""
        order = await repo.get_order(self.session, order_id, for_update=True)
        if order.status not in PRICE_EDITABLE or order.is_paid:
            raise InvalidTransitionError(f"Заказ #{order.id}: цену можно менять только до оплаты")
        if price < 0:
            raise ValueError("Цена не может быть отрицательной")
        old, order.price = order.price, price
        if price == 0:
            order.is_paid = True
        self._event(order, order.status, order.status, actor_id, comment=f"цена {old} → {price}")
        await self.session.flush()
        return order

    async def assign(self, order_id: int, manager_id: int) -> Order:
        order = await repo.get_order(self.session, order_id, for_update=True)
        order.manager_id = manager_id
        await self.session.flush()
        return order

    async def request_revision(self, order_id: int, user_id: int, text: str) -> Revision:
        """Правки от клиента. Две бесплатные, дальше — с пометкой «платная» для менеджера.

        Пока правки уже в работе, новые сообщения дополняют их и не тратят бесплатную попытку.
        """
        order = await repo.get_order(self.session, order_id, for_update=True)
        self._own(order, user_id)
        if order.status not in (S.DONE, S.REVISION):
            raise InvalidTransitionError("Правки можно отправить, когда заказ готов")

        is_paid = False
        if order.status is S.DONE:
            is_paid = order.revisions_left == 0
            if not is_paid:
                order.revisions_left -= 1
            await self._apply(order, S.REVISION, user_id, comment=None)
            self.set_stage(order, Stage.EDIT_TODO)
        revision = Revision(order_id=order.id, text=text, is_paid=is_paid)
        self.session.add(revision)
        await self.session.flush()
        return revision

    async def _apply(self, order: Order, to: OrderStatus, actor_id: int | None, comment: str | None) -> None:
        current = order.status
        if to not in TRANSITIONS[current]:
            raise InvalidTransitionError(f"Заказ #{order.id}: нельзя перейти из {current} в {to}")
        if to is S.WORK:
            if not order.is_paid:
                raise PaymentRequiredError(f"Заказ #{order.id} не оплачен")
            self.set_stage(order, Stage.DECK_TODO)
        elif to is S.CANCELLED and order.package_cost:
            await self.packages.refund(order)

        order.status = to
        self._event(order, current, to, actor_id, comment)
        await self.session.flush()

    @staticmethod
    def _own(order: Order, user_id: int) -> None:
        if order.user_id != user_id:
            raise ForbiddenError(f"Заказ #{order.id} принадлежит другому клиенту")

    def _event(
        self,
        order: Order,
        from_status: OrderStatus | None,
        to_status: OrderStatus,
        actor_id: int | None,
        comment: str | None = None,
    ) -> None:
        self.session.add(
            OrderEvent(
                order_id=order.id,
                from_status=from_status,
                to_status=to_status,
                actor_id=actor_id,
                comment=comment,
            )
        )
