"""Служебные команды: /emoji, /demo, /logo."""

import html

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from slidelab.config import Settings

router = Router(name="staff_tools")


@router.message(Command("emoji"))
async def cmd_emoji(message: Message, command: CommandObject, settings: Settings) -> None:
    """/emoji — премиум-эмодзи бота. /emoji <ключ> <премиум-эмодзи> — выбрать, /emoji <ключ> off — убрать."""
    from slidelab.telegram.premium import MARKS, EmojiStore, button_keys

    store = EmojiStore(settings.content_dir / "emoji.json")
    data = store.data()
    buttons = sorted(set(button_keys().values()))
    parts = (command.args or "").split()
    if not parts:

        def row(key: str, about: str, group: str) -> str:
            item = data[group].get(key)
            if not item:
                return f"— <code>{key}</code> · {about}"
            alt = html.escape(item.get("alt") or "⭐")
            mark = f'<tg-emoji emoji-id="{item["id"]}">{alt}</tg-emoji>'
            return f"{mark} <code>{key}</code> · {about}"

        lines = [row(k, v, "marks") for k, v in MARKS.items()]
        lines += [row(k, html.escape(strip_btn(k)), "buttons") for k in buttons]
        await message.answer(
            "<b>Премиум-эмодзи</b>\nНужен Telegram Premium у владельца бота. Работают в личке с клиентами "
            "(в канале Telegram их боту не разрешает).\n\n"
            "Выбрать: <code>/emoji logo</code> и сразу за ним премиум-эмодзи из своих наборов.\n"
            "Убрать: <code>/emoji logo off</code>\n\n" + "\n".join(lines)
        )
        return
    key = parts[0]
    group = "marks" if key in MARKS else "buttons" if key in buttons else ""
    if not group:
        await message.answer(f"Нет ключа <code>{html.escape(key)}</code>. Список — /emoji")
        return
    if len(parts) > 1 and parts[1].lower() == "off":
        store.set(group, key, None)
        await message.answer(f"Убрал эмодзи у <code>{key}</code>.")
        return
    found = next((e for e in (message.entities or []) if e.type == "custom_emoji" and e.custom_emoji_id), None)
    if found is None:
        await message.answer(
            "Не вижу премиум-эмодзи в сообщении. Напишите <code>/emoji " + key + "</code> и вставьте эмодзи из "
            "набора (обычные эмодзи не подойдут)."
        )
        return
    alt = found.extract_from(message.text or "") if hasattr(found, "extract_from") else ""
    store.set(group, key, found.custom_emoji_id, alt)
    await message.answer(
        f'Готово: <tg-emoji emoji-id="{found.custom_emoji_id}">{html.escape(alt or "⭐")}</tg-emoji> → '
        f"<code>{key}</code>. Клиенты увидят его в следующих сообщениях."
    )


def strip_btn(key: str) -> str:
    from slidelab.core.enums import Lang
    from slidelab.core.i18n import TEXTS

    return TEXTS[Lang.RU].get(key, key)


@router.message(Command("demo"))
async def cmd_demo(message: Message, settings: Settings) -> None:
    """/demo — открыть в приложении показ эффектов пакета (оплата, последняя презентация) без настоящего заказа."""
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

    base = settings.webapp_url.split("#")[0].split("?")[0].rstrip("/")
    if settings.legacy_webapp or not base.startswith("https://"):
        await message.answer("Приложение сейчас недоступно — нет ссылки.")
        return
    await message.answer(
        "🎬 Демо эффектов пакета — без заказов и списаний.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="Открыть демо", web_app=WebAppInfo(url=f"{base}/?demo=1"))]]
        ),
    )


@router.message(Command("logo"))
async def cmd_logo(message: Message, command: CommandObject, settings: Settings) -> None:
    """/logo — логотип на аватар бота (avatar_bot.png, с подписью «Bot») и канала (avatar_mono.png)."""
    from aiogram.exceptions import TelegramAPIError
    from aiogram.types import FSInputFile, InputProfilePhotoStatic

    path = settings.content_dir / "media" / "avatar_mono.png"
    if not path.exists():
        await message.answer(f"Нет файла <code>{html.escape(str(path))}</code>.")
        return
    bot_path = settings.content_dir / "media" / "avatar_bot.png"
    if not bot_path.exists():
        bot_path = path
    bot = message.bot
    assert bot is not None
    report = []
    try:
        await bot.set_my_profile_photo(photo=InputProfilePhotoStatic(photo=FSInputFile(bot_path)))
        report.append("бот — готово")
    except TelegramAPIError as e:
        report.append(f"бот — не вышло ({html.escape(str(e))[:200]}). Можно вручную: @BotFather → /setuserpic")
    try:
        await bot.set_chat_photo(chat_id=settings.channel, photo=FSInputFile(path))
        report.append("канал — готово")
    except TelegramAPIError as e:
        report.append(
            f"канал — не вышло ({html.escape(str(e))[:200]}). Нужно право бота «Изменение профиля канала» "
            "в админах канала, или поставьте фото вручную"
        )
    await message.answer("<b>Логотип</b>\n" + "\n".join(f"— {r}" for r in report))
