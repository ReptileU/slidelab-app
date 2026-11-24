"""Жизненный цикл заказа.

Статус (status) — то, что видит клиент: принят → обложка → оплата → в работе → готово.
Стадия (stage) — что делает конвейер Claude: обложка / презентация / правки, «сделать» или «на проверке».
"""

from collections.abc import Callable
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from slidelab.core import repositories as repo
from slidelab.core.enums import CouponOrigin, Deadline, Lang, OrderSource, OrderStatus, PaidFrom, Stage
from slidelab.core.errors import (
    CoverLimitError,
    DueTooSoonError,
    ForbiddenError,
    InvalidTransitionError,
    PaymentRequiredError,
)
from slidelab.core.models import Coupon, Order, OrderEvent, Revision, User
from slidelab.core.models.base import as_utc, utcnow
from slidelab.core.schemas.order import OrderDraft
from slidelab.core.services import points, pricing
from slidelab.core.services.packages import PackageService

S = OrderStatus

# Допустимые переходы. Отмена возможна на любом этапе до готовности.
TRANSITIONS: dict[OrderStatus, frozenset[OrderStatus]] = {
    S.NEW: frozenset({S.COVER, S.WORK, S.CANCELLED}),  # WORK — «сразу всю», без обложки
    S.COVER: frozenset({S.AWAITING_PAYMENT, S.WORK, S.CANCELLED}),
    S.AWAITING_PAYMENT: frozenset({S.WORK, S.COVER, S.CANCELLED}),  # COVER — передумал по обложке
    S.WORK: frozenset({S.DONE, S.CANCELLED}),
    S.DONE: frozenset({S.REVISION, S.CANCELLED}),  # отмена после сдачи — вручную владельцем
    S.REVISION: frozenset({S.DONE, S.CANCELLED}),
    S.CANCELLED: frozenset(),
}

NORMAL_MIN_HOURS = 48  # «Обычно» — не раньше чем через двое суток; быстрее — «Срочно» за доплату

