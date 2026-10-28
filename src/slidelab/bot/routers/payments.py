"""Оплата: перевод на карту с чеком и звёзды Telegram."""

import html
import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, LabeledPrice, Message, PreCheckoutQuery
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from slidelab.core import repositories as repo
from slidelab.core.enums import PaymentProvider, PaymentStatus, PlanCode
from slidelab.core.errors import DomainError
from slidelab.core.i18n import money, t
from slidelab.core.models import Payment, User
from slidelab.core.services.payments import PaymentService
from slidelab.telegram import keyboards as kb
from slidelab.telegram import views
from slidelab.telegram.callbacks import PayCb
from slidelab.telegram.flows import Flows
from slidelab.telegram.states import ReceiptForm

router = Router(name="payments")
log = logging.getLogger(__name__)


def _payment_id(payload: str) -> int | None:
    prefix, _, value = payload.partition(":")
    return int(value) if prefix == "pay" and value.isdigit() else None


async def _legacy_payment(session: AsyncSession, user: User, payload: str, amount: int) -> Payment | None:
    """Счёт, выставленный прежним ботом: «o:12» — заказ, «s:month» или «s:month.12» — пакет (с зачётом #12).

    Такие счета ещё могут лежать в чатах клиентов. Заводим под них платёж, если сумма совпадает.
    """
    kind, _, ref = payload.partition(":")
    service = PaymentService(session)
    pending = select(Payment).where(
        Payment.user_id == user.id,
        Payment.provider == PaymentProvider.STARS,
        Payment.status == PaymentStatus.PENDING,
        Payment.amount == amount,
    )
    if kind == "o" and ref.isdigit():
        order = await repo.get_order(session, int(ref))
        if order.user_id != user.id:
            return None
        found = await session.scalar(pending.where(Payment.order_id == order.id).order_by(Payment.id.desc()))
        payment = found or await service.for_order(order, PaymentProvider.STARS)
    elif kind == "s":
        plan, _, credit = ref.partition(".")
        if plan not in PlanCode._value2member_map_:
            return None
        found = await session.scalar(pending.where(Payment.plan_code == PlanCode(plan)).order_by(Payment.id.desc()))
        payment = found or await service.for_plan(
            user.id, PlanCode(plan), PaymentProvider.STARS, int(credit) if credit.isdigit() else None
        )
    else:
        return None
    return payment if payment.amount == amount else None


async def _resolve(session: AsyncSession, user: User, payload: str, amount: int) -> int | None:
    payment_id = _payment_id(payload)
    if payment_id is not None:
        return payment_id
    try:
        legacy = await _legacy_payment(session, user, payload, amount)
    except DomainError:
        return None
    return legacy.id if legacy else None


async def create_payment(session: AsyncSession, user: User, data: PayCb, provider: PaymentProvider) -> Payment:
    service = PaymentService(session)
    if data.kind == "plan":
        return await service.for_plan(user.id, PlanCode(data.ref), provider, data.credit or None)
    order = await repo.get_order(session, int(data.ref))
    if order.user_id != user.id:
        raise DomainError("Чужой заказ")
    return await service.for_order(order, provider)


# --- перевод на карту ------------------------------------------------------------


@router.callback_query(PayCb.filter(F.action == "card"))
async def on_card_paid(callback: CallbackQuery, callback_data: PayCb, state: FSMContext, user: User) -> None:
    await callback.answer()
    await state.set_state(ReceiptForm.waiting)
    await state.update_data(kind=callback_data.kind, ref=callback_data.ref, credit=callback_data.credit)
    if isinstance(callback.message, Message):
        await callback.message.answer(t(user.lang, "receipt_ask"))


@router.message(ReceiptForm.waiting, F.photo | F.document | (F.text & ~F.text.in_(kb.ALL_MENU_TEXTS)))
async def on_receipt(message: Message, state: FSMContext, session: AsyncSession, user: User, flows: Flows) -> None:
    data = PayCb(action="card", **await state.get_data())
    await state.clear()
    try:
        payment = await create_payment(session, user, data, PaymentProvider.MANUAL_CARD)
    except DomainError:
        await message.answer(t(user.lang, "already_paid"))
        return
    await session.commit()
    if payment.order_id:
        what = f"заказ #{payment.order_id}"
        flows.pipeline.add_note(payment.order_id, "Клиент", "сообщил об оплате переводом (чек у владельца в Telegram)")
    else:
        what = f"пакет «{t(None, 'plan_' + data.ref)}»" + (
            f" (засчитан #{data.credit})" if payment.credit_order_id else ""
        )
    await flows.n.staff(
        f"🧾 <b>Чек: {what}</b> · {money(payment.amount)} сум\n"
        f"{html.escape(views.client_name(user))} · ID: <code>{user.tg_id}</code>\n"
        "Проверьте поступление на карту 👇",
        user=user,
    )
    await flows.n.copy_to_staff(message, user)
    await flows.n.staff("Деньги пришли?", kb.staff_receipt(payment.id), user=user)
    await message.answer(t(user.lang, "receipt_sent"), reply_markup=await flows.n.menu(user))


