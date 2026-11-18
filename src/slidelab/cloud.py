"""Облако (Render и т.п.): бот, API и Mini App — в одном процессе, без компьютера.

    uv run uvicorn --factory slidelab.cloud:create_app --host 0.0.0.0 --port $PORT

Отличия от домашнего запуска:
- Telegram присылает сообщения на /telegram/webhook (WEBHOOK_URL — адрес сервиса), а не бот опрашивает его;
- бот и API — одно приложение: общие база, хранилище диалогов и сам бот;
- фоновые задачи (проверка результатов, сторож, напоминания) работают внутри того же процесса;
- ссылка «Открыть» постоянная — app.json и туннель не нужны.
"""

import asyncio
import contextlib
import hmac
import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import Update
from fastapi import FastAPI, Request, Response
from fastapi.routing import APIRoute

from slidelab.api.main import create_app as create_api
from slidelab.bot.main import (
    EXTRA_BOTS,
    WEBHOOK_PATH,
    build_dispatcher,
    make_publisher_router,
    make_storage,
    reset_menu_buttons,
    set_profile,
    start_background,
)
from slidelab.config import Settings, get_settings
from slidelab.core.db import make_engine, make_sessionmaker
from slidelab.core.filemirror import FileMirror, Root
from slidelab.telegram import premium

log = logging.getLogger("slidelab.cloud")


def with_service_url(settings: Settings, env: dict[str, str] | None = None) -> Settings:
    """Render сам сообщает адрес сервиса (RENDER_EXTERNAL_URL) — из него webhook и ссылка на Mini App,
    если их не вписали вручную."""
    env = dict(os.environ) if env is None else env
    url = (env.get("RENDER_EXTERNAL_URL") or "").rstrip("/")
    if not url:
        return settings
    update: dict[str, object] = {}
    if not settings.webhook_url:
        update["webhook_url"] = url
    if not (env.get("WEBAPP_URL") or env.get("MINIAPP_URL")):
        update["webapp_url"] = url + "/"
        update["legacy_webapp"] = False
    return settings.model_copy(update=update) if update else settings


def create_app(settings: Settings | None = None) -> FastAPI:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    settings = with_service_url(settings or get_settings())
    app = create_api(settings)
    secret = settings.webhook_secret.get_secret_value() if settings.webhook_secret else ""
    pending: set[asyncio.Task[object]] = set()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = make_engine(settings.database_url)
        sessionmaker = make_sessionmaker(engine)
        bot = Bot(settings.bot_token.get_secret_value(), default=DefaultBotProperties(parse_mode=ParseMode.HTML))
        premium.install(bot, settings.content_dir)
        storage = make_storage(settings)
        dp = build_dispatcher(
            settings, storage=storage, sessionmaker=sessionmaker, extra_router=make_publisher_router(bot, settings)
        )
        # API и бот — одно приложение: общие база, хранилище диалогов и бот
        app.state.sessionmaker, app.state.bot, app.state.storage = sessionmaker, bot, storage
        app.state.dispatcher = dp

        # Диск облака временный: папка конвейера и служебные файлы живут в базе, на диск — при запуске
        mirror = FileMirror(
            sessionmaker,
            [Root("orders", settings.work_dir), Root("data", settings.data_dir), Root("content", settings.content_dir)],
        )
        await mirror.restore()
        await dp.emit_startup(bot=bot)
        if settings.webhook_url:
            await bot.set_webhook(
                settings.webhook_url.rstrip("/") + WEBHOOK_PATH,
                secret_token=secret or None,
                allowed_updates=dp.resolve_used_update_types(),
            )
        with contextlib.suppress(Exception):
            await set_profile(bot, settings)
        jobs = start_background(bot, dp, settings)
        jobs.append(asyncio.create_task(reset_menu_buttons(bot, sessionmaker, settings)))
        jobs.append(asyncio.create_task(mirror.loop()))
        log.info("SlideLab в облаке запущен: webhook %s", settings.webhook_url or "не задан")
        try:
            yield
        finally:
            for job in jobs:
                job.cancel()
            await asyncio.gather(*jobs, *pending, return_exceptions=True)
            with contextlib.suppress(Exception):
                await mirror.sync()  # последние изменения — в базу до остановки
            await dp.emit_shutdown(bot=bot)
            for extra in EXTRA_BOTS:
                await extra.session.close()
            await bot.session.close()
            await storage.close()
            await engine.dispose()

    app.router.lifespan_context = lifespan

    async def telegram_webhook(request: Request) -> Response:
        """Апдейт от Telegram. Отвечаем сразу, обрабатываем в фоне — Telegram не ждёт долгих обработчиков."""
        if secret and not hmac.compare_digest(request.headers.get("X-Telegram-Bot-Api-Secret-Token", ""), secret):
            return Response(status_code=401)
        bot: Bot = request.app.state.bot
        update = Update.model_validate(await request.json(), context={"bot": bot})
        task = asyncio.create_task(request.app.state.dispatcher.feed_update(bot, update))
        pending.add(task)
        task.add_done_callback(pending.discard)
        return Response(status_code=200)

    # Статика Mini App подключена на «/» и перехватила бы всё — webhook ставим первым маршрутом
    app.router.routes.insert(0, APIRoute(WEBHOOK_PATH, telegram_webhook, methods=["POST"], include_in_schema=False))
    return app
