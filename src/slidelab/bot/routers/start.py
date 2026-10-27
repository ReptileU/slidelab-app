"""Вход и меню: /start с deep-link, язык, цены, пакеты, примеры, вопросы."""

import html
import logging

from aiogram import F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile, InlineKeyboardMarkup, InputMediaPhoto, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from slidelab.bot.routers import legacy as legacy_router
from slidelab.bot.routers import order as order_flow
from slidelab.bot.routers import orders as my_orders
from slidelab.core import repositories as repo
from slidelab.core.enums import Lang, PlanCode
from slidelab.core.i18n import DEFAULT, t
from slidelab.core.models import FaqItem, PackagePlan, User
from slidelab.core.models.base import utcnow
from slidelab.telegram import keyboards as kb
from slidelab.telegram import legacy, views
from slidelab.telegram.callbacks import FormCb, LangCb, PlanCb
from slidelab.telegram.flows import Flows
from slidelab.telegram.notifier import Notifier, lang_of
from slidelab.telegram.states import AskForm

log = logging.getLogger(__name__)
router = Router(name="start")
router.message.filter(F.chat.type == "private")

IMAGE_EXT = (".jpg", ".jpeg", ".png", ".webp")


@router.message(CommandStart())
async def cmd_start(
    message: Message, command: CommandObject, state: FSMContext, session: AsyncSession, user: User, flows: Flows
) -> None:
    await state.clear()
    payload = command.args or ""

    action = legacy.parse_start_payload(payload)
    if isinstance(action, legacy.LegacyOrder):
        user.lang = user.lang or action.ui_lang
    if action is not None:
        await legacy_router.handle(action, message, session, user, flows)
        return
    if user.lang is None:
        await state.update_data(after_lang=payload)
        await message.answer(t(None, "lang_pick"), reply_markup=kb.languages())
        return
    await route(payload, message, state, session, user, flows)


async def route(
    payload: str, message: Message, state: FSMContext, session: AsyncSession, user: User, flows: Flows
) -> None:
    """Deep-link: order, sub_<тариф>, edit_<номер>, ask — или просто приветствие."""
    if payload == "order":
        await order_flow.begin(message, state, user)
    elif payload.startswith("sub_") and payload[4:] in PlanCode._value2member_map_:
        await flows.plan_payment(user, PlanCode(payload[4:]))
    elif payload.startswith("edit_") and payload[5:].isdigit():
        await my_orders.ask_revision(message, state, session, user, int(payload[5:]))
    elif payload == "ask":
        await begin_ask(message, state, user)
    else:
        await greet(message, user, flows.n)


async def greet(message: Message, user: User, notifier: Notifier, *, back: bool = False) -> None:
    await message.answer(t(user.lang, "welcome_back" if back else "welcome"), reply_markup=await notifier.menu(user))


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext, user: User, notifier: Notifier) -> None:
    await state.clear()
    await message.answer(t(user.lang, "cancelled"), reply_markup=await notifier.menu(user))


@router.message(Command("id"))
async def cmd_id(message: Message) -> None:
    assert message.from_user is not None
    await message.answer(f"Ваш Telegram ID: <code>{message.from_user.id}</code>")


# --- язык ---------------------------------------------------------------------


@router.message(Command("language"))
async def cmd_language(message: Message) -> None:
    await message.answer(t(None, "lang_pick"), reply_markup=kb.languages())


@router.callback_query(FormCb.filter((F.field == "action") & (F.value == "language")))
async def on_language_menu(callback: CallbackQuery) -> None:
    await callback.answer()
    if isinstance(callback.message, Message):
        await callback.message.answer(t(None, "lang_pick"), reply_markup=kb.languages())


@router.callback_query(LangCb.filter())
async def on_language(
    callback: CallbackQuery,
    callback_data: LangCb,
    state: FSMContext,
    session: AsyncSession,
    user: User,
    flows: Flows,
) -> None:
    user.lang = Lang(callback_data.code)
    await session.flush()
    await callback.answer(t(user.lang, "lang_name"))
    if isinstance(callback.message, Message):
        await callback.message.delete()
        payload = (await state.get_data()).get("after_lang", "")
        await state.clear()
        await route(payload, callback.message, state, session, user, flows)


# --- цены и пакеты ------------------------------------------------------------


