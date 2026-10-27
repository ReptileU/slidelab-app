"""Заказ в чате: тема → объём → срок → язык → дизайн → дополнительно → материалы → проверка.

Вопросы с кнопками редактируют одно и то же сообщение — чат не засоряется.
Плюс быстрый заказ: клиент пересылает файл — объём, срок, готово.
"""

import html
from typing import Any

from aiogram import F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message, ReplyKeyboardRemove
from sqlalchemy.ext.asyncio import AsyncSession

from slidelab.bot.utils import file_of
from slidelab.core import repositories as repo
from slidelab.core.enums import Deadline, Design, Lang, OrderSource, PaidFrom, SlideTier
from slidelab.core.i18n import money, t
from slidelab.core.models import User
from slidelab.core.models.order import CONTACT_MAX, TEMPLATE_URL_MAX, TOPIC_MAX
from slidelab.core.schemas.order import OrderDraft
from slidelab.core.services import pricing
from slidelab.core.services.orders import OrderService
from slidelab.telegram import keyboards as kb
from slidelab.telegram.callbacks import FormCb, QuickCb
from slidelab.telegram.flows import Flows, Material
from slidelab.telegram.notifier import lang_of
from slidelab.telegram.states import OrderForm, QuickForm

router = Router(name="order")
router.message.filter(F.chat.type == "private")

TOTAL_STEPS = 7


def step(user: User, n: int, key: str) -> str:
    return f"{t(user.lang, 'step', n=n, total=TOTAL_STEPS)}\n{t(user.lang, key)}"


async def begin(message: Message, state: FSMContext, user: User) -> None:
    await state.clear()
    await state.set_state(OrderForm.topic)
    await state.update_data(materials=[])
    await message.answer(step(user, 1, "ask_topic"), reply_markup=ReplyKeyboardRemove())


@router.message(Command("new", "order"))
@router.message(F.text.in_(kb.menu_texts("btn_new")))
async def cmd_new(message: Message, state: FSMContext, user: User) -> None:
    await begin(message, state, user)


@router.callback_query(FormCb.filter((F.field == "action") & (F.value == "start")))
async def on_start(callback: CallbackQuery, state: FSMContext, user: User) -> None:
    await callback.answer()
    if isinstance(callback.message, Message):
        await begin(callback.message, state, user)


@router.callback_query(StateFilter(OrderForm), FormCb.filter((F.field == "action") & (F.value == "cancel")))
async def on_cancel(callback: CallbackQuery, state: FSMContext, user: User, flows: Flows) -> None:
    await state.clear()
    await callback.answer()
    if isinstance(callback.message, Message):
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer(t(user.lang, "cancelled"), reply_markup=await flows.n.menu(user))


# --- 1. тема ------------------------------------------------------------------


@router.message(OrderForm.topic, F.text)
async def on_topic(message: Message, state: FSMContext, session: AsyncSession, user: User) -> None:
    topic = (message.text or "").strip()
    if len(topic) < 3:
        await message.answer(t(user.lang, "topic_short"))
        return
    if len(topic) > TOPIC_MAX:
        await message.answer(t(user.lang, "topic_long"))
        return
    await state.update_data(topic=topic)
    await state.set_state(OrderForm.slides)
    prices = await tier_prices(session, user)
    await message.answer(step(user, 2, "ask_slides"), reply_markup=kb.slides(lang_of(user), prices))


@router.message(OrderForm.topic)
async def on_topic_not_text(message: Message, user: User) -> None:
    await message.answer(t(user.lang, "send_text"))


async def tier_prices(session: AsyncSession, user: User) -> dict[SlideTier, int]:
    """Цена каждого объёма для этого клиента (учитывает скидку на первый заказ)."""
    rules = await repo.get_price_rules(session)
    first = not await repo.has_orders(session, user.id)
    req = pricing.QuoteRequest
    return {s: pricing.quote(req(s, Deadline.NORMAL), rules, first_order=first).price for s in SlideTier}


# --- 2–5. кнопки ----------------------------------------------------------------


