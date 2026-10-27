"""Рабочее место владельца и менеджеров.

Работает в личке владельца с ботом (как раньше) или в супергруппе менеджеров с темами.
Ответ реплаем на сообщение со строкой «ID: …» уходит клиенту.
"""

import html
import re
from datetime import datetime, timedelta

from aiogram import F, Router
from aiogram.filters import BaseFilter, Command, CommandObject, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, ForceReply, Message
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from slidelab.bot.utils import file_of
from slidelab.config import Settings
from slidelab.core import repositories as repo
from slidelab.core.enums import (
    AttachmentKind,
    LedgerReason,
    MessageDirection,
    OrderStatus,
    PaymentProvider,
    PaymentStatus,
    PlanCode,
    Stage,
)
from slidelab.core.errors import DomainError
from slidelab.core.i18n import money, t
from slidelab.core.models import Attachment, Order, OrderEvent, Payment, SupportMessage, User, UserPackage
from slidelab.core.models.base import utcnow
from slidelab.core.services.orders import OrderService
from slidelab.core.services.packages import PackageService
from slidelab.core.services.payments import PaymentService
from slidelab.core.services.pipeline import KIND_ACC, TODO, TODO_OF
from slidelab.telegram import keyboards as kb
from slidelab.telegram import views
from slidelab.telegram.callbacks import MgrCb
from slidelab.telegram.flows import Flows, Material
from slidelab.telegram.states import StaffForm

ID_RE = re.compile(r"ID:?\s*(\d+)")
ORDER_RE = re.compile(r"#(\d+)")
URL_RE = re.compile(r"https://\S+")


class FromStaff(BaseFilter):
    """Апдейт из чата команды (личка владельца или группа менеджеров) от человека из команды."""

    async def __call__(self, event: Message | CallbackQuery, settings: Settings, is_manager: bool = False) -> bool:
        message = event if isinstance(event, Message) else event.message
        return bool(is_manager and message is not None and message.chat.id == settings.staff_chat_id)


router = Router(name="staff")
router.message.filter(FromStaff())
router.callback_query.filter(FromStaff())


async def _ask(callback: CallbackQuery, text: str) -> None:
    await callback.answer()
    if isinstance(callback.message, Message):
        await callback.message.answer(text, reply_markup=ForceReply(selective=True))


async def owner_of(session: AsyncSession, order: Order) -> User:
    return await repo.get_user(session, order.user_id)


# --- обложка вручную ------------------------------------------------------------


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
    if kind == "cover":
        await flows.send_cover(order, client, files)
        await orders.cover_sent(order, actor_id=user.id)
        pipe.archive_review(order.id, kind)
        note = "обложка отправлена клиенту — ждём его ответа"
    else:
        links = pipe.review_links(order.id)  # ссылки читаем до переноса папки
        folder = pipe.archive_review(order.id, kind)
        rel = str(folder.relative_to(pipe.root))
        names = [f.name for f in files]
        if order.status in (OrderStatus.WORK, OrderStatus.REVISION):
            await orders.deliver(order, user.id, deliver_dir=rel, files=names, links=links)
        else:
            order.deliver_dir, order.deliver_files, order.deliver_links = rel, names, links
        order.delivered = False  # новая версия — снова предложим правки
        await flows.offer_formats(order, client)
        note = f"{KIND_ACC[kind]} отправлена клиенту"
    await flows.sync(order)
    await session.commit()
    await callback.answer("Отправлено клиенту")
    if isinstance(callback.message, Message):
        await callback.message.edit_reply_markup(reply_markup=None)
    await flows.n.refresh_card(order, note)
    await session.commit()


@router.callback_query(MgrCb.filter(F.action == "rv_fix"))
async def on_review_fix(callback: CallbackQuery, callback_data: MgrCb, state: FSMContext) -> None:
    await state.set_state(StaffForm.fix)
    await state.update_data(order_id=callback_data.order_id)
    if isinstance(callback.message, Message):
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


@router.message(F.reply_to_message, F.text.contains("canva."))
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


# --- статистика, пакеты ---------------------------------------------------------------


@router.message(Command("stats"))
async def cmd_stats(message: Message, session: AsyncSession) -> None:
    now = utcnow()
    lines = ["<b>Статистика</b>"]
    for days in (7, 30):
        since = now - timedelta(days=days)
        created = await session.scalar(select(func.count(Order.id)).where(Order.created_at >= since)) or 0
        covers = await _reached(session, OrderStatus.COVER, since)
        started = await _reached(session, OrderStatus.WORK, since)
        uzs = await _revenue(session, since, "UZS")
        stars = await _revenue(session, since, "XTR")
        conversion = f"{started * 100 // covers}%" if covers else "—"
        lines.append(
            f"\n<b>{days} дней</b>\nЗаказов: {created}\n"
            f"Обложек: {covers} → в работу: {started} ({conversion})\n"
            f"Выручка: {money(uzs)} сум + {stars} ⭐"
        )
    await message.answer("\n".join(lines))