PRICE_EDITABLE = frozenset({S.NEW, S.COVER, S.AWAITING_PAYMENT})
# Оплату принимаем заранее — с момента заказа и до начала работы
PAYABLE = frozenset({S.NEW, S.COVER, S.AWAITING_PAYMENT})
# Клиент сам отменяет заказ, пока презентацию не сдали
CLIENT_CANCELLABLE = frozenset({S.NEW, S.COVER, S.AWAITING_PAYMENT, S.WORK})
# Отмена уже начатой презентации с возвратом оплаты — не чаще раза в столько дней (работа Claude уже потрачена)
WORK_REFUND_DAYS = 30
# Бесплатных обложек без ответа клиента одновременно — защита от спама; «Оплатить сразу» и пакеты не ограничены
FREE_COVERS_MAX = 3


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
        coupons = await repo.open_coupons(self.session, user_id)
        voucher = coupons[0].slides if coupons else None
        user = await self.session.get(User, user_id)
        discount = (user.discount_pct or 0) if user else 0
        return pricing.quote(
            req, rules, first_order=first_order, package=balance, voucher=voucher, discount_pct=discount
        )

    def _due(self, draft: OrderDraft) -> datetime | None:
        """Срок к дате — только у «Обычно» и не раньше чем через NORMAL_MIN_HOURS: быстрее — это «Срочно»."""
        if draft.deadline is not Deadline.NORMAL or draft.due_at is None:
            return None
        due = as_utc(draft.due_at).replace(tzinfo=None)
        if due < self.clock().replace(tzinfo=None) + timedelta(hours=NORMAL_MIN_HOURS):
            raise DueTooSoonError(f"Раньше чем через {NORMAL_MIN_HOURS} ч — только «Срочно»")
        return due

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

        due_at = self._due(draft)
        q = await self.quote(user_id, draft.quote_request())
        if not draft.skip_cover and q.price > 0:
            await self._check_free_covers(user_id)
        style_id = await repo.get_style_id(self.session, draft.style_key) if draft.style_key else None
        order = Order(
            user_id=user_id,
            topic=draft.topic,
            slides=draft.slides,
            deadline=draft.deadline,
            due_at=due_at,
            pres_lang=draft.pres_lang,
            design=draft.design,
            style_id=style_id,
            template_url=draft.template_url or None,
            extra_text=draft.extra_text,
            extra_notes=draft.extra_notes,
            need_humor=draft.need_humor,
            title_author=draft.title_author or None,
            title_group=draft.title_group or None,
            title_teacher=draft.title_teacher or None,
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
            skip_cover=draft.skip_cover,
            # бесплатную обложку конвейер начинает сразу; «сразу всю» ждёт оплаты и обложку не делает
            stage=None if draft.skip_cover else Stage.COVER_TODO,
            stage_at=self.clock(),
            idempotency_key=idempotency_key,
        )
        self.session.add(order)
        await self.session.flush()
        if q.discount_pct:  # скидка из пакета за баллы потрачена этим заказом (вернётся, если его отменят до оплаты)
            order.discount_pct = q.discount_pct
            user = await self.session.get(User, user_id)
            if user is not None:
                user.discount_pct = None
        if q.voucher:  # база оплачена купоном
            coupon = (await repo.open_coupons(self.session, user_id, for_update=True))[0]
            coupon.used_order_id = order.id
            order.coupon_id = coupon.id
        if order.skip_cover and order.is_paid:  # из пакета без доплаты — сразу в работу
            await self._apply(order, S.WORK, None, comment="сразу всю презентацию — из пакета")
        if order.paid_from is PaidFrom.PACKAGE:
            await self.packages.debit(order)
        self._event(order, None, S.NEW, actor_id=user_id)
        await self.session.flush()
        return order

    async def _check_free_covers(self, user_id: int) -> None:
        """Защита от спама: бесплатных обложек без ответа — не больше FREE_COVERS_MAX. Оплаченным — без ограничений."""
        waiting = await self.session.scalar(
            select(func.count(Order.id)).where(
                Order.user_id == user_id,
                Order.is_paid.is_(False),
                Order.skip_cover.is_(False),
                Order.status.in_([S.NEW, S.COVER, S.AWAITING_PAYMENT]),
            )
        )
        if (waiting or 0) >= FREE_COVERS_MAX:
            raise CoverLimitError(f"У клиента уже {waiting} бесплатных обложек без ответа")

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

    async def cover_first(self, order_id: int, user_id: int) -> Order:
        """Нажал «Сразу всю» случайно: пока не заплатил, возвращаем к бесплатной обложке."""
        order = await repo.get_order(self.session, order_id, for_update=True)
        self._own(order, user_id)
        if not order.skip_cover:
            return order  # уже обычный заказ — повторное нажатие
        if order.is_paid or order.status is not S.NEW:
            raise InvalidTransitionError("Заказ уже оплачен — делаем всю презентацию")
        order.skip_cover = False
        self.set_stage(order, Stage.COVER_TODO)
        await self.session.flush()
        return order

    def refund_on_cancel(self, order: Order, user: User) -> bool:
        """Вернётся ли оплата, если клиент отменит сейчас.

        До начала работы — всегда. Презентацию уже делают — раз в WORK_REFUND_DAYS дней, и не за заказ,
        оплаченный купоном: иначе «заказал купоном → отменил → купон вернулся» по кругу ест работу.
        """
        if order.status is not S.WORK:
            return True
        if order.coupon_id is not None:
            return False
        last = user.work_refund_at
        return last is None or self.clock() - as_utc(last) >= timedelta(days=WORK_REFUND_DAYS)

    async def cancel_by_client(self, order_id: int, user_id: int) -> Order:
        """Клиент отменил заказ сам.

        Не оплачен — просто удаляем из списка. Оплачен из пакета — презентация возвращается в пакет.
        Оплачен деньгами — купон: следующая презентация уже оплачена, платить только за доплаты.
        После начала работы оплата возвращается не всегда — см. refund_on_cancel.
        """
        order = await repo.get_order(self.session, order_id, for_update=True)
        self._own(order, user_id)
        if order.status is S.CANCELLED:
            return order
        if order.status not in CLIENT_CANCELLABLE:
            raise InvalidTransitionError("Презентация уже готова — отменить нельзя, напишите нам")
        user = await self.session.get(User, user_id)
        assert user is not None
        refund = self.refund_on_cancel(order, user)
        paid = order.is_paid or order.coupon_id is not None
        if order.status is S.WORK and refund and paid:
            user.work_refund_at = self.clock()
        keep = (
            refund
            and order.is_paid
            and order.paid_from is PaidFrom.CASH
            and order.price > 0
            and order.coupon_id is None
        )
        comment = "отменил клиент" + ("" if refund or not paid else " — без возврата: работа уже шла")
        await self._apply(order, S.CANCELLED, user_id, comment=comment, refund=refund)
        if keep:
            self.give_coupon(order)
        elif not order.is_paid and order.coupon_id is None:
            order.hidden = True  # не оплачен — убираем из списка
        await self.session.flush()
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
        """Оплата получена. Если клиент уже одобрил обложку — сразу в работу.

        Пока обложку делают или переделывают, оплата только запоминается: работа начнётся,
        когда клиент нажмёт «Нравится» (как в прежнем боте). Возвращает True, если работа началась.
        """
        order.is_paid = True
        cover_ready = order.status is S.COVER and order.stage in (Stage.COVER_SENT, Stage.COVER_OK)
        full_now = order.skip_cover and order.status is S.NEW  # «сразу всю»: обложку не ждём
        if order.status is S.AWAITING_PAYMENT or cover_ready or full_now:
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
        Как в прежнем боте, правки принимаются на любом этапе: пока делается обложка — Claude переделывает
        обложку, пока делается презентация — пожелание просто дописывается к заданию.
        """
        order = await repo.get_order(self.session, order_id, for_update=True)
        self._own(order, user_id)
        if order.status is S.CANCELLED:
            raise InvalidTransitionError("Заказ отменён")

        is_paid = False
        if order.status in (S.NEW, S.COVER, S.AWAITING_PAYMENT):
            if order.status is S.AWAITING_PAYMENT:
                await self._apply(order, S.COVER, user_id, comment="правки к обложке")
            self.set_stage(order, Stage.COVER_TODO)
        elif order.status is S.REVISION and order.stage is Stage.EDIT_REVIEW:
            self.set_stage(order, Stage.EDIT_TODO)  # ещё правки, пока прошлые на проверке — Claude учтёт все
        elif order.status is S.DONE:
            is_paid = order.revisions_left == 0
            if not is_paid:
                order.revisions_left -= 1
            await self._apply(order, S.REVISION, user_id, comment=None)
            self.set_stage(order, Stage.EDIT_TODO)
        revision = Revision(order_id=order.id, text=text, is_paid=is_paid)
        self.session.add(revision)
        await self.session.flush()
        return revision

    async def _apply(
        self, order: Order, to: OrderStatus, actor_id: int | None, comment: str | None, *, refund: bool = True
    ) -> None:
        current = order.status
        if to not in TRANSITIONS[current]:
            raise InvalidTransitionError(f"Заказ #{order.id}: нельзя перейти из {current} в {to}")
        if current is S.NEW and to is S.WORK and not order.skip_cover:  # мимо обложки — только «сразу всю»
            raise InvalidTransitionError(f"Заказ #{order.id}: сначала обложка")
        if to is S.WORK:
            if not order.is_paid:
                raise PaymentRequiredError(f"Заказ #{order.id} не оплачен")
            self.set_stage(order, Stage.DECK_TODO)
        elif to is S.CANCELLED:
            if refund and order.package_cost and not await self.packages.refund(order):
                self.give_coupon(order)  # срок пакета вышел — презентация не пропадает, а становится купоном
            if refund and order.coupon_id is not None:  # был оплачен купоном — купон возвращается клиенту
                coupon = await self.session.get(Coupon, order.coupon_id, with_for_update=True)
                if coupon is not None:
                    coupon.used_order_id = None
            if order.discount_pct and not order.is_paid:  # не оплатил — скидка из пакета за баллы возвращается
                user = await self.session.get(User, order.user_id)
                if user is not None:
                    user.discount_pct = min((user.discount_pct or 0) + order.discount_pct, points.DISCOUNT_MAX)
            order.stage = None  # убираем из конвейера: Claude и сторож его больше не видят
            order.credit_until = None

        order.status = to
        self._event(order, current, to, actor_id, comment)
        await self.session.flush()

    def give_coupon(self, order: Order) -> Coupon:
        """Оплаченная презентация отменённого заказа — купон клиенту (без срока)."""
        coupon = Coupon(user_id=order.user_id, slides=order.slides, origin=CouponOrigin.CANCEL, order_id=order.id)
        self.session.add(coupon)
        return coupon

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
