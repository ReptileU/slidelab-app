"""Кнопки на карточке заказа: обложка, цена, оплата, файлы, отмена, проверка, статусы."""

import html
import re
from contextlib import suppress
from datetime import datetime

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from slidelab.bot.routers.staff.common import ORDER_RE, URL_RE, _ask, owner_of
from slidelab.bot.utils import file_of
from slidelab.core import repositories as repo
from slidelab.core.enums import (
    AttachmentKind,
    OrderStatus,
    PaymentProvider,
    PaymentStatus,
    Stage,
)
from slidelab.core.errors import DomainError
from slidelab.core.i18n import money, t
from slidelab.core.models import (
    Attachment,
    User,
)
from slidelab.core.services.orders import OrderService
from slidelab.core.services.payments import PaymentService
from slidelab.core.services.pipeline import KIND_ACC, TODO, TODO_OF
from slidelab.telegram import keyboards as kb
from slidelab.telegram import views
from slidelab.telegram.callbacks import MgrCb
from slidelab.telegram.flows import Flows, Material
from slidelab.telegram.notifier import lang_of
from slidelab.telegram.states import StaffForm
from slidelab.telegram.widgets import service as widgets

router = Router(name="staff_cards")


@router.callback_query(MgrCb.filter(F.action == "cover"))
async def on_cover(callback: CallbackQuery, callback_data: MgrCb, state: FSMContext) -> None:
    await state.set_state(StaffForm.cover)
    await state.update_data(order_id=callback_data.order_id)
    await _ask(callback, f"Пришлите обложку для #{callback_data.order_id} — фото или файл.")


@router.message(StaffForm.cover, F.photo | F.document)
async def on_cover_file(message: Message, state: FSMContext, session: AsyncSession, user: User, flows: Flows) -> None:
    order_id = (await state.get_data())["order_id"]
    await state.clear()
    order = await repo.get_order(session, order_id)
    ref = file_of(message)
    assert ref is not None
    session.add(Attachment(order_id=order.id, kind=AttachmentKind.COVER, tg_file_id=ref.file_id, file_name=ref.name))
    await OrderService(session).cover_sent(order, actor_id=user.id)
    await flows.sync(order)
    await session.commit()
    await flows.send_cover_file(order, await owner_of(session, order), ref.file_id, photo=bool(message.photo))
    await flows.n.refresh_card(order, "обложка отправлена клиенту")
    await session.commit()


# --- цена ----------------------------------------------------------------------


@router.callback_query(MgrCb.filter(F.action == "price"))
async def on_price(callback: CallbackQuery, callback_data: MgrCb, state: FSMContext) -> None:
    await state.set_state(StaffForm.price)
    await state.update_data(order_id=callback_data.order_id)
    await _ask(callback, f"Новая цена для #{callback_data.order_id} в сумах — только число:")


@router.message(StaffForm.price, F.text)
async def on_price_value(message: Message, state: FSMContext, session: AsyncSession, user: User, flows: Flows) -> None:
    digits = "".join(c for c in message.text or "" if c.isdigit())
    if not digits:
        await message.answer("Нужно число, например 35000.")
        return
    order_id = (await state.get_data())["order_id"]
    await state.clear()
    order = await OrderService(session).set_price(order_id, int(digits), actor_id=user.id)
    await flows.sync(order)
    await session.commit()
    await flows.n.refresh_card(order, f"цена: {money(order.price)} сум")


# --- оплата -----------------------------------------------------------------------


@router.callback_query(MgrCb.filter(F.action == "paid"))
async def on_paid(
    callback: CallbackQuery, callback_data: MgrCb, session: AsyncSession, user: User, flows: Flows
) -> None:
    result = await PaymentService(session).confirm_manual(callback_data.order_id, user.id)
    await session.commit()
    await callback.answer(
        "Оплата отмечена" + (" — Claude делает презентацию" if result.started else ""), show_alert=True
    )
    assert result.order is not None
    await flows.announce_paid(result, await owner_of(session, result.order))
    await session.commit()