async def _reached(session: AsyncSession, status: OrderStatus, since: datetime) -> int:
    stmt = select(func.count(func.distinct(OrderEvent.order_id))).where(
        OrderEvent.to_status == status, OrderEvent.created_at >= since
    )
    return int(await session.scalar(stmt) or 0)


async def _revenue(session: AsyncSession, since: datetime, currency: str) -> int:
    stmt = select(func.coalesce(func.sum(Payment.amount), 0)).where(
        Payment.status == PaymentStatus.PAID, Payment.currency == currency, Payment.created_at >= since
    )
    return int(await session.scalar(stmt) or 0)


@router.message(Command("subs"))
async def cmd_subs(message: Message, session: AsyncSession) -> None:
    rows = (
        await session.execute(
            select(UserPackage, User)
            .join(User, User.id == UserPackage.user_id)
            .where(UserPackage.expires_at > utcnow(), UserPackage.left > 0)
            .order_by(UserPackage.expires_at)
        )
    ).all()
    lines = [
        f"• {html.escape(views.client_name(u))} <code>{u.tg_id}</code> — {t(None, 'plan_' + p.plan_code.value)}, "
        f"осталось {p.left}/{p.total}, до {views.date_short(p.expires_at)}"
        for p, u in rows
    ]
    await message.answer("<b>Активные пакеты</b>\n" + ("\n".join(lines) if lines else "пока нет"))


@router.message(Command("grant"))
async def cmd_grant(message: Message, command: CommandObject, session: AsyncSession, flows: Flows) -> None:
    """/grant <Telegram ID> <week|month|vip> — выдать пакет без оплаты."""
    parts = (command.args or "").split()
    if len(parts) != 2 or not parts[0].isdigit() or parts[1] not in PlanCode._value2member_map_:
        await message.answer("Формат: <code>/grant 123456789 month</code>")
        return
    client = await repo.get_user_by_tg(session, int(parts[0]))
    if client is None:
        await message.answer("Клиент ещё не писал боту — пусть нажмёт /start.")
        return
    package = await PackageService(session).activate(client.id, PlanCode(parts[1]), LedgerReason.GRANT)
    await session.commit()
    name = t(client.lang, "plan_" + package.plan_code.value)
    await flows.n.client(
        client,
        "pkg_on",
        await flows.n.menu(client),
        plan=name,
        left=package.left,
        date=views.date_short(package.expires_at),
    )
    await message.answer(f"Выдан пакет «{t(None, 'plan_' + package.plan_code.value)}» · осталось {package.left}")


# --- ответ клиенту ---------------------------------------------------------------------


def _reply_target(message: Message) -> int | None:
    src = message.reply_to_message
    if src is None or src.from_user is None or not src.from_user.is_bot:
        return None
    found = ID_RE.search(src.text or src.caption or "")
    return int(found.group(1)) if found else None


@router.message(StateFilter(None), F.func(lambda m: _reply_target(m) is not None))
async def on_reply(message: Message, session: AsyncSession, flows: Flows) -> None:
    """Реплай на сообщение с «ID: …» — клиенту. Ссылка или файл в ответ на заказ сохраняются в его «Моих работах»."""
    tg_id = _reply_target(message)
    assert tg_id is not None
    client = await repo.get_user_by_tg(session, tg_id)
    if client is None:
        await message.reply("Клиент не найден.")
        return
    await send_to_client(message, client, session, flows)
    src_text = (
        message.reply_to_message.text or message.reply_to_message.caption or "" if message.reply_to_message else ""
    )
    note = await _remember_result(session, client, src_text, message)
    await session.commit()
    await message.reply("Отправил клиенту" + note)


@router.message(StateFilter(None), F.message_thread_id, F.chat.type == "supergroup", ~F.text.startswith("/"))
async def on_topic_reply(message: Message, session: AsyncSession, flows: Flows) -> None:
    """В группе менеджеров любое сообщение в теме клиента уходит клиенту."""
    assert message.message_thread_id is not None
    client = await repo.get_user_by_topic(session, message.message_thread_id)
    if client is not None:
        await send_to_client(message, client, session, flows)
        await session.commit()


async def send_to_client(message: Message, client: User, session: AsyncSession, flows: Flows) -> None:
    await flows.n.client(client, "manager_reply")
    await message.copy_to(client.tg_id)
    text = message.text or message.caption
    if text:
        session.add(SupportMessage(user_id=client.id, direction=MessageDirection.OUT, text=text))


async def _remember_result(session: AsyncSession, client: User, src_text: str, message: Message) -> str:
    """Админ ответил ссылкой на готовую презентацию на сообщение заказа — запомним её у клиента."""
    found = ORDER_RE.search(src_text)
    link = URL_RE.search(message.text or message.caption or "")
    if not found or not link:
        return ""
    order = await session.get(Order, int(found.group(1)))
    if order is None or order.user_id != client.id:
        return ""
    order.result_link = link.group(0).rstrip(").,;")
    return f"\nСохранил ссылку в «Моих заказах» клиента (#{order.id})"
