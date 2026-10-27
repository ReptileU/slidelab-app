"""«Мои заказы» и всё, что клиент делает с заказом: оплата, обложка, формат, правки, оценка."""

import html
import time
from typing import Any

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from slidelab.bot.utils import file_of
from slidelab.core import repositories as repo
from slidelab.core.enums import OrderStatus
from slidelab.core.errors import DomainError
from slidelab.core.i18n import t
from slidelab.core.models import Order, Review, User
from slidelab.core.models.base import utcnow
from slidelab.core.services.orders import OrderService
from slidelab.telegram import keyboards as kb
from slidelab.telegram import views
from slidelab.telegram.callbacks import FmtCb, OrderCb, RateCb
from slidelab.telegram.flows import Flows, Material
from slidelab.telegram.notifier import lang_of
from slidelab.telegram.states import CoverChangeForm, RevisionForm

router = Router(name="orders")
router.message.filter(F.chat.type == "private")

# Защита от двойного нажатия формата: тот же формат не шлём повторно две минуты
_recent_formats: dict[tuple[int, int, str], float] = {}


async def own(session: AsyncSession, user: User, order_id: int) -> Order | None:
    order = await repo.get_order(session, order_id)
    return order if order.user_id == user.id else None


# --- список -------------------------------------------------------------------


@router.message(Command("orders"))
@router.message(F.text.in_(kb.menu_texts("btn_orders")))
async def show_orders(message: Message, session: AsyncSession, user: User) -> None:
    orders = [o for o in await repo.list_user_orders(session, user.id, limit=20) if not o.hidden][:10]
    package = await repo.get_active_package(session, user.id, utcnow())
    text = t(user.lang, "orders_title") if orders else t(user.lang, "orders_empty")
    if package is not None:
        text += t(
            user.lang, "my_package", left=package.left, total=package.total, date=views.date_short(package.expires_at)
        )
    await message.answer(text, reply_markup=kb.orders_list(lang_of(user), orders) if orders else None)


@router.callback_query(OrderCb.filter(F.action == "show"))
async def on_show(callback: CallbackQuery, callback_data: OrderCb, session: AsyncSession, user: User) -> None:
    await callback.answer()
    order = await own(session, user, callback_data.order_id)
    if order is not None and isinstance(callback.message, Message):
        await callback.message.answer(
            views.client_order_card(user.lang, order), reply_markup=kb.order_actions(lang_of(user), order)
        )


@router.callback_query(OrderCb.filter(F.action == "hide"))
async def on_hide(
    callback: CallbackQuery, callback_data: OrderCb, session: AsyncSession, user: User, flows: Flows
) -> None:
    await callback.answer()
    await hide(session, user, flows, callback_data.order_id)


async def hide(session: AsyncSession, user: User, flows: Flows, order_id: int | None) -> None:
    """Убрать готовый или отменённый заказ из «Моих заказов» (данные остаются у нас)."""
    orders = await repo.list_user_orders(session, user.id, limit=100)
    done = [
        o
        for o in orders
        if o.status in (OrderStatus.DONE, OrderStatus.CANCELLED)
        and not o.hidden
        and (order_id is None or o.id == order_id)
    ]
    if not done:
        return
    for o in done:
        o.hidden = True
    await session.commit()
    ids = ", #".join(str(o.id) for o in done)
    await flows.n.client(user, "hidden", await flows.n.menu(user), id=ids)


# --- оплата ---------------------------------------------------------------------


@router.callback_query(OrderCb.filter(F.action == "pay"))
async def on_pay(
    callback: CallbackQuery, callback_data: OrderCb, session: AsyncSession, user: User, flows: Flows
) -> None:
    order = await own(session, user, callback_data.order_id)
    if order is None or order.is_paid:
        await callback.answer(t(user.lang, "already_paid"))
        return
    await callback.answer()
    await flows.n.send_pay(user, amount=order.price, order=order)
    await session.commit()