@router.callback_query(MgrCb.filter(F.action == "pay_ok"))
async def on_receipt_ok(
    callback: CallbackQuery, callback_data: MgrCb, session: AsyncSession, user: User, flows: Flows
) -> None:
    result = await PaymentService(session).mark_paid(callback_data.payment_id, raw={"confirmed_by": user.id})
    await session.commit()
    await callback.answer("Оплата подтверждена")
    if isinstance(callback.message, Message):
        await callback.message.edit_text(f"✅ Оплата подтверждена · {html.escape(views.client_name(user))}")
    await flows.announce_paid(result, await repo.get_user(session, result.payment.user_id))
    await session.commit()
    await widgets.payment_confirmed(flows.bot, widgets.store_for(flows.settings.data_dir), callback_data.payment_id)


@router.callback_query(MgrCb.filter(F.action == "pay_no"))
async def on_receipt_no(
    callback: CallbackQuery, callback_data: MgrCb, session: AsyncSession, user: User, flows: Flows
) -> None:
    payment = await PaymentService(session).mark_failed(callback_data.payment_id)
    await session.commit()
    await callback.answer()
    if isinstance(callback.message, Message):
        await callback.message.edit_text(f"❌ Оплата не найдена · {html.escape(views.client_name(user))}")
    client = await repo.get_user(session, payment.user_id)
    if payment.order_id:
        what = t(client.lang, "what_order", id=payment.order_id)
    else:
        what = t(client.lang, "what_package", plan=t(client.lang, f"plan_{payment.plan_code}"))
    await flows.n.client(client, "payment_not_found", what=what)


# --- готовые файлы вручную (без конвейера) --------------------------------------


@router.callback_query(MgrCb.filter(F.action == "files"))
async def on_files(callback: CallbackQuery, callback_data: MgrCb, state: FSMContext) -> None:
    await state.set_state(StaffForm.files)
    await state.update_data(order_id=callback_data.order_id, files=[])
    await callback.answer()
    if isinstance(callback.message, Message):
        await callback.message.answer(
            f"Пришлите файлы для #{callback_data.order_id} (PPTX, PDF…), потом нажмите «Готово».",
            reply_markup=kb.staff_files_done(callback_data.order_id),
        )


@router.message(StaffForm.files, F.document | F.photo)
async def on_file(message: Message, state: FSMContext) -> None:
    ref = file_of(message)
    assert ref is not None
    files = (await state.get_data())["files"]
    files.append({"name": ref.name, "file_id": ref.file_id})
    await state.update_data(files=files)
    await message.reply(f"Принято: {html.escape(ref.name)} · всего {len(files)}")


@router.callback_query(StaffForm.files, MgrCb.filter(F.action == "files_done"))
async def on_files_done(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, user: User, flows: Flows
) -> None:
    data = await state.get_data()
    if not data["files"]:
        await callback.answer("Сначала пришлите файлы", show_alert=True)
        return
    await callback.answer("Отправляю клиенту")
    await state.clear()
    order = await repo.get_order(session, data["order_id"])
    folder = flows.pipeline.dir(order.id) / f"sent_manual_{datetime.now():%m%d_%H%M%S}"
    folder.mkdir(parents=True)
    names = []
    for f in data["files"]:
        target = folder / f["name"]
        await flows.bot.download(f["file_id"], destination=target)
        names.append(target.name)
    await OrderService(session).deliver(
        order, user.id, deliver_dir=str(folder.relative_to(flows.pipeline.root)), files=names, links={}
    )
    await flows.sync(order)
    await session.commit()
    await flows.offer_formats(order, await owner_of(session, order))
    await flows.n.refresh_card(order, f"файлы отправлены клиенту ({len(names)})")
    await session.commit()


# --- отмена и возврат звёзд --------------------------------------------------------


@router.callback_query(MgrCb.filter(F.action.in_({"cancel", "refund"})))
async def on_cancel_ask(callback: CallbackQuery, callback_data: MgrCb) -> None:
    what = "Вернуть звёзды и отменить" if callback_data.action == "refund" else "Отменить"
    await callback.answer()
    if isinstance(callback.message, Message):
        await callback.message.answer(
            f"{what} заказ #{callback_data.order_id}?",
            reply_markup=kb.staff_confirm(callback_data.order_id, callback_data.action),
        )


