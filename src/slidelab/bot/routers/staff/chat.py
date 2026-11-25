"""Переписка с клиентом: ответ реплаем или в теме группы уходит клиенту."""

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from slidelab.bot.routers.staff.common import ORDER_RE, URL_RE
from slidelab.core import repositories as repo
from slidelab.core.enums import (
    MessageDirection,
)
from slidelab.core.models import (
    Order,
    SupportMessage,
    User,
)
from slidelab.telegram.flows import Flows

router = Router(name="staff_chat")


def _reply_target(message: Message) -> int | None:
    src = message.reply_to_message
    if src is None or src.from_user is None or not src.from_user.is_bot:
        return None
    # Адресат — только «ID: <code>123</code>», который пишет сам бот. Имя и текст клиента в сообщениях бота
    # экранированы, поэтому «ID: 555» в них — просто текст и адресата не подменит.
    text = src.text or src.caption or ""
    for entity in src.entities or src.caption_entities or []:
        if entity.type != "code":
            continue
        value = entity.extract_from(text)
        before = text.encode("utf-16-le")[: entity.offset * 2].decode("utf-16-le")
        if value.isdigit() and before.rstrip().endswith("ID:"):
            return int(value)
    return None


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
