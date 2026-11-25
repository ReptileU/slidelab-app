"""Общее для рабочего места команды: кто считается командой и мелкие помощники."""

import re

from aiogram.filters import BaseFilter
from aiogram.types import CallbackQuery, ForceReply, Message
from sqlalchemy.ext.asyncio import AsyncSession

from slidelab.config import Settings
from slidelab.core import repositories as repo
from slidelab.core.models import (
    Order,
    User,
)

ORDER_RE = re.compile(r"#(\d+)")
URL_RE = re.compile(r"https://\S+")


class FromStaff(BaseFilter):
    """Апдейт из чата команды (личка владельца или группа менеджеров) от человека из команды."""

    async def __call__(self, event: Message | CallbackQuery, settings: Settings, is_manager: bool = False) -> bool:
        message = event if isinstance(event, Message) else event.message
        if not is_manager or message is None:
            return False
        if message.chat.id == settings.staff_chat_id:
            return True
        # Группа менеджеров задана — команды (/stats, /grant…) всё равно доступны в личке с ботом
        return isinstance(event, Message) and message.chat.type == "private" and (event.text or "").startswith("/")


async def _ask(callback: CallbackQuery, text: str) -> None:
    await callback.answer()
    if isinstance(callback.message, Message):
        await callback.message.answer(text, reply_markup=ForceReply(selective=True))


async def owner_of(session: AsyncSession, order: Order) -> User:
    return await repo.get_user(session, order.user_id)