@router.callback_query(MgrCb.filter(F.action == "noop"))
async def on_noop(callback: CallbackQuery) -> None:
    await callback.answer()
    if isinstance(callback.message, Message):
        await callback.message.delete()


@router.callback_query(MgrCb.filter(F.action == "cancel_yes"))
async def on_cancel(
    callback: CallbackQuery, callback_data: MgrCb, session: AsyncSession, user: User, flows: Flows
) -> None:
    order = await OrderService(session).transition(callback_data.order_id, OrderStatus.CANCELLED, actor_id=user.id)
    await flows.sync(order)
    await session.commit()
    await callback.answer("Отменён")
    if isinstance(callback.message, Message):
        await callback.message.delete()
    await flows.n.client(await owner_of(session, order), "order_cancelled", id=order.id)
    await flows.n.refresh_card(order, "отменён")


@router.callback_query(MgrCb.filter(F.action == "refund_yes"))
async def on_refund(
    callback: CallbackQuery, callback_data: MgrCb, session: AsyncSession, user: User, flows: Flows
) -> None:
    ok, text = await refund_stars(session, flows, callback_data.order_id, user.id)
    await callback.answer(text, show_alert=not ok)
    if ok and isinstance(callback.message, Message):
        await callback.message.delete()


async def refund_stars(session: AsyncSession, flows: Flows, order_id: int, actor_id: int) -> tuple[bool, str]:
    order = await repo.get_order(session, order_id)
    payment = await repo.latest_payment(session, order.id, PaymentStatus.PAID)
    if payment is None or payment.provider is not PaymentProvider.STARS or not payment.external_id:
        return False, f"По заказу #{order_id} нет оплаты звёздами"
    client = await owner_of(session, order)
    # сначала возврат в Telegram: если он не прошёл, в базе ничего не меняем
    await flows.bot.refund_star_payment(client.tg_id, payment.external_id)
    await PaymentService(session).mark_refunded(payment.id)
    if order.status not in (OrderStatus.CANCELLED, OrderStatus.DONE, OrderStatus.REVISION):
        await OrderService(session).transition(
            order.id, OrderStatus.CANCELLED, actor_id=actor_id, comment="возврат звёзд"
        )
    await flows.sync(order)
    await session.commit()
    await flows.n.client(client, "stars_refunded", amount=payment.amount, id=order.id)
    await flows.n.refresh_card(order, f"↩️ возвращено {payment.amount} ⭐, заказ отменён")
    return True, f"Вернул {payment.amount} ⭐"


@router.message(Command("refund"))
async def cmd_refund(message: Message, command: CommandObject, session: AsyncSession, user: User, flows: Flows) -> None:
    """/refund 12 — вернуть звёзды за заказ #12 и отменить его."""
    ref = (command.args or "").strip().lstrip("#")
    if not ref.isdigit():
        await message.answer("Формат: <code>/refund 12</code>")
        return
    try:
        _, text = await refund_stars(session, flows, int(ref), user.id)
    except DomainError as e:
        text = str(e)
    await message.answer(text)


# --- проверка работы Claude ---------------------------------------------------------


