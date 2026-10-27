"""Запуск бота.

uv run python -m slidelab.bot.main        — long polling (домашний компьютер, разработка)
WEBHOOK_URL=https://… в .env              — вебхук (сервер)
"""

import asyncio
import contextlib
import logging

from aiogram import Bot, Dispatcher, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.base import BaseStorage
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.types import (
    BotCommand,
    BotCommandScopeAllPrivateChats,
    BotCommandScopeChat,
    MenuButtonWebApp,
    WebAppInfo,
)
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from slidelab.bot import publisher, tasks
from slidelab.bot.middlewares import ContextMiddleware, DbSessionMiddleware
from slidelab.bot.routers import build_router
from slidelab.config import Settings, get_settings
from slidelab.core.db import make_engine, make_sessionmaker

log = logging.getLogger(__name__)
WEBHOOK_PATH = "/telegram/webhook"

# Команды клиента: короткие глаголы, как пункты меню
COMMANDS = {
    "ru": [
        ("start", "Главное меню"),
        ("new", "Новая презентация"),
        ("orders", "Мои заказы"),
        ("prices", "Цены"),
        ("packages", "Пакеты — дешевле"),
        ("help", "Вопросы"),
        ("language", "Язык"),
        ("paysupport", "Оплата и возвраты"),
    ],
    "uz": [
        ("start", "Bosh menyu"),
        ("new", "Yangi taqdimot"),
        ("orders", "Buyurtmalarim"),
        ("prices", "Narxlar"),
        ("packages", "Paketlar — arzonroq"),
        ("help", "Savollar"),
        ("language", "Til"),
        ("paysupport", "To‘lov va qaytarish"),
    ],
    "en": [
        ("start", "Main menu"),
        ("new", "New presentation"),
        ("orders", "My orders"),
        ("prices", "Prices"),
        ("packages", "Packs — cheaper"),
        ("help", "Questions"),
        ("language", "Language"),
        ("paysupport", "Payments & refunds"),
    ],
}
STAFF_COMMANDS = [
    ("stats", "Статистика за 7 и 30 дней"),
    ("subs", "Активные пакеты"),
    ("grant", "Выдать пакет: /grant ID month"),
    ("refund", "Вернуть звёзды: /refund 12"),
    ("posts", "Посты канала"),
    ("repost", "Опубликовать пост заново"),
    ("id", "Мой Telegram ID"),
]

# Описание до нажатия «Старт» и в профиле: что это и почему стоит попробовать
DESCRIPTIONS: dict[str | None, tuple[str, str]] = {
    None: (
        "SlideLab — презентации с дизайном под вашу тему.\n\n"
        "• Обложка бесплатно — платите, только если понравится\n"
        "• Живой PPTX: каждый текст и график редактируется\n"
        "• Русский, узбекский, английский\n\n"
        "Примеры работ — @slidelab_uz",
        "Презентации с дизайном под вашу тему. Обложка бесплатно.",
    ),
    "uz": (
        "SlideLab — mavzuingizga mos dizayndagi taqdimotlar.\n\n"
        "• Muqova bepul — yoqsagina to‘laysiz\n"
        "• Jonli PPTX: har bir matn va grafik tahrirlanadi\n"
        "• Rus, o‘zbek, ingliz tilida\n\n"
        "Ishlar namunasi — @slidelab_uz",
        "Mavzuingizga mos dizayndagi taqdimotlar. Muqova bepul.",
    ),
    "en": (
        "SlideLab — presentations designed for your topic.\n\n"
        "• Free cover — pay only if you like it\n"
        "• Editable PPTX: every text and chart can be changed\n"
        "• Russian, Uzbek, English\n\n"
        "Our work — @slidelab_uz",
        "Presentations designed for your topic. The cover is free.",
    ),
}


def make_storage(settings: Settings) -> BaseStorage:
    """Redis на сервере; на домашнем компьютере — память (анкеты сбросятся при перезапуске)."""
    return RedisStorage.from_url(settings.redis_url) if settings.redis_url else MemoryStorage()