# --- обложка ----------------------------------------------------------------------


@router.callback_query(OrderCb.filter(F.action == "cover_ok"))
async def on_cover_ok(
    callback: CallbackQuery, callback_data: OrderCb, session: AsyncSession, user: User, flows: Flows
) -> None:
    await callback.answer()
    if isinstance(callback.message, Message):
        await callback.message.edit_reply_markup(reply_markup=None)
    order = await own(session, user, callback_data.order_id)
    if order is None or order.status is not OrderStatus.COVER:
        return
    await OrderService(session).approve_cover(order.id, user.id)
    await flows.sync(order)
    await session.commit()
    if order.is_paid:  # оплачено заранее — approve_cover сразу отправил в работу
        await flows.n.client(user, "cover_go")
        await flows.n.refresh_card(order, "👍 обложка одобрена, оплачено — Claude делает презентацию")
    else:
        await flows.n.client(user, "cover_pay")
        await flows.n.send_pay(user, amount=order.price, order=order)
        await flows.n.refresh_card(order, "👍 обложка одобрена — ждём оплату, реквизиты клиенту отправлены")
    await session.commit()


@router.callback_query(OrderCb.filter(F.action == "cover_change"))
async def on_cover_change(callback: CallbackQuery, callback_data: OrderCb, state: FSMContext, user: User) -> None:
    await callback.answer()
    await state.set_state(CoverChangeForm.text)
    await state.update_data(order_id=callback_data.order_id)
    if isinstance(callback.message, Message):
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer(t(user.lang, "cover_change_prompt"))


@router.message(CoverChangeForm.text)
async def on_cover_change_text(
    message: Message, state: FSMContext, session: AsyncSession, user: User, flows: Flows
) -> None:
    order_id = (await state.get_data())["order_id"]
    await state.clear()
    try:
        order = await OrderService(session).request_cover_change(order_id, user.id)
    except DomainError:
        await message.answer(t(user.lang, "revise_not_allowed"))
        return
    text = message.text or message.caption or ""
    if text:
        flows.pipeline.add_note(order.id, "Клиент (обложка)", text)
    ref = file_of(message)
    if ref is not None:
        await flows.save_materials(order.id, [Material(name=ref.name, file_id=ref.file_id)], sub="edits")
    await flows.sync(order)
    await session.commit()
    await flows.n.copy_to_staff(
        message, user, header=f"🎨 <b>#{order.id}: хочет другую обложку</b> — Claude переделает"
    )
    await message.answer(t(user.lang, "cover_change_sent"))


# --- готовые файлы и формат ------------------------------------------------------


@router.callback_query(OrderCb.filter(F.action == "files"))
async def on_files(
    callback: CallbackQuery, callback_data: OrderCb, session: AsyncSession, user: User, flows: Flows
) -> None:
    await callback.answer(t(user.lang, "fmt_sending"))
    order = await own(session, user, callback_data.order_id)
    if order is not None:
        await flows.offer_formats(order, user)
        await session.commit()


@router.callback_query(FmtCb.filter())
async def on_format(
    callback: CallbackQuery, callback_data: FmtCb, session: AsyncSession, user: User, flows: Flows
) -> None:
    await callback.answer(t(user.lang, "fmt_sending"))
    await send_format(session, user, flows, callback_data.order_id, callback_data.fmt)


async def send_format(session: AsyncSession, user: User, flows: Flows, order_id: int, fmt: str) -> None:
    order = await own(session, user, order_id)
    if order is None:
        return
    key = (user.tg_id, order_id, fmt)
    now = time.monotonic()
    if now - _recent_formats.get(key, -1e9) < 120:
        return
    _recent_formats[key] = now
    if not await flows.deliver(order, user, fmt):
        await flows.n.client(user, "fmt_none")
    await session.commit()


# --- правки ---------------------------------------------------------------------