@router.message(Command("prices"))
@router.message(F.text.in_(kb.menu_texts("btn_prices")))
async def show_prices(message: Message, session: AsyncSession, user: User) -> None:
    rule = await repo.get_price_rule_row(session)
    await message.answer(views.prices(user.lang, rule), reply_markup=kb.prices(lang_of(user)))


@router.message(Command("packages"))
async def cmd_packages(message: Message, session: AsyncSession, user: User, flows: Flows) -> None:
    text, markup = await packages_view(session, user, flows)
    await message.answer(text, reply_markup=markup)


@router.callback_query(PlanCb.filter(F.code == "list"))
async def on_packages(callback: CallbackQuery, session: AsyncSession, user: User, flows: Flows) -> None:
    await callback.answer()
    if isinstance(callback.message, Message):
        text, markup = await packages_view(session, user, flows)
        await callback.message.answer(text, reply_markup=markup)


async def packages_view(session: AsyncSession, user: User, flows: Flows) -> tuple[str, InlineKeyboardMarkup]:
    plans = list(
        (await session.scalars(select(PackagePlan).where(PackagePlan.is_active).order_by(PackagePlan.sort))).all()
    )
    current = await repo.get_active_package(session, user.id, utcnow())
    gift = flows.settings.gift_until.strftime("%d.%m") if utcnow().date() <= flows.settings.gift_until else None
    return views.packages(user.lang, plans, current, gift), kb.plans(lang_of(user), [(p.code, p.price) for p in plans])


@router.callback_query(PlanCb.filter(F.code != "list"))
async def on_plan(callback: CallbackQuery, callback_data: PlanCb, user: User, flows: Flows) -> None:
    ok = await flows.plan_payment(user, PlanCode(callback_data.code), callback_data.credit)
    await callback.answer(None if ok else t(user.lang, "credit_expired"), show_alert=not ok)


# --- примеры --------------------------------------------------------------------


@router.message(F.text.in_(kb.menu_texts("btn_examples")))
async def show_examples(message: Message, user: User, flows: Flows) -> None:
    folder = flows.settings.content_dir / "portfolio"
    images = sorted(p for p in folder.iterdir() if p.suffix.lower() in IMAGE_EXT)[:10] if folder.is_dir() else []
    if images:
        media = [InputMediaPhoto(media=FSInputFile(p)) for p in images]
        media[0].caption = t(user.lang, "examples")
        try:
            await message.answer_media_group(media)  # type: ignore[arg-type]
        except Exception as e:
            log.warning("Портфолио не отправилось: %s", e)
            images = []
    channel = flows.settings.channel
    if channel:
        await message.answer(t(user.lang, "examples_channel", channel=channel))
    elif not images:
        await message.answer(t(user.lang, "examples_soon"))


# --- вопросы --------------------------------------------------------------------


@router.message(Command("help"))
@router.message(F.text.in_(kb.menu_texts("btn_help")))
async def show_help(message: Message, session: AsyncSession, user: User) -> None:
    lang = (user.lang or DEFAULT).value
    items = (await session.scalars(select(FaqItem).where(FaqItem.is_active).order_by(FaqItem.sort))).all()
    blocks = [t(user.lang, "help")]
    for item in items:
        qa = item.texts.get(lang) or item.texts[DEFAULT.value]
        blocks.append(f"<b>{html.escape(qa['q'])}</b>\n{html.escape(qa['a'])}")
    await message.answer("\n\n".join(blocks), reply_markup=kb.help_menu(lang_of(user)))


async def begin_ask(message: Message, state: FSMContext, user: User) -> None:
    await state.set_state(AskForm.text)
    await message.answer(t(user.lang, "ask_prompt"))


@router.callback_query(FormCb.filter((F.field == "action") & (F.value == "ask")))
async def on_ask(callback: CallbackQuery, state: FSMContext, user: User) -> None:
    await callback.answer()
    if isinstance(callback.message, Message):
        await begin_ask(callback.message, state, user)


@router.message(Command("paysupport"))
async def cmd_paysupport(message: Message, user: User, notifier: Notifier) -> None:
    """Обязательная для оплаты звёздами команда: вопросы по оплате и возвратам."""
    await message.answer(t(user.lang, "paysupport", admin=notifier.settings.admin_username))
