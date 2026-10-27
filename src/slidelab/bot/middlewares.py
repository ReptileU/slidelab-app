from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware, Bot
from aiogram.types import TelegramObject
from aiogram.types import User as TgUser
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from slidelab.config import Settings
from slidelab.core.services.users import upsert_from_telegram
from slidelab.telegram.flows import Flows
from slidelab.telegram.notifier import Notifier

Handler = Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]]


class DbSessionMiddleware(BaseMiddleware):
    """Одна сессия и транзакция на апдейт: коммит после хендлера, откат при ошибке."""

    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self.sessionmaker = sessionmaker

    async def __call__(self, handler: Handler, event: TelegramObject, data: dict[str, Any]) -> Any:
        async with self.sessionmaker() as session:
            data["session"] = session
            try:
                result = await handler(event, data)
            except Exception:
                await session.rollback()
                raise
            await session.commit()
            return result


class ContextMiddleware(BaseMiddleware):
    """Клиент из БД, его язык и Notifier — в каждый хендлер."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def __call__(self, handler: Handler, event: TelegramObject, data: dict[str, Any]) -> Any:
        tg_user: TgUser | None = data.get("event_from_user")
        session: AsyncSession = data["session"]
        bot: Bot = data["bot"]
        if tg_user is not None and not tg_user.is_bot:
            user = await upsert_from_telegram(
                session,
                tg_id=tg_user.id,
                first_name=tg_user.first_name,
                last_name=tg_user.last_name,
                username=tg_user.username,
                is_manager=tg_user.id in self.settings.staff_ids,
            )
            data["user"] = user
            # Простые значения — их можно читать и после отката транзакции (в обработчике ошибок)
            data["lang"] = user.lang
            data["is_manager"] = user.is_manager
        notifier = Notifier(bot, session, self.settings)
        data["notifier"] = notifier
        data["flows"] = Flows(notifier)
        return await handler(event, data)