@router.callback_query(OrderForm.slides, FormCb.filter(F.field == "slides"))
async def on_slides(callback: CallbackQuery, callback_data: FormCb, state: FSMContext, user: User) -> None:
    tier = SlideTier(callback_data.value)
    await state.update_data(slides=tier.value)
    await state.set_state(OrderForm.deadline)
    await edit(callback, step(user, 3, "ask_deadline"), kb.deadlines(lang_of(user), tier))


@router.callback_query(OrderForm.deadline, FormCb.filter(F.field == "deadline"))
async def on_deadline(callback: CallbackQuery, callback_data: FormCb, state: FSMContext, user: User) -> None:
    await state.update_data(deadline=Deadline(callback_data.value).value)
    await state.set_state(OrderForm.plang)
    await edit(callback, step(user, 4, "ask_plang"), kb.pres_langs(lang_of(user)))


@router.callback_query(OrderForm.plang, FormCb.filter(F.field == "plang"))
async def on_plang(callback: CallbackQuery, callback_data: FormCb, state: FSMContext, user: User) -> None:
    await state.update_data(pres_lang=Lang(callback_data.value).value)
    await state.set_state(OrderForm.design)
    await edit(callback, step(user, 5, "ask_design"), kb.designs(lang_of(user)))


@router.callback_query(OrderForm.design, FormCb.filter(F.field == "design"))
async def on_design(callback: CallbackQuery, callback_data: FormCb, state: FSMContext, user: User) -> None:
    design = Design(callback_data.value)
    await state.update_data(design=design.value)
    if design is Design.OWN:
        await state.set_state(OrderForm.template)
        await edit(callback, step(user, 5, "ask_template"), kb.template_later(lang_of(user)))
        return
    await to_extras(callback, state, user)


@router.message(OrderForm.template, F.text)
async def on_template_link(message: Message, state: FSMContext, user: User) -> None:
    url = (message.text or "").strip()
    if "." not in url or " " in url or len(url) > TEMPLATE_URL_MAX:
        await message.answer(t(user.lang, "ask_template"), reply_markup=kb.template_later(lang_of(user)))
        return
    await state.update_data(template_url=url)
    await state.set_state(OrderForm.extras)
    await message.answer(step(user, 6, "ask_extras"), reply_markup=kb.extras(lang_of(user), False, False, False))


@router.message(OrderForm.template, F.document | F.photo)
async def on_template_file(message: Message, state: FSMContext, user: User) -> None:
    await add_material(message, state)
    await state.set_state(OrderForm.extras)
    await message.answer(step(user, 6, "ask_extras"), reply_markup=kb.extras(lang_of(user), False, False, False))


@router.callback_query(OrderForm.template, FormCb.filter((F.field == "action") & (F.value == "no_template")))
async def on_template_later(callback: CallbackQuery, state: FSMContext, user: User) -> None:
    await to_extras(callback, state, user)


async def to_extras(callback: CallbackQuery, state: FSMContext, user: User) -> None:
    await state.set_state(OrderForm.extras)
    await edit(callback, step(user, 6, "ask_extras"), kb.extras(lang_of(user), False, False, False))


# --- 6. дополнительно -----------------------------------------------------------


@router.callback_query(OrderForm.extras, FormCb.filter(F.field == "extra"))
async def on_extra(callback: CallbackQuery, callback_data: FormCb, state: FSMContext, user: User) -> None:
    data = await state.get_data()
    flags = {k: bool(data.get(k)) for k in ("extra_text", "extra_notes", "need_humor")}
    if callback_data.value == "next":
        await state.set_state(OrderForm.files)
        has_files = len(data.get("materials", [])) > 0
        await edit(callback, step(user, 7, "ask_files"), kb.materials(lang_of(user), has_files))
        return
    key = {"text": "extra_text", "notes": "extra_notes", "humor": "need_humor"}[callback_data.value]
    flags[key] = not flags[key]
    await state.update_data(flags)
    await callback.answer()
    if isinstance(callback.message, Message):
        markup = kb.extras(lang_of(user), flags["extra_text"], flags["extra_notes"], flags["need_humor"])
        await callback.message.edit_reply_markup(reply_markup=markup)


