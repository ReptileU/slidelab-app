from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Annotated

from aiogram import Bot
from aiogram.fsm.storage.base import BaseStorage
from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from slidelab.api.auth import InitDataError, TgUser, validate_init_data
from slidelab.config import Settings
from slidelab.core.models import User
from slidelab.core.services.users import upsert_from_telegram
from slidelab.telegram.flows import Flows
from slidelab.telegram.notifier import Notifier


def get_settings_dep(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Сессия на запрос. Коммитит сам маршрут — до отправки сообщений в Telegram."""
    async with request.app.state.sessionmaker() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


SettingsDep = Annotated[Settings, Depends(get_settings_dep)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]


@dataclass(frozen=True, slots=True)
class Viewer:
    user: User
    tg: TgUser


async def get_viewer(
    session: SessionDep, settings: SettingsDep, authorization: Annotated[str | None, Header()] = None
) -> Viewer:
    """Пользователь Mini App по заголовку `Authorization: tma <initData>`."""
    if authorization and authorization.startswith("tma "):
        try:
            tg = validate_init_data(authorization[4:], settings.bot_token.get_secret_value(), settings.init_data_ttl)
        except InitDataError as e:
            raise HTTPException(status_code=401, detail=str(e)) from e
    elif settings.dev_tg_id is not None:
        # Локальная разработка в обычном браузере
        tg = TgUser(settings.dev_tg_id, "Dev", None, "dev", "ru", None)
    else:
        raise HTTPException(status_code=401, detail="Откройте приложение из Telegram")

    user = await upsert_from_telegram(
        session,
        tg_id=tg.id,
        first_name=tg.first_name,
        last_name=tg.last_name,
        username=tg.username,
        is_manager=tg.id in settings.staff_ids,
    )
    await session.commit()
    return Viewer(user=user, tg=tg)


ViewerDep = Annotated[Viewer, Depends(get_viewer)]


def get_bot(request: Request) -> Bot:
    bot: Bot = request.app.state.bot
    return bot


def get_storage(request: Request) -> BaseStorage:
    storage: BaseStorage = request.app.state.storage
    return storage


BotDep = Annotated[Bot, Depends(get_bot)]
StorageDep = Annotated[BaseStorage, Depends(get_storage)]


def get_notifier(bot: BotDep, session: SessionDep, settings: SettingsDep) -> Notifier:
    return Notifier(bot, session, settings)


NotifierDep = Annotated[Notifier, Depends(get_notifier)]


def get_flows(notifier: NotifierDep) -> Flows:
    return Flows(notifier)


FlowsDep = Annotated[Flows, Depends(get_flows)]
