"""Действия из старой витрины index.html (sendData и ссылки /start).

Удаляется после перехода на новую Mini App.
"""

import html

from aiogram import F, Router
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