def build_dispatcher(
    settings: Settings,
    *,
    storage: BaseStorage | None = None,
    sessionmaker: async_sessionmaker[AsyncSession] | None = None,
    extra_router: Router | None = None,
) -> Dispatcher:
    """storage и sessionmaker подменяются в тестах (память вместо Redis, SQLite вместо PostgreSQL)."""
    dp = Dispatcher(storage=storage or make_storage(settings), settings=settings)
    if sessionmaker is None:
        engine = make_engine(settings.database_url)
        sessionmaker = make_sessionmaker(engine)
        dp.shutdown.register(engine.dispose)
    dp.update.outer_middleware(DbSessionMiddleware(sessionmaker))
    dp.update.outer_middleware(ContextMiddleware(settings))
    dp.include_router(build_router(extra_router))
    dp["sessionmaker"] = sessionmaker
    return dp


async def set_profile(bot: Bot, settings: Settings) -> None:
    """Команды, описание и кнопка меню — то, что клиент видит до первого сообщения."""
    scope = BotCommandScopeAllPrivateChats()
    for lang, items in COMMANDS.items():
        commands = [BotCommand(command=c, description=d) for c, d in items]
        await bot.set_my_commands(commands, scope=scope, language_code=None if lang == "ru" else lang)
    if settings.admin_id:
        staff = [BotCommand(command=c, description=d) for c, d in COMMANDS["ru"] + STAFF_COMMANDS]
        await bot.set_my_commands(staff, scope=BotCommandScopeChat(chat_id=settings.admin_id))
    for code, (description, short) in DESCRIPTIONS.items():
        with contextlib.suppress(Exception):  # Telegram ограничивает частоту — не критично
            await bot.set_my_description(description=description, language_code=code)
            await bot.set_my_short_description(short_description=short, language_code=code)
    if settings.webapp_url.startswith("https://"):
        await bot.set_chat_menu_button(
            menu_button=MenuButtonWebApp(text="SlideLab", web_app=WebAppInfo(url=settings.webapp_url))
        )


def start_background(bot: Bot, dp: Dispatcher, settings: Settings) -> list["asyncio.Task[None]"]:
    sm: async_sessionmaker[AsyncSession] = dp["sessionmaker"]
    jobs = [
        asyncio.create_task(tasks.watch_reviews(bot, sm, settings)),
        asyncio.create_task(tasks.watch_stuck(bot, sm, settings)),
    ]
    if settings.admin_id and settings.channel:
        jobs.append(asyncio.create_task(publisher.loop(bot)))
    return jobs


def make_publisher_router(bot: Bot, settings: Settings) -> Router | None:
    if not (settings.admin_id and settings.channel):
        log.info("Публикация постов выключена: нужны ADMIN_ID и CHANNEL_URL")
        return None
    post_bot = (
        Bot(settings.post_bot_token.get_secret_value(), default=DefaultBotProperties(parse_mode=ParseMode.HTML))
        if settings.post_bot_token
        else bot
    )
    return publisher.setup(settings.admin_id, settings.channel, post_bot, settings.content_dir)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    settings = get_settings()
    if not settings.admin_id:
        log.warning("ADMIN_ID не задан — заявки некуда отправлять. Напишите боту /id и впишите число в .env")
    bot = Bot(settings.bot_token.get_secret_value(), default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = build_dispatcher(settings, extra_router=make_publisher_router(bot, settings))

    async def on_startup(bot: Bot) -> None:
        try:
            await set_profile(bot, settings)
        except Exception as e:
            log.warning("Профиль бота не обновлён: %s", e)
        dp["jobs"] = start_background(bot, dp, settings)

    async def on_shutdown() -> None:
        for job in dp.workflow_data.get("jobs", []):
            job.cancel()

    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    hook = settings.webhook_url
    if not hook:

        async def polling() -> None:
            await bot.delete_webhook(drop_pending_updates=False)
            await dp.start_polling(bot)

        asyncio.run(polling())
        return

    webhook_url = hook.rstrip("/") + WEBHOOK_PATH
    secret = settings.webhook_secret.get_secret_value() if settings.webhook_secret else None

    async def set_webhook(bot: Bot) -> None:
        await bot.set_webhook(webhook_url, secret_token=secret, allowed_updates=dp.resolve_used_update_types())

    dp.startup.register(set_webhook)
    app = web.Application()
    SimpleRequestHandler(dispatcher=dp, bot=bot, secret_token=secret).register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)
    web.run_app(app, host="0.0.0.0", port=settings.bot_port)


if __name__ == "__main__":
    main()