@router.callback_query(MgrCb.filter(F.action == "rv_send"))
async def on_review_send(
    callback: CallbackQuery, callback_data: MgrCb, session: AsyncSession, user: User, flows: Flows
) -> None:
    order = await repo.get_order(session, callback_data.order_id)
    if order.stage is None or not order.stage.value.endswith("_review"):
        await callback.answer("Уже обработано", show_alert=True)
        return
    kind = order.stage.value.removesuffix("_review")
    client = await owner_of(session, order)
    orders = OrderService(session)
    pipe = flows.pipeline
    files = pipe.review_files(order.id)
    # Порядок важен: если Telegram или база откажут, папка review/ останется на месте и можно нажать ещё раз
    if kind == "cover":
        await flows.send_cover(order, client, files)
        await orders.cover_sent(order, actor_id=user.id)
        await flows.sync(order)
        await session.commit()
        pipe.archive_review(order.id, kind)
        note = "обложка отправлена клиенту — ждём его ответа"
    else:
        links = pipe.review_links(order.id)
        folder = pipe.archive_target(order.id, kind)
        rel = str(folder.relative_to(pipe.root))
        names = [f.name for f in files]
        if order.status in (OrderStatus.WORK, OrderStatus.REVISION):
            await orders.deliver(order, user.id, deliver_dir=rel, files=names, links=links)
        else:
            order.deliver_dir, order.deliver_files, order.deliver_links = rel, names, links
        order.delivered = False  # новая версия — снова предложим правки
        await flows.sync(order)
        await session.commit()
        pipe.archive_review(order.id, kind, target=folder)
        await flows.offer_formats(order, client)
        note = f"{KIND_ACC[kind]} отправлена клиенту"
    await callback.answer("Отправлено клиенту")
    if isinstance(callback.message, Message):
        with suppress(TelegramBadRequest):  # кнопок уже нет — не мешаем остальному
            await callback.message.edit_reply_markup(reply_markup=None)
    await flows.n.refresh_card(order, note)
    await session.commit()


@router.callback_query(MgrCb.filter(F.action == "rv_fix"))
async def on_review_fix(callback: CallbackQuery, callback_data: MgrCb, state: FSMContext) -> None:
    await state.set_state(StaffForm.fix)
    await state.update_data(order_id=callback_data.order_id)
    if isinstance(callback.message, Message):
        with suppress(TelegramBadRequest):  # кнопок уже нет — не мешаем остальному
            await callback.message.edit_reply_markup(reply_markup=None)
    await _ask(callback, f"Доработка #{callback_data.order_id}: что исправить? Текстом, можно со скриншотом.")


@router.message(StaffForm.fix)
async def on_fix_text(message: Message, state: FSMContext, session: AsyncSession, flows: Flows) -> None:
    order_id = (await state.get_data())["order_id"]
    await state.clear()
    order = await repo.get_order(session, order_id)
    if order.stage is None or not order.stage.value.endswith("_review"):
        await message.reply("Этот заказ уже не на проверке.")
        return
    kind = order.stage.value.removesuffix("_review")
    flows.pipeline.add_note(order.id, "Владелец (доработать)", message.text or message.caption or "(см. файл)")
    ref = file_of(message)
    if ref is not None:
        await flows.save_materials(order.id, [Material(name=ref.name, file_id=ref.file_id)], sub="edits")
    flows.pipeline.archive_review(order.id, kind, rejected=True)
    OrderService(session).set_stage(order, TODO_OF[kind])
    await flows.sync(order)
    await session.commit()
    await message.reply(f"Записал. Claude переделает {KIND_ACC[kind]} #{order.id} и пришлёт снова.")


REVIEW_CAPTION = re.compile(r"^#(\d+) · ")


@router.message(
    F.text.contains("canva."),
    F.reply_to_message.func(lambda m: bool(REVIEW_CAPTION.match(m.caption or m.text or ""))),
)
async def on_canva_link(message: Message, session: AsyncSession, flows: Flows) -> None:
    """Ответ ссылкой Canva на сообщение с файлами заказа: «редактируемая копия» или «листать» (/view)."""
    src = message.reply_to_message
    assert src is not None
    found = ORDER_RE.search(src.caption or src.text or "")
    url_match = URL_RE.search(message.text or "")
    if not found or not url_match:
        return
    order = await repo.get_order(session, int(found.group(1)))
    url = url_match.group(0).rstrip(").,;")
    key = "view" if re.search(r"/view(\?|$|/)", url) else "canva"
    if order.stage and order.stage.value.endswith("_review"):
        flows.pipeline.set_review_link(order.id, key, url)
        await message.reply(
            f"Ссылку {'для просмотра' if key == 'view' else 'Canva'} добавил к #{order.id} — уйдёт вместе с файлами."
        )
        return
    if not order.deliver_dir:
        await message.reply(f"#{order.id}: сначала отправьте клиенту файлы — ссылку добавлю к ним.")
        return
    order.deliver_links = {**(order.deliver_links or {}), key: url}
    await session.commit()
    if key == "view":
        await message.reply(f"Ссылку для просмотра добавил к #{order.id}.")
    else:
        await message.reply(f"Ссылку Canva добавил к #{order.id}.", reply_markup=kb.staff_send_canva(order.id))