# --- 7. материалы и контакт -----------------------------------------------------


@router.message(OrderForm.files)
async def on_material(message: Message, state: FSMContext, user: User) -> None:
    n = await add_material(message, state)
    await message.answer(t(user.lang, "files_got", n=n), reply_markup=kb.materials(lang_of(user), True))


@router.callback_query(OrderForm.files, FormCb.filter(F.field == "files"))
async def on_files_done(callback: CallbackQuery, state: FSMContext, session: AsyncSession, user: User) -> None:
    await callback.answer()
    if not isinstance(callback.message, Message):
        return
    await callback.message.edit_reply_markup(reply_markup=None)
    if user.username:
        await state.update_data(contact=f"@{user.username}")
        await summary(callback.message, state, session, user)
        return
    await state.set_state(OrderForm.contact)
    await callback.message.answer(t(user.lang, "ask_contact"), reply_markup=kb.contact_request(lang_of(user)))


@router.message(OrderForm.contact, F.contact | F.text)
async def on_contact(message: Message, state: FSMContext, session: AsyncSession, user: User) -> None:
    contact = message.contact.phone_number if message.contact else (message.text or "").strip()
    await state.update_data(contact=contact[:CONTACT_MAX])
    if message.contact:
        user.phone = message.contact.phone_number
    await summary(message, state, session, user)


async def add_material(message: Message, state: FSMContext) -> int:
    ref = file_of(message)
    data = await state.get_data()
    materials: list[dict[str, Any]] = data.get("materials", [])
    if ref is not None:
        materials.append({"name": ref.name, "file_id": ref.file_id})
    elif message.text:
        materials.append({"name": "text", "text": message.text[:4000]})
    await state.update_data(materials=materials)
    return len(materials)


# --- проверка и отправка --------------------------------------------------------


async def summary(message: Message, state: FSMContext, session: AsyncSession, user: User) -> None:
    data = await state.get_data()
    draft = make_draft(data)
    q = await OrderService(session).quote(user.id, draft.quote_request())
    lang = user.lang
    if q.paid_from is PaidFrom.PACKAGE:
        key = "price_package_extra" if q.price else "price_package"
        price = t(lang, key, cost=q.package_cost, left=q.package_left_after, price=money(q.price))
    else:
        price = t(lang, "price_cash", price=money(q.price))
        if q.first_order_discount:
            price = price.replace("</b>", "</b>" + t(lang, "price_first"), 1)
    flags = (("text_label", draft.extra_text), ("notes_label", draft.extra_notes), ("humor_label", draft.need_humor))
    extras = [t(lang, label) for label, on in flags if on]
    n = len(data.get("materials", []))
    text = t(
        lang,
        "summary",
        topic=f"<b>{html.escape(draft.topic)}</b>",
        slides=t(lang, "slides_" + draft.slides.value),
        deadline=t(lang, "dl_" + draft.deadline.value),
        plang=t(lang, "plang_" + draft.pres_lang.value),
        design=t(lang, "ds_" + draft.design.value),
        extras=(" · " + ", ".join(extras)) if extras else "",
        files=t(lang, "summary_files", n=n) if n else "",
        price=price,
    )
    await state.set_state(OrderForm.confirm)
    await message.answer(text, reply_markup=kb.confirm(lang_of(user)))


@router.callback_query(OrderForm.confirm, FormCb.filter((F.field == "action") & (F.value == "send")))
async def on_send(callback: CallbackQuery, state: FSMContext, session: AsyncSession, user: User, flows: Flows) -> None:
    data = await state.get_data()
    # ключ — сообщение со сводкой: повторное нажатие не создаст второй заказ
    key = f"chat:{user.tg_id}:{callback.message.message_id}" if callback.message else None
    order = await OrderService(session).create(
        user.id, make_draft(data), idempotency_key=key, source=OrderSource.CHAT, ui_lang=lang_of(user)
    )
    await state.clear()
    await session.commit()
    await callback.answer()
    if isinstance(callback.message, Message):
        await callback.message.edit_reply_markup(reply_markup=None)
    await flows.order_created(order, user, [Material(**m) for m in data.get("materials", [])])
    await session.commit()