# --- звёзды -------------------------------------------------------------------------


@router.callback_query(PayCb.filter(F.action == "stars"))
async def on_stars_invoice(callback: CallbackQuery, callback_data: PayCb, session: AsyncSession, user: User) -> None:
    """Запасной путь, если ссылка на оплату не создалась: счёт отдельным сообщением."""
    try:
        payment = await create_payment(session, user, callback_data, PaymentProvider.STARS)
    except DomainError:
        await callback.answer(t(user.lang, "already_paid"), show_alert=True)
        return
    await session.commit()
    await callback.answer()
    lang = user.lang
    if callback_data.kind == "plan":
        title = t(lang, "invoice_package", plan=t(lang, "plan_" + callback_data.ref))
        plan = await repo.get_plan(session, PlanCode(callback_data.ref))
        desc = t(lang, "invoice_package_desc", count=plan.count, days=plan.days)
    else:
        order = await repo.get_order(session, int(callback_data.ref))
        title = t(lang, "invoice_order", id=order.id)
        desc = t(lang, "invoice_order_desc", topic=order.topic[:80], slides=t(lang, "slides_" + order.slides.value))
    if isinstance(callback.message, Message):
        await callback.message.answer_invoice(
            title=title[:32],
            description=desc[:255],
            payload=f"pay:{payment.id}",
            currency="XTR",
            prices=[LabeledPrice(label=title[:32], amount=payment.amount)],
        )


@router.pre_checkout_query()
async def on_pre_checkout(query: PreCheckoutQuery, session: AsyncSession, user: User) -> None:
    payment_id = await _resolve(session, user, query.invoice_payload, query.total_amount)
    if payment_id is None:
        await query.answer(ok=False, error_message=t(user.lang, "error", admin="slidelab_uz"))
        return
    await session.commit()  # платёж под старый счёт должен сохраниться до successful_payment
    try:
        await PaymentService(session).check_pending(payment_id, query.total_amount, query.currency)
    except DomainError as e:
        await query.answer(ok=False, error_message=str(e))
        return
    await query.answer(ok=True)


@router.message(F.successful_payment)
async def on_successful_payment(message: Message, session: AsyncSession, user: User, flows: Flows) -> None:
    sp = message.successful_payment
    assert sp is not None
    # после отката объекты сессии устаревают — нужное для предупреждения берём заранее
    who, tg_id, lang = views.client_name(user), user.tg_id, user.lang
    payment_id = await _resolve(session, user, sp.invoice_payload, sp.total_amount)
    try:
        if payment_id is None:
            raise DomainError(f"не найден счёт {sp.invoice_payload}")
        result = await PaymentService(session).mark_paid(
            payment_id, external_id=sp.telegram_payment_charge_id, raw=sp.model_dump(mode="json")
        )
        await session.commit()
    except Exception as e:
        # Звёзды уже списаны, а Telegram это сообщение не повторит — владелец должен узнать в любом случае
        await session.rollback()
        log.exception("Оплата звёздами не записалась")
        await flows.n.staff(
            f"⚠️ <b>Звёзды получены, но оплата не записалась</b>\n{sp.total_amount} ⭐ · счёт "
            f"<code>{html.escape(sp.invoice_payload)}</code> · charge <code>{sp.telegram_payment_charge_id}</code>\n"
            f"{html.escape(who)} · ID: <code>{tg_id}</code>\n{html.escape(str(e))[:300]}"
        )
        await message.answer(t(lang, "receipt_sent"))
        return
    await flows.announce_paid(result, user)
    if result.order is not None and not result.already_paid:
        await flows.n.staff(
            f"⭐ Возврат при необходимости — кнопка «Вернуть звёзды» в карточке заказа #{result.order.id}", user=user
        )
    await session.commit()