@router.callback_query(MgrCb.filter(F.action == "send_canva"))
async def on_send_canva(callback: CallbackQuery, callback_data: MgrCb, session: AsyncSession, flows: Flows) -> None:
    order = await repo.get_order(session, callback_data.order_id)
    ok = await flows.deliver(order, await owner_of(session, order), "canva")
    await session.commit()
    await callback.answer("Отправлено" if ok else "Нет ссылки", show_alert=not ok)


# --- сторож ------------------------------------------------------------------------


@router.callback_query(MgrCb.filter(F.action.startswith("stk_")))
async def on_stuck(callback: CallbackQuery, callback_data: MgrCb, session: AsyncSession, flows: Flows) -> None:
    order = await repo.get_order(session, callback_data.order_id)
    action = callback_data.action[4:]
    if isinstance(callback.message, Message):
        with suppress(TelegramBadRequest):  # кнопок уже нет — не мешаем остальному
            await callback.message.edit_reply_markup(reply_markup=None)
    if action == "mute":
        order.no_alert = True
        await session.commit()
        await callback.answer("Больше не напоминаю об этом заказе")
        return
    stage = order.stage if action == "redo" else {"cover": Stage.COVER_TODO, "deck": Stage.DECK_TODO}[action]
    if stage not in TODO:
        await callback.answer("Заказ уже в другом статусе", show_alert=True)
        return
    if not (flows.pipeline.dir(order.id) / "brief.json").exists():
        flows.pipeline.write_brief(order, views.client_name(await owner_of(session, order)))
    flows.pipeline.reset_attempt(order.id)
    flows.pipeline.add_note(order.id, "Владелец (доработать)", "Предыдущая попытка не получилась — сделай заново.")
    OrderService(session).set_stage(order, stage)
    await flows.sync(order)
    await session.commit()
    await callback.answer()
    if isinstance(callback.message, Message):
        await callback.message.reply(
            f"#{order.id} снова в работе ({KIND_ACC[TODO[stage]]}). Claude возьмёт его в ближайший запуск."
        )


# --- ручная смена статуса -------------------------------------------------------------


@router.callback_query(MgrCb.filter(F.action.in_({"st_work", "st_done", "st_edit"})))
async def on_set_status(
    callback: CallbackQuery, callback_data: MgrCb, session: AsyncSession, user: User, flows: Flows
) -> None:
    """Как кнопки статусов прежнего бота: клиент получает уведомление, «Готово» — ещё и правки с зачётом."""
    orders = OrderService(session)
    order = await repo.get_order(session, callback_data.order_id, for_update=True)
    client = await owner_of(session, order)
    try:
        if callback_data.action == "st_work":
            await orders.transition(order.id, OrderStatus.WORK, actor_id=user.id, comment="вручную")
            note = "в работе — Claude делает презентацию"
        elif callback_data.action == "st_done":
            await orders.deliver(order, user.id)
            note = "готово (вручную)"
        else:
            await orders.transition(order.id, OrderStatus.REVISION, actor_id=user.id, comment="правки вручную")
            orders.set_stage(order, Stage.EDIT_TODO)
            note = "правки — Claude вносит изменения"
    except DomainError as e:
        await callback.answer(str(e), show_alert=True)
        return
    await flows.sync(order)
    await session.commit()
    await callback.answer(note)
    await flows.notify_status(order, client)
    if order.status is OrderStatus.DONE:
        await flows.n.client(client, "after_delivery", kb.after_delivery(lang_of(client), order.id))
        await flows.offer_credit(order, client)
    await flows.n.refresh_card(order, note)
    await session.commit()


# --- статистика, пакеты ---------------------------------------------------------------
