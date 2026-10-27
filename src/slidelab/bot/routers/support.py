"""Вопросы менеджеру и всё, что клиент пишет вне сценариев. Подключается последним.

- текст → менеджеру (ответ реплаем вернётся клиенту);
- файл при активном заказе → материалы к заказу (и в папку для Claude);
- файл без заказа → быстрый заказ по нему.
"""

import html

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from slidelab.bot.routers import order as order_flow
from slidelab.bot.utils import file_of
from slidelab.core import repositories as repo
from slidelab.core.enums import AttachmentKind, MessageDirection
from slidelab.core.i18n import t
from slidelab.core.models import Attachment, SupportMessage, User
from slidelab.telegram import views
from slidelab.telegram.flows import Flows, Material
from slidelab.telegram.states import AskForm

router = Router(name="support")
router.message.filter(F.chat.type == "private")

REPLY_HINT = "\n\n<i>Ответьте реплаем — перешлю клиенту.</i>"


@router.message(AskForm.text)
async def on_question(message: Message, state: FSMContext, session: AsyncSession, user: User, flows: Flows) -> None:
    await state.clear()
    await relay(message, session, user, flows, "❓ <b>Вопрос</b>")
    await message.answer(t(user.lang, "question_sent"), reply_markup=await flows.n.menu(user))


@router.message()
async def on_any(message: Message, state: FSMContext, session: AsyncSession, user: User, flows: Flows) -> None:
    ref = file_of(message)
    if ref is None:
        await relay(message, session, user, flows, "💬 <b>Сообщение</b>")
        await message.answer(t(user.lang, "question_sent"))
        return

    order = await repo.latest_active_order(session, user.id)
    if order is None:
        await order_flow.begin_quick(message, state, session, user)
        return
    session.add(
        Attachment(
            order_id=order.id,
            kind=AttachmentKind.SOURCE,
            tg_file_id=ref.file_id,
            file_name=ref.name,
            mime_type=ref.mime,
        )
    )
    await flows.save_materials(order.id, [Material(name=ref.name, file_id=ref.file_id)])
    await session.commit()
    # альбом — одной шапкой
    first_in_album = not message.media_group_id or (await state.get_data()).get("album") != message.media_group_id
    if message.media_group_id:
        await state.update_data(album=message.media_group_id)
    await flows.n.copy_to_staff(message, user, header=f"📎 <b>Материал к #{order.id}</b>" if first_in_album else None)
    if first_in_album:
        await message.answer(t(user.lang, "files_attached", id=order.id))


async def relay(message: Message, session: AsyncSession, user: User, flows: Flows, title: str) -> None:
    """Сообщение клиента — команде со строкой «ID:», чтобы ответить реплаем."""
    text = message.text or message.caption or ""
    if message.text:
        who = html.escape(views.client_name(user))
        await flows.n.staff(
            f"{title}\n{who} · ID: <code>{user.tg_id}</code>\n\n{html.escape(text)}{REPLY_HINT}", user=user
        )
    else:
        await flows.n.copy_to_staff(message, user, header=title)
    if text:
        session.add(SupportMessage(user_id=user.id, direction=MessageDirection.IN, text=text))
    await session.commit()