async def ask_revision(message: Message, state: FSMContext, session: AsyncSession, user: User, order_id: int) -> None:
    order = await own(session, user, order_id)
    if order is None or order.status is OrderStatus.CANCELLED:
        await message.answer(t(user.lang, "revise_not_allowed"))
        return
    await state.set_state(RevisionForm.collecting)
    await state.update_data(order_id=order.id, texts=[], files=[], copies=[])
    await message.answer(
        t(user.lang, "revise_prompt", id=order.id), reply_markup=kb.send_revision(lang_of(user), order.id)
    )


@router.callback_query(OrderCb.filter(F.action == "revise"))
async def on_revise(
    callback: CallbackQuery, callback_data: OrderCb, state: FSMContext, session: AsyncSession, user: User
) -> None:
    await callback.answer()
    if isinstance(callback.message, Message):
        await ask_revision(callback.message, state, session, user, callback_data.order_id)


@router.message(RevisionForm.collecting)
async def on_revision_part(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    ref = file_of(message)
    if message.text:
        data["texts"].append(message.text)
    if message.caption:
        data["texts"].append(message.caption)
    if ref is not None:
        data["files"].append({"name": ref.name, "file_id": ref.file_id})
        data["copies"].append(message.message_id)  # скриншоты перешлём команде как есть
    await state.update_data(texts=data["texts"], files=data["files"], copies=data["copies"])


@router.callback_query(RevisionForm.collecting, OrderCb.filter(F.action == "send_revision"))
async def on_revision_send(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, user: User, flows: Flows
) -> None:
    data: dict[str, Any] = await state.get_data()
    text = "\n".join(data["texts"]).strip()
    if not text and not data["files"]:
        await callback.answer(t(user.lang, "revise_empty"), show_alert=True)
        return
    await callback.answer()
    try:
        revision = await OrderService(session).request_revision(data["order_id"], user.id, text[:1500] or "(файлы)")
    except DomainError:
        await state.clear()
        await flows.n.client(user, "revise_not_allowed")
        return
    await state.clear()
    order = await repo.get_order(session, data["order_id"])
    flows.pipeline.add_note(order.id, "Клиент (правки)", text or "(см. файлы в edits/)")
    await flows.save_materials(order.id, [Material(**f) for f in data["files"]], sub="edits")
    await flows.sync(order)
    await session.commit()

    paid = " · <b>платная</b>" if revision.is_paid else ""
    await flows.n.refresh_card(order, f"✏️ правки{paid} — Claude вносит:\n{html.escape(text)}")
    if isinstance(callback.message, Message) and flows.settings.staff_chat_id:
        for message_id in data["copies"]:
            await flows.bot.copy_message(flows.settings.staff_chat_id, callback.message.chat.id, message_id)
    await flows.n.client_text(
        user, t(user.lang, "revise_sent") + (t(user.lang, "revise_paid") if revision.is_paid else "")
    )
    await session.commit()


# --- оценка ---------------------------------------------------------------------


@router.callback_query(OrderCb.filter(F.action == "good"))
async def on_good(callback: CallbackQuery, callback_data: OrderCb, user: User) -> None:
    await callback.answer()
    if isinstance(callback.message, Message):
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer(t(user.lang, "rate_ask"), reply_markup=kb.rating(callback_data.order_id))


@router.callback_query(RateCb.filter())
async def on_rate(
    callback: CallbackQuery, callback_data: RateCb, session: AsyncSession, user: User, flows: Flows
) -> None:
    order = await own(session, user, callback_data.order_id)
    stars = max(1, min(5, callback_data.stars))
    if order is None:
        await callback.answer()
        return
    session.add(Review(user_id=user.id, order_id=order.id, stars=stars))
    await session.commit()
    await callback.answer(t(user.lang, "rate_thanks"))
    if isinstance(callback.message, Message):
        await callback.message.edit_text(t(user.lang, "rate_thanks"))
    await flows.n.staff(f"#{order.id} · оценка {'★' * stars}", user=user)
