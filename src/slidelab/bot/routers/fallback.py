"""Нажатия, которые никто не обработал: в основном кнопки из сообщений прежнего бота. Подключается последним."""

import re

from aiogram import Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from slidelab.core.i18n import t
from slidelab.core.models import Order, User
from slidelab.telegram.flows import Flows

router = Router(name="fallback")
NUMBER = re.compile(r"\d+")


@router.callback_query()
async def on_stale_button(
    callback: CallbackQuery, session: AsyncSession, user: User, flows: Flows, is_manager: bool = False
) -> None:
    order = None
    if is_manager:  # старая кнопка владельца — присылаем новую карточку заказа с актуальными кнопками
        found = NUMBER.search(callback.data or "")
        order = await session.get(Order, int(found.group(0))) if found else None
    if order is None:
        await callback.answer(t(user.lang, "stale_button"), show_alert=True)
        return
    await callback.answer("Кнопка из прежнего бота — прислал актуальную карточку")
    owner = await session.get(User, order.user_id)
    assert owner is not None
    await flows.n.post_card(order, owner)
    await session.commit()
