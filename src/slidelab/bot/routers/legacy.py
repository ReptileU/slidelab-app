"""Действия из старой витрины index.html (sendData и ссылки /start).

Удаляется после перехода на новую Mini App.
"""

import contextlib
import html

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from slidelab.bot.routers import orders as my_orders
from slidelab.core import repositories as repo
from slidelab.core.enums import OrderSource
from slidelab.core.errors import DomainError
from slidelab.core.i18n import t
from slidelab.core.models import User
from slidelab.core.services.orders import OrderService
from slidelab.telegram import legacy, views
from slidelab.telegram.flows import Flows

router = Router(name="legacy")
router.message.filter(F.chat.type == "private")

# Кнопки меню прежнего бота — они ещё висят у клиентов, пока те не получат новое меню
OLD_MENU: dict[str, str] = {
    **dict.fromkeys(("💰 Прайс", "💰 Narxlar", "💰 Prices"), "prices"),
    **dict.fromkeys(("🎨 Примеры работ", "🎨 Ishlar namunasi", "🎨 Our work"), "examples"),
    **dict.fromkeys(("💬 Заказ в чате", "💬 Chatda buyurtma", "💬 Order in chat"), "new"),
    **dict.fromkeys(("📦 Мои заказы", "📦 Buyurtmalarim", "📦 My orders"), "orders"),
    **dict.fromkeys(("❓ Вопросы", "❓ Savollar", "❓ FAQ"), "help"),
    **dict.fromkeys(("🌐 Язык", "🌐 Til", "🌐 Language"), "language"),
}


@router.message(F.text.in_(OLD_MENU))
async def on_old_menu(message: Message, state: FSMContext, session: AsyncSession, user: User, flows: Flows) -> None:
    from slidelab.bot.routers import order as order_flow
    from slidelab.bot.routers import start

    assert message.text is not None
    await state.clear()
    await reset_menu_button(message)
    await message.answer(t(user.lang, "menu_updated"), reply_markup=await flows.n.menu(user))
    match OLD_MENU[message.text]:
        case "prices":
            await start.show_prices(message, session, user)
        case "examples":
            await start.show_examples(message, user, flows)
        case "new":
            await order_flow.begin(message, state, user)
        case "orders":
            await my_orders.show_orders(message, session, user)
        case "help":
            await start.show_help(message, session, user)
        case _:
            await start.cmd_language(message)


async def reset_menu_button(message: Message) -> None:
    """Прежний бот ставил каждому клиенту свою кнопку меню со старой витриной — возвращаем общую."""
    if message.bot is None:
        return
    with contextlib.suppress(TelegramAPIError):
        await message.bot.set_chat_menu_button(chat_id=message.chat.id)


@router.message(F.web_app_data)
async def on_web_app_data(message: Message, session: AsyncSession, user: User, flows: Flows) -> None:
    assert message.web_app_data is not None
    action = legacy.parse_web_app_data(message.web_app_data.data)
    if action is None:
        await message.answer(t(user.lang, "error", admin=flows.settings.admin_username))
        return
    if isinstance(action, legacy.LegacyOrder):
        user.lang = user.lang or action.ui_lang
    await handle(action, message, session, user, flows)


async def handle(
    action: legacy.LegacyAction, message: Message, session: AsyncSession, user: User, flows: Flows
) -> None:
    if isinstance(action, legacy.LegacyOrder):
        draft = action.draft
        if action.style_name:  # витрина присылает название стиля — передаём его в бриф пожеланием
            comment = f"Стиль из витрины: {action.style_name[:40]}. {draft.comment or ''}".strip()
            draft = draft.model_copy(update={"comment": comment[:400]})
        if not draft.contact and user.username:
            draft = draft.model_copy(update={"contact": f"@{user.username}"})
        order = await OrderService(session).create(
            user.id,
            draft,
            idempotency_key=f"legacy:{user.tg_id}:{message.message_id}",
            source=OrderSource.APP,
            ui_lang=action.ui_lang,
        )
        await session.commit()
        await flows.order_created(order, user)
        await session.commit()
    elif isinstance(action, legacy.LegacyPlan):
        await flows.plan_payment(user, action.plan)
        await session.commit()
    elif isinstance(action, legacy.LegacyRevision):
        try:
            revision = await OrderService(session).request_revision(action.order_id, user.id, action.text)
        except DomainError:
            await message.answer(t(user.lang, "revise_not_allowed"))
            return
        order = await repo.get_order(session, action.order_id)
        flows.pipeline.add_note(order.id, "Клиент (правки)", action.text)
        await flows.sync(order)
        await session.commit()
        paid = " · <b>платная</b>" if revision.is_paid else ""
        await flows.n.refresh_card(order, f"✏️ правки{paid} — Claude вносит:\n{html.escape(action.text)}")
        await message.answer(t(user.lang, "revise_sent") + (t(user.lang, "revise_paid") if revision.is_paid else ""))
    elif isinstance(action, legacy.LegacyQuestion):
        await flows.n.staff(
            f"❓ <b>Вопрос</b>\n{html.escape(views.client_name(user))} · ID: <code>{user.tg_id}</code>\n\n"
            f"{html.escape(action.text)}\n\n<i>Ответьте реплаем — перешлю клиенту.</i>",
            user=user,
        )
        await message.answer(t(user.lang, "question_sent"), reply_markup=await flows.n.menu(user))
    elif isinstance(action, legacy.LegacyHide):
        await my_orders.hide(session, user, flows, action.order_id)
    elif isinstance(action, legacy.LegacyGetFormat):
        await my_orders.send_format(session, user, flows, action.order_id, action.fmt)