def make_draft(data: dict[str, Any]) -> OrderDraft:
    return OrderDraft(
        topic=data["topic"],
        slides=data["slides"],
        deadline=data["deadline"],
        pres_lang=data["pres_lang"],
        design=data["design"],
        template_url=data.get("template_url"),
        extra_text=bool(data.get("extra_text")),
        extra_notes=bool(data.get("extra_notes")),
        need_humor=bool(data.get("need_humor")),
        contact=data.get("contact"),
        has_source_files=bool(data.get("materials")),
    )


@router.message(
    StateFilter(
        OrderForm.slides, OrderForm.deadline, OrderForm.plang, OrderForm.design, OrderForm.extras, OrderForm.confirm
    )
)
async def use_buttons(message: Message, user: User) -> None:
    await message.answer(t(user.lang, "use_buttons"))


async def edit(callback: CallbackQuery, text: str, markup: InlineKeyboardMarkup) -> None:
    await callback.answer()
    if isinstance(callback.message, Message):
        await callback.message.edit_text(text, reply_markup=markup)


# --- быстрый заказ по пересланному файлу ---------------------------------------


async def begin_quick(message: Message, state: FSMContext, session: AsyncSession, user: User) -> None:
    ref = file_of(message)
    assert ref is not None
    await state.clear()
    await state.set_state(QuickForm.choosing)
    await state.update_data(
        topic=t(user.lang, "quick_topic", name=ref.name)[:TOPIC_MAX],
        materials=[{"name": ref.name, "file_id": ref.file_id}],
    )
    prices = await tier_prices(session, user)
    await message.answer(t(user.lang, "quick_ask"), reply_markup=kb.slides(lang_of(user), prices, QuickCb))


@router.message(QuickForm.choosing, F.document | F.photo | F.video | F.audio | F.voice)
async def on_quick_more(message: Message, state: FSMContext, user: User) -> None:
    n = await add_material(message, state)
    await message.answer(t(user.lang, "quick_more", n=n))


@router.callback_query(QuickForm.choosing, QuickCb.filter(F.field == "slides"))
async def on_quick_slides(callback: CallbackQuery, callback_data: QuickCb, state: FSMContext, user: User) -> None:
    tier = SlideTier(callback_data.value)
    await state.update_data(slides=tier.value)
    await edit(callback, t(user.lang, "quick_deadline"), kb.deadlines(lang_of(user), tier, QuickCb))


@router.callback_query(QuickForm.choosing, QuickCb.filter(F.field == "deadline"))
async def on_quick_deadline(
    callback: CallbackQuery,
    callback_data: QuickCb,
    state: FSMContext,
    session: AsyncSession,
    user: User,
    flows: Flows,
) -> None:
    data = await state.get_data()
    if not data.get("slides"):
        await callback.answer()
        return
    lang = lang_of(user)
    draft = OrderDraft(
        topic=data["topic"],
        slides=data["slides"],
        deadline=Deadline(callback_data.value),
        pres_lang=lang,
        design=Design.OURS,
        contact=f"@{user.username}" if user.username else None,
        has_source_files=True,
    )
    key = f"quick:{user.tg_id}:{callback.message.message_id}" if callback.message else None
    order = await OrderService(session).create(
        user.id, draft, idempotency_key=key, source=OrderSource.FILE, ui_lang=lang
    )
    await state.clear()
    await session.commit()
    await callback.answer()
    if isinstance(callback.message, Message):
        await callback.message.edit_reply_markup(reply_markup=None)
    await flows.order_created(order, user, [Material(**m) for m in data.get("materials", [])])
    await session.commit()


@router.message(QuickForm.choosing)
async def quick_use_buttons(message: Message, user: User) -> None:
    await message.answer(t(user.lang, "use_buttons"))
