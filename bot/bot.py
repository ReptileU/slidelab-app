"""
SlideLab — бот для приёма заказов на презентации.
Языки: русский / узбекский.

Что умеет:
  • меню: Прайс, Примеры работ, Заказать, Вопросы
  • анкета заказа по шагам с кнопками
  • считает примерную цену
  • присылает готовую заявку (с файлами) владельцу в личку
  • сохраняет заявки в файл orders.csv

Настройки берутся из файла settings.txt.
"""

import asyncio
import base64
import contextvars
import re
import csv
import json
import html
import py_compile
import sys
import logging
import os
from datetime import datetime
from pathlib import Path

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandObject, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    LabeledPrice,
    PreCheckoutQuery,
    ForceReply,
    InlineKeyboardMarkup,
    FSInputFile,
    InputMediaPhoto,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    WebAppInfo,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from dotenv import load_dotenv

# ───────────────────────── НАСТРОЙКИ ─────────────────────────
# Настройки читаются из settings.txt (рядом с bot.py) или из .env
load_dotenv(Path(__file__).with_name("settings.txt"))
load_dotenv(Path(__file__).with_name(".env"))

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_ID = int(os.getenv("ADMIN_ID", "0") or 0)          # твой Telegram ID
CHANNEL_URL = os.getenv("CHANNEL_URL", "https://t.me/slidelab_uz").strip()
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "").strip().lstrip("@")
# Реквизиты для оплаты — впишите в settings.txt (строки PAY_UZUM=, PAY_PAYME=, PAY_ZOOMRAD=, PAY_NAME=)
PAY_CARDS = [(label, os.getenv(key, "").strip()) for key, label in
             (("PAY_UZUM", "Uzum Bank"), ("PAY_PAYME", "Payme"), ("PAY_ZOOMRAD", "Zoomrad"))]
PAY_CARDS = [(label, num) for label, num in PAY_CARDS if num]
PAY_NAME = os.getenv("PAY_NAME", "").strip()
# Оплата звёздами Telegram: сколько сумов вы реально получаете за 1 ⭐ при выводе
# (≈ $0.013 × курс ~11 970 сум/$ ≈ 155 сум, октябрь 2026). Поменять: STAR_RATE= в settings.txt, STARS=0 — выключить.
STAR_RATE = float(os.getenv("STAR_RATE", "155") or 155)
STARS_ON = os.getenv("STARS", "1").strip() != "0"


# Подарок Telegram за покупку пакета: «эмодзи:звёзды». Поменять — GIFT_WEEK= / GIFT_MONTH= / GIFT_VIP= в settings.txt, пусто — без подарка
GIFTS = {plan: os.getenv(f"GIFT_{plan.upper()}", default).strip()
         for plan, default in (("week", "🧸:15"), ("month", "🌹:25"), ("vip", "🏆:100"))}


async def tg_api(method: str, **params):
    """Прямой вызов Bot API (подарки появились позже, чем наша версия aiogram)."""
    import aiohttp
    async with aiohttp.ClientSession() as http:
        async with http.post(f"https://api.telegram.org/bot{BOT_TOKEN}/{method}", json=params) as r:
            data = await r.json()
    if not data.get("ok"):
        raise RuntimeError(data.get("description", "ошибка Telegram"))
    return data["result"]


# Акция «подарок за пакет» действует до этой даты включительно (GIFT_UNTIL=ГГГГ-ММ-ДД в settings.txt)
GIFT_UNTIL = os.getenv("GIFT_UNTIL", "2026-11-30").strip()


async def send_pack_gift(bot: Bot, uid: int, plan: str, lang: str) -> None:
    spec = GIFTS.get(plan, "")
    if not spec or datetime.now().strftime("%Y-%m-%d") > GIFT_UNTIL:
        return
    emoji, _, stars = spec.partition(":")
    stars = int(stars or 0)
    try:
        gifts = (await tg_api("getAvailableGifts"))["gifts"]
        same = [g for g in gifts if g.get("star_count") == stars and not g.get("remaining_count") == 0]
        pick = next((g for g in same if g.get("sticker", {}).get("emoji") == emoji), None) or (same[0] if same else None)
        if not pick:
            raise RuntimeError(f"нет подарка за {stars} ⭐")
        await tg_api("sendGift", user_id=uid, gift_id=pick["id"], text=T[lang]["gift_text"][:128])
        await bot.send_message(uid, T[lang]["gift_sent"])
        await bot.send_message(ADMIN_ID, f"🎁 Клиенту ID <code>{uid}</code> отправлен подарок {pick.get('sticker', {}).get('emoji', '')} "
                                         f"({pick['star_count']} ⭐ с баланса бота)")
    except Exception as e:  # noqa: BLE001
        logging.warning("Подарок не отправлен: %s", e)
        await bot.send_message(ADMIN_ID, f"🎁 Не получилось отправить подарок {emoji} ({stars} ⭐) клиенту ID <code>{uid}</code>: "
                                         f"{html.escape(str(e))[:150]}\n\nСкорее всего, на балансе бота мало звёзд. "
                                         "Подарите вручную: профиль клиента в Telegram → ⋯ → «Отправить подарок».")


def to_stars(sum_: int) -> int:
    """Сумма в сумах → звёзды, с округлением вверх до 5."""
    import math
    return max(1, math.ceil(sum_ / STAR_RATE / 5) * 5)
# Канал для публикации постов: @ник канала. По умолчанию берётся из CHANNEL_URL.
POST_CHANNEL = os.getenv("POST_CHANNEL", "").strip() or (
    "@" + CHANNEL_URL.rstrip("/").split("/")[-1] if "t.me/" in CHANNEL_URL else "")
# Необязательно: отдельный бот только для публикации в канал
POST_BOT_TOKEN = os.getenv("POST_BOT_TOKEN", "").strip()
# Mini App (красивое окно заказа внутри Telegram). Пусто = выключено.
MINIAPP_URL = os.getenv("MINIAPP_URL", "https://reptileu.github.io/slidelab-app/").strip()

ORDERS_FILE = Path(__file__).with_name("orders.csv")
ORDERS_DB = Path(__file__).with_name("orders.json")   # номера и статусы заказов для «Мои заказы»
SUBS_DB = Path(__file__).with_name("subs.json")       # подписки клиентов

# ───────────────────────── ПОДПИСКИ ─────────────────────────
# limit — сколько презентаций за период (21–30 слайдов списывает 2). Чтобы не перегрузить вас,
# безлимита нет даже на VIP; одновременно в работе у VIP — один заказ, следующий — после сдачи.
PLANS = {
    "week":  {"days": 14, "limit": 2,  "price": 34_000,  "notes": False},
    "month": {"days": 30, "limit": 4,  "price": 64_000,  "notes": False},
    "vip":   {"days": 60, "limit": 10, "price": 145_000, "notes": True},
}
CURRENT_USER = contextvars.ContextVar("current_user", default=None)
PORTFOLIO_DIR = Path(__file__).with_name("portfolio")   # сюда кладём картинки работ

# ───────────────────────── ЦЕНЫ ─────────────────────────
# ключ пакета -> (цена в сумах, "от" или нет)
PACKAGES = {
    "s10": (19_000, False),
    "s20": (29_000, False),
    "s30": (39_000, False),
}
URGENT_EXTRA = 0.5      # +50% за срочность
TEXT_EXTRA = 5_000     # текст под ключ
NOTES_EXTRA = 5_000    # конспект для выступления


FIRST_PRICE = int(os.getenv("FIRST_PRICE", "9900") or 0)   # первый заказ «Мини» для новых клиентов (0 — выключить)
CREDIT_DAYS = int(os.getenv("CREDIT_DAYS", "3") or 0)       # сколько дней после сдачи можно «засчитать» заказ в пакет


def is_new_client(uid) -> bool:
    if not uid:
        return False
    if any(o.get("uid") == uid and o.get("status") != "cancel" for o in load_orders()["orders"].values()):
        return False
    return str(uid) not in load_subs()


def first_discount(package: str) -> bool:
    return bool(FIRST_PRICE) and package == "s10" and is_new_client(CURRENT_USER.get())


def calc_price(package: str, deadline: str, need_text: bool, need_notes: bool) -> tuple[int, bool]:
    """Возвращает (примерная цена, это минимальная цена 'от')."""
    base, is_from = PACKAGES[package]
    if first_discount(package):
        base = FIRST_PRICE
    price = base
    if deadline == "d1":
        price = int(price * (1 + URGENT_EXTRA))
    if need_text:
        price += TEXT_EXTRA
    if need_notes:
        price += NOTES_EXTRA
    return price, is_from


def fmt_sum(n: int) -> str:
    return f"{n:,}".replace(",", " ")


# ───────────────────────── ТЕКСТЫ ─────────────────────────
T = {
    "ru": {
        "choose_lang": "Выберите язык / Tilni tanlang / Choose language:",
        "welcome": (
            "👋 Привет! Это <b>SlideLab</b> — красивые презентации на заказ.\n\n"
            "🎨 Свой стиль под каждую тему: фото, иллюстрации, графики\n"
            "📝 Конспект для выступления\n"
            "🎁 Обложка бесплатно — сначала посмотри стиль, потом плати\n\n"
            "📎 Или просто перешли сюда лекцию / задание — оформим заказ в 2 нажатия\n\n"
            "Выбери, что нужно 👇"
        ),
        "btn_price": "💰 Прайс",
        "btn_examples": "🎨 Примеры работ",
        "btn_order": "💬 Заказ в чате",
        "btn_app": "✨ Заказать",
        "plan_names": {"week": "2 презентации", "month": "4 презентации", "vip": "VIP · 10 презентаций"},
        "sub_req_sent": ("📦 Заявка на пакет «{plan}» принята! "
                         "После оплаты пакет включится — остаток видно в приложении: 👤 Профиль."),
        "sub_on": "📦 Пакет «{plan}» включён! Доступно презентаций: {limit}, действует до {end}. Заказывайте как обычно — презентация спишется из пакета.",
        "sub_line": "\n\n📦 Из пакета списано: {cost}, осталось {left}.",
        "sub_pay": " Доплата: {pay} сум (срочность / текст).",
        "sub_empty": "\n\n📦 Презентации в пакете закончились — этот заказ по обычной цене. Новый пакет можно купить в любой момент: «✨ Заказать» → 👤 Профиль.",
        "sub_status": "📦 Ваш пакет: осталось {left} из {limit} презентаций, до {end}.",
        "btn_my": "📦 Мои заказы",
        "my_empty": "📦 У вас пока нет заказов. Нажмите «✨ Заказать» — это займёт пару минут.",
        "my_title": "📦 <b>Ваши заказы</b>\n",
        "order_line": "\n\n📦 Номер заказа: <b>#{id}</b>. Статус смотрите в «📦 Мои заказы».",
        "status_note": "📦 Заказ <b>#{id}</b> «{topic}»: {status}",
        "st": {"new": "🆕 Принят", "cover": "🎨 Обложка готова", "work": "🛠 В работе",
               "edit": "✏️ Вносим правки", "done": "✅ Готово", "cancel": "✖️ Отменён"},
        "done_hint": "\n\n✏️ Нужно что-то поменять? Нажмите «Внести правки» ниже — 2 правки бесплатно.",
        "btn_edit": "✏️ Внести правки #{id}",
        "menu_refresh": "📦 Статус обновлён и в приложении: «✨ Заказать» → 👤 Профиль.",
        "pres_saved": "🎞 Презентация сохранена в приложении: «✨ Заказать» → 👤 Профиль → Мои презентации.",
        "edit_prompt": ("✏️ <b>Правки к заказу #{id}</b>\nНапишите, что поменять (например: «слайд 3 — другой график»), "
                        "и пришлите скриншоты или файлы — всё передам. Когда закончите, просто вернитесь в меню."),
        "edit_got": "✅ Передал правки. Можно прислать ещё — текст, скриншоты, файлы.",
        "cv_ready": "🎨 Обложка к заказу #{id} готова! Это бесплатно. Нравится?",
        "cv_ok": "👍 Нравится — делаем дальше",
        "cv_chg": "✏️ Хочу поменять",
        "cv_chg_prompt": "✏️ Напишите, что поменять в обложке (цвет, стиль, фото, текст) — можно со скриншотом примера.",
        "cv_go": "🚀 Отлично! Приступаем ко всей презентации — пришлём, как будет готово.",
        "cv_pay": "🙌 Отлично! Осталось оплатить — и сразу приступим ко всей презентации.",
        "pay_head": "💳 <b>Оплата заказа #{id}</b> — {sum} сум\n\n",
        "pay_head_sub": "💳 <b>Оплата пакета «{plan}»</b> — {sum} сум\n\n",
        "pay_cards": "Переведите на любую карту (нажмите на номер — он скопируется):\n{cards}{name}\n\nПосле оплаты картой нажмите «✅ Я оплатил картой» и пришлите скриншот чека.",
        "pay_name": "\nПолучатель: <b>{n}</b>",
        "pay_order_note": "🎁 Обложку делаем бесплатно и без предоплаты. Оплатить можно сейчас или после того, как обложка понравится — тогда сразу начнём всю презентацию.\n\n",
        "pay_nocards": "Менеджер напишет, как оплатить.",
        "btn_paid": "✅ Я оплатил картой",
        "btn_stars": "⭐ Оплатить звёздами — {n} ⭐",
        "pay_or_stars": "\n\n⭐ Или оплатите звёздами Telegram — одна кнопка, подтверждается автоматически.",
        "pay_stars_only": "Оплатите звёздами Telegram — кнопка ниже, подтверждение придёт автоматически.",
        "inv_order": "Презентация SlideLab #{id}",
        "inv_order_d": "«{topic}» · {sl} слайдов. Оплата всей презентации (обложка — бесплатно).",
        "inv_sub": "Пакет «{plan}»",
        "inv_sub_d": "Презентаций: {limit}, действует {days} дней. Остаток не сгорает при покупке нового пакета.",
        "inv_done": "Уже оплачено 👍",
        "inv_credit": " Засчитан заказ #{id} (−{sum} сум).",
        "cr_text": ("🔥 <b>Понравилось? Сделаем выгоднее!</b>\n\nВозьмите пакет до <b>{date}</b> — "
                    "этот заказ ({sum} сум) засчитаем в него. Доплачиваете только разницу:\n\n{lines}\n\n"
                    "Остаток не сгорает, заказывать — как обычно."),
        "cr_line": "📦 {plan}: <s>{full}</s> → <b>{pay} сум</b> · ещё {more} шт.",
        "cr_btn": "📦 {plan} — доплатить {pay}",
        "cr_expired": "Срок зачёта прошёл — пакет можно купить по обычной цене в приложении.",
        "paysupport": "💬 Вопросы по оплате и возвратам: напишите сюда в чат или менеджеру @{admin} — ответим и поможем. Если заказ отменён до начала работы, звёзды вернём.",
        "pay_send_check": "📸 Пришлите скриншот или фото чека об оплате (можно и текстом: сумма, время, с какой карты).",
        "pay_thanks": "🙏 Спасибо! Проверим поступление и подтвердим — обычно в течение часа.",
        "paid_go": "✅ Оплату по заказу #{id} получили, спасибо! Приступаем ко всей презентации.",
        "deck_ready": "🎉 Ваша презентация по заказу #{id} готова!",
        "fmt_ask": ("🎉 <b>Презентация по заказу #{id} готова!</b>\n\nВ каком формате прислать? Выберите — всё придёт сюда, в чат.\n"
                    "Google Slides и Canva — откроются в вашем собственном аккаунте: редактируете сами, без нашего."),
        "fmt_btn": {"pptx": "📊 PowerPoint (PPTX)", "pdf": "📄 PDF", "png": "🖼 Картинками", "gslides": "🟢 Google Slides", "canva": "🎨 Canva"},
        "fmt_all": "📦 Все форматы",
        "lnk_gslides": ("🟢 <b>Google Slides</b> — ваша личная копия:\n{url}\n\nНажмите «Создать копию» — презентация сохранится в вашем "
                        "Google Диске, и вы сможете менять её как угодно (нужен любой аккаунт Google)."),
        "lnk_canva": ("🎨 <b>Canva</b> — ваша личная копия:\n{url}\n\nОткройте ссылку и нажмите «Использовать шаблон» — копия появится "
                      "в вашем аккаунте Canva (бесплатный подойдёт), редактируйте сколько угодно."),
        "fmt_sending": "Отправляю…",
        "how_gslides": ("🟢 <b>Как открыть в Google Slides</b> (в вашем аккаунте, без нашего):\n"
                        "1. Сохраните файл PPTX выше\n2. Откройте drive.google.com → «Создать» → «Загрузить файл»\n"
                        "3. Нажмите на файл → «Открыть в Google Презентациях» — и редактируйте"),
        "how_canva": ("🎨 <b>Как открыть в Canva</b> (в вашем аккаунте, бесплатный подойдёт):\n"
                      "1. Сохраните файл PPTX выше\n2. В Canva нажмите «Создать дизайн» → «Импортировать файл»\n"
                      "3. Выберите PPTX — все слайды станут редактируемыми"),
        "fmt_none": "Не нашёл файл в этом формате — напишите нам, пришлём.",
        "fmt_more": "\n\n📎 Нужен другой формат — нажмите кнопку в сообщении выше ещё раз.",
        "gift_text": "Спасибо, что выбрали SlideLab! Пусть презентации будут на 5+ 🎓",
        "gift_sent": "🎁 Акция SlideLab: за покупку пакета — подарок! Он уже в вашем профиле Telegram.",
        "paid_early": "✅ Оплату по заказу #{id} получили, спасибо! Сначала пришлём обложку — как только вы её одобрите, сразу делаем всю презентацию.",
        "q_sent": "✅ Вопрос отправлен! Ответим прямо здесь, в чате.",
        "ask_prompt": "❓ Напишите ваш вопрос одним сообщением — я передам его менеджеру.",
        "reply_prefix": "💬 <b>Ответ SlideLab:</b>",
        "app_sent": (
            "🎉 Заявка отправлена! Скоро напишем вам и пришлём <b>бесплатную обложку</b>.\n\n"
            "Если есть файлы (текст, шаблон, требования) — можно просто прислать их сюда."
        ),
        "app_file_ok": "✅ Передал. Можно прислать ещё.",
        "app_sent_src": (
            "🎉 Заявка отправлена! Скоро напишем вам и пришлём <b>бесплатную обложку</b>.\n\n"
            "📎 <b>Теперь перешлите сюда свои источники</b> прямо из других чатов — сохранять на телефон не нужно.\n"
            "Как: зажмите сообщение с файлом → «Переслать» → выберите этот бот.\n\n"
            "Подходят любые файлы (PDF, Word, PowerPoint, Excel, фото, видео, аудио, архивы) и ссылки."
        ),
        "sources": "Источники",
        "tpl": "Шаблон",
        "tpl_ask": "\n\n🎨 <b>Перешлите сюда файл шаблона</b> (PPTX, PDF, скриншоты) или ссылку на него (Google Slides, Canva). 🔓 Для ссылки откройте доступ: «Все, у кого есть ссылка».",
        "qf_ask": "📎 Получил файл! Сделаем по нему презентацию.\n\nСколько нужно <b>слайдов</b>? 👇",
        "qf_deadline": "⏰ К какому <b>сроку</b>?",
        "qf_more": "✅ Добавил файл (всего: {n}). Выберите вариант кнопкой выше 👆",
        "comment": "Пожелания",
        "btn_faq": "❓ Вопросы",
        "btn_lang": "🌐 Язык",
        "price": (
            "📌 <b>ПРАЙС</b>\n\n"
            "🟢 Мини — до 10 слайдов — 19 000 сум\n"
            "🎁 <b>Первый заказ Мини — 9 900 сум</b>\n"
            "🔵 Стандарт — 11–20 слайдов — 29 000 сум\n"
            "🟣 Большой — 21–30 слайдов — 39 000 сум\n\n"
            "⚡ Срочно (до 20 слайдов): +50%\n"
            "➕ Текст под ключ: +5 000 сум\n"
            "➕ Конспект для выступления: +5 000 сум\n"
            "✏️ 2 правки бесплатно\n\n"
            "✅ В цене: уникальный дизайн, подбор фото и иллюстраций, графики, PPTX + PDF"
        ),
        "examples": "🎨 Все работы и стили — в нашем канале:\n{url}",
        "examples_caption": "🎨 Примеры наших работ. Каждая презентация — в своём стиле под тему.",
        "examples_soon": "🎨 Примеры работ скоро появятся здесь. А пока нажмите «📝 Заказать» — пришлём бесплатную обложку в стиле вашей темы 🎁",
        "faq": (
            "❓ <b>Частые вопросы</b>\n\n"
            "<b>Как быстро?</b> Срок обсуждаем в чате до начала работы и держим его — обычно в течение дня. Очень срочно — «Срочно» (до 20 слайдов), +50%."
            "<b>Как оплатить?</b> Обложка — бесплатно. Понравилась — оплачиваете заказ: картой Uzum Bank / Payme / Zoomrad (реквизиты пришлёт бот) или звёздами Telegram в одно нажатие.\n\n"
            "<b>А если не понравится?</b> Сначала делаем бесплатную обложку. "
            "Потом 2 правки бесплатно. Не подошло после правок — вернём предоплату.\n\n"
            "<b>В каком формате?</b> PPTX (PowerPoint, Google Slides) и PDF.\n\n"
            "<b>Нет текста?</b> Напишем сами (+5 000 сум).\n\n"
            "<b>Есть свой шаблон или фирменный стиль?</b> Пришлите — оформим в нём. "
            "Нет — придумаем дизайн под вашу тему.\n\n"
            "<b>Мою работу покажут другим?</b> Нет, только с вашего разрешения."
        ),
        "faq_contact": "Остались вопросы? Напишите: @{admin}",
        "q_topic": "📝 Шаг 1/7. Напишите <b>тему презентации</b>:",
        "q_slides": "📊 Шаг 2/7. Сколько нужно <b>слайдов</b>?",
        "slides": {"s10": "до 10", "s20": "11–20", "s30": "21–30"},
        "q_deadline": "⏰ Шаг 3/7. К какому <b>сроку</b>?",
        "deadline": {"d1": "⚡ Срочно (+50%)", "d2": "📅 Обычно — срок обсудим в чате", "d3": "🐢 Не спешу"},
        "q_plang": "🌐 Шаг 4/7. На каком <b>языке</b> презентация?",
        "plang": {"ru": "Русский", "uz": "O‘zbek", "en": "English"},
        "q_design": (
            "🎨 Шаг 5/7. <b>Дизайн</b>: у вас есть свой шаблон, фирменный стиль или пример, "
            "как должно выглядеть?"
        ),
        "design": {"own": "📎 Есть свой дизайн / шаблон", "ours": "✨ Сделайте дизайн сами по теме"},
        "files_own_hint": "\n\n📎 <b>Не забудьте прислать свой шаблон или пример дизайна</b> (файл PPTX, PDF или скриншоты).",
        "q_extras": "➕ Шаг 6/7. Что ещё нужно? Нажмите, чтобы отметить, потом «Дальше».",
        "extra_text": "Текст под ключ (+5 000)",
        "extra_notes": "Конспект (+5 000)",
        "next": "Дальше ➡️",
        "q_files": (
            "📎 Шаг 7/7. Отправьте <b>материалы</b>: текст, требования преподавателя, фото, примеры.\n"
            "Можно несколько файлов. Когда закончите — нажмите «Готово»."
        ),
        "files_got": "✅ Получено файлов: {n}. Можно ещё или нажмите «Готово».",
        "btn_done": "✅ Готово",
        "btn_skip": "Нет материалов",
        "q_contact": (
            "📞 Как с вами связаться? Нажмите кнопку, чтобы отправить номер, "
            "или напишите ник / телефон текстом."
        ),
        "btn_phone": "📱 Отправить номер",
        "summary": (
            "🧾 <b>Ваша заявка</b>\n\n"
            "Тема: {topic}\n"
            "Слайдов: {slides}\n"
            "Срок: {deadline}\n"
            "Язык: {plang}\n"
            "Дизайн: {design}\n"
            "Доп.: {extras}\n"
            "Файлов: {files}\n\n"
            "💰 Примерная цена: <b>{price}</b>\n\n"
            "Всё верно?"
        ),
        "price_fmt": "{n} сум",
        "price_fmt_from": "от {n} сум",
        "extras_none": "—",
        "btn_confirm": "✅ Отправить заявку",
        "btn_restart": "🔄 Заполнить заново",
        "sent": (
            "🎉 Заявка отправлена! Скоро напишем вам и пришлём <b>бесплатную обложку</b>.\n"
            "Обычно отвечаем в течение часа."
        ),
        "cancelled": "Заявка отменена. Возвращаю в меню.",
        "use_buttons": "Пожалуйста, выберите вариант кнопкой выше 👆",
        "send_text": "Пожалуйста, напишите текстом.",
        "error_admin": "⚠️ Не удалось отправить заявку. Напишите напрямую: @{admin}",
    },
    "uz": {
        "choose_lang": "Выберите язык / Tilni tanlang / Choose language:",
        "welcome": (
            "👋 Salom! Bu <b>SlideLab</b> — buyurtma asosida chiroyli taqdimotlar.\n\n"
            "🎨 Har bir mavzuga o‘z uslubi: rasmlar, illyustratsiyalar, grafiklar\n"
            "📝 Chiqish uchun konspekt\n"
            "🎁 Muqova bepul — avval uslubni ko‘ring, keyin to‘lang\n\n"
            "📎 Yoki ma’ruza / topshiriqni shu yerga forward qiling — 2 bosishda buyurtma\n\n"
            "Keraklisini tanlang 👇"
        ),
        "btn_price": "💰 Narxlar",
        "btn_examples": "🎨 Ishlar namunasi",
        "btn_order": "💬 Chatda buyurtma",
        "btn_app": "✨ Buyurtma",
        "plan_names": {"week": "2 ta taqdimot", "month": "4 ta taqdimot", "vip": "VIP · 10 ta taqdimot"},
        "sub_req_sent": ("📦 «{plan}» paketiga ariza qabul qilindi! "
                         "To‘lovdan so‘ng paket yoqiladi — qoldiq ilovada: 👤 Profil."),
        "sub_on": "📦 «{plan}» paketi yoqildi! Taqdimotlar: {limit}, {end} gacha amal qiladi. Odatdagidek buyurtma bering — taqdimot paketdan yechiladi.",
        "sub_line": "\n\n📦 Paketdan yechildi: {cost}, qoldi {left}.",
        "sub_pay": " Qo‘shimcha to‘lov: {pay} so‘m (shoshilinch / matn).",
        "sub_empty": "\n\n📦 Paketdagi taqdimotlar tugadi — bu buyurtma odatiy narxda. Yangi paketni istalgan vaqtda olish mumkin: «✨ Buyurtma» → 👤 Profil.",
        "sub_status": "📦 Paketingiz: {limit} tadan {left} qoldi, {end} gacha.",
        "btn_my": "📦 Buyurtmalarim",
        "my_empty": "📦 Sizda hali buyurtma yo‘q. «✨ Buyurtma» ni bosing — bir-ikki daqiqa.",
        "my_title": "📦 <b>Buyurtmalaringiz</b>\n",
        "order_line": "\n\n📦 Buyurtma raqami: <b>#{id}</b>. Holatini «📦 Buyurtmalarim» da ko‘ring.",
        "status_note": "📦 <b>#{id}</b> «{topic}» buyurtma: {status}",
        "st": {"new": "🆕 Qabul qilindi", "cover": "🎨 Muqova tayyor", "work": "🛠 Ishlanmoqda",
               "edit": "✏️ Tuzatilmoqda", "done": "✅ Tayyor", "cancel": "✖️ Bekor qilindi"},
        "done_hint": "\n\n✏️ Biror narsani o‘zgartirish kerakmi? Pastdagi «Tuzatish kiritish» ni bosing — 2 marta bepul.",
        "btn_edit": "✏️ Tuzatish #{id}",
        "menu_refresh": "📦 Holat ilovada ham yangilandi: «✨ Buyurtma» → 👤 Profil.",
        "pres_saved": "🎞 Taqdimot ilovada saqlandi: «✨ Buyurtma» → 👤 Profil → Taqdimotlarim.",
        "edit_prompt": ("✏️ <b>#{id} buyurtmaga tuzatishlar</b>\nNimani o‘zgartirishni yozing (masalan: «3-slayd — boshqa grafik») "
                        "va skrinshot yoki fayllarni yuboring — hammasini yetkazaman. Tugatgach, menyuga qayting."),
        "edit_got": "✅ Tuzatishlar yetkazildi. Yana yuborishingiz mumkin — matn, skrinshot, fayl.",
        "cv_ready": "🎨 #{id} buyurtma muqovasi tayyor! Bu bepul. Yoqdimi?",
        "cv_ok": "👍 Yoqdi — davom etamiz",
        "cv_chg": "✏️ O‘zgartirmoqchiman",
        "cv_chg_prompt": "✏️ Muqovada nimani o‘zgartirish kerakligini yozing (rang, uslub, rasm, matn) — namunani skrinshot qilib yuborsangiz ham bo‘ladi.",
        "cv_go": "🚀 Ajoyib! Butun taqdimotni boshlaymiz — tayyor bo‘lgach yuboramiz.",
        "cv_pay": "🙌 Ajoyib! To‘lov qilish qoldi — so‘ng darhol butun taqdimotni boshlaymiz.",
        "pay_head": "💳 <b>#{id} buyurtma to‘lovi</b> — {sum} so‘m\n\n",
        "pay_head_sub": "💳 <b>«{plan}» paketi to‘lovi</b> — {sum} so‘m\n\n",
        "pay_cards": "Istalgan kartaga o‘tkazing (raqamni bossangiz — nusxalanadi):\n{cards}{name}\n\nKarta orqali to‘lagach «✅ Karta bilan to‘ladim» ni bosing va chek skrinshotini yuboring.",
        "pay_name": "\nQabul qiluvchi: <b>{n}</b>",
        "pay_order_note": "🎁 Muqovani bepul va oldindan to‘lovsiz qilamiz. Hozir yoki muqova yoqqandan keyin to‘lashingiz mumkin — shunda darhol butun taqdimotni boshlaymiz.\n\n",
        "pay_nocards": "Menejer to‘lov qanday qilinishini yozadi.",
        "btn_paid": "✅ Karta bilan to‘ladim",
        "btn_stars": "⭐ Yulduzlar bilan to‘lash — {n} ⭐",
        "pay_or_stars": "\n\n⭐ Yoki Telegram yulduzlari bilan to‘lang — bitta tugma, avtomatik tasdiqlanadi.",
        "pay_stars_only": "Telegram yulduzlari bilan to‘lang — pastdagi tugma, tasdiq avtomatik keladi.",
        "inv_order": "SlideLab taqdimoti #{id}",
        "inv_order_d": "«{topic}» · {sl} slayd. Butun taqdimot to‘lovi (muqova — bepul).",
        "inv_sub": "«{plan}» paketi",
        "inv_sub_d": "Taqdimotlar: {limit}, {days} kun amal qiladi. Yangi paket olinganda qoldiq yonmaydi.",
        "inv_done": "Allaqachon to‘langan 👍",
        "inv_credit": " #{id} buyurtma hisobga olindi (−{sum} so‘m).",
        "cr_text": ("🔥 <b>Yoqdimi? Yanada foydali qilamiz!</b>\n\n<b>{date}</b> gacha paket oling — "
                    "bu buyurtma ({sum} so‘m) unga hisoblanadi. Faqat farqini to‘laysiz:\n\n{lines}\n\n"
                    "Qoldiq yonmaydi, buyurtma — odatdagidek."),
        "cr_line": "📦 {plan}: <s>{full}</s> → <b>{pay} so‘m</b> · yana {more} ta.",
        "cr_btn": "📦 {plan} — {pay} to‘lash",
        "cr_expired": "Hisoblash muddati o‘tdi — paketni ilovada odatiy narxda olish mumkin.",
        "paysupport": "💬 To‘lov va qaytarish bo‘yicha savollar: shu chatga yoki menejer @{admin} ga yozing — yordam beramiz. Buyurtma ish boshlanishidan oldin bekor qilinsa, yulduzlar qaytariladi.",
        "pay_send_check": "📸 To‘lov chekining skrinshoti yoki rasmini yuboring (matn bilan ham bo‘ladi: summa, vaqt, qaysi kartadan).",
        "pay_thanks": "🙏 Rahmat! To‘lovni tekshirib, tasdiqlaymiz — odatda bir soat ichida.",
        "paid_go": "✅ #{id} buyurtma to‘lovi qabul qilindi, rahmat! Butun taqdimotni boshlaymiz.",
        "deck_ready": "🎉 #{id} buyurtma bo‘yicha taqdimotingiz tayyor!",
        "fmt_ask": ("🎉 <b>#{id} buyurtma bo‘yicha taqdimot tayyor!</b>\n\nQaysi formatda yuboraylik? Tanlang — hammasi shu chatga keladi.\n"
                    "Google Slides va Canva — o‘z akkauntingizda ochiladi: o‘zingiz tahrirlaysiz, bizning akkauntsiz."),
        "fmt_btn": {"pptx": "📊 PowerPoint (PPTX)", "pdf": "📄 PDF", "png": "🖼 Rasmlar", "gslides": "🟢 Google Slides", "canva": "🎨 Canva"},
        "fmt_all": "📦 Barcha formatlar",
        "lnk_gslides": ("🟢 <b>Google Slides</b> — sizning shaxsiy nusxangiz:\n{url}\n\n«Nusxa yaratish» ni bosing — taqdimot Google "
                        "Diskingizga saqlanadi va uni xohlaganingizcha o‘zgartirasiz (istalgan Google akkaunti kerak)."),
        "lnk_canva": ("🎨 <b>Canva</b> — sizning shaxsiy nusxangiz:\n{url}\n\nHavolani oching va «Shablondan foydalanish» ni bosing — nusxa "
                      "Canva akkauntingizda paydo bo‘ladi (bepul ham bo‘ladi), xohlaganingizcha tahrirlang."),
        "fmt_sending": "Yuboryapman…",
        "how_gslides": ("🟢 <b>Google Slides da qanday ochish</b> (o‘z akkauntingizda):\n"
                        "1. Yuqoridagi PPTX faylni saqlang\n2. drive.google.com → «Yaratish» → «Fayl yuklash»\n"
                        "3. Faylni bosing → «Google Slaydlarda ochish» — va tahrirlang"),
        "how_canva": ("🎨 <b>Canva da qanday ochish</b> (o‘z akkauntingizda, bepul ham bo‘ladi):\n"
                      "1. Yuqoridagi PPTX faylni saqlang\n2. Canva da «Dizayn yaratish» → «Faylni import qilish»\n"
                      "3. PPTX ni tanlang — barcha slaydlar tahrirlanadigan bo‘ladi"),
        "fmt_none": "Bu formatdagi faylni topmadim — bizga yozing, yuboramiz.",
        "fmt_more": "\n\n📎 Boshqa format kerakmi — yuqoridagi xabardagi tugmani yana bosing.",
        "gift_text": "SlideLab ni tanlaganingiz uchun rahmat! Taqdimotlar faqat 5 ga bo‘lsin 🎓",
        "gift_sent": "🎁 SlideLab aksiyasi: paket uchun — sovg‘a! U allaqachon Telegram profilingizda.",
        "paid_early": "✅ #{id} buyurtma to‘lovi qabul qilindi, rahmat! Avval muqovani yuboramiz — uni ma’qullashingiz bilan butun taqdimotni boshlaymiz.",
        "q_sent": "✅ Savol yuborildi! Shu chatda javob beramiz.",
        "ask_prompt": "❓ Savolingizni bitta xabarda yozing — menejerga yetkazaman.",
        "reply_prefix": "💬 <b>SlideLab javobi:</b>",
        "app_sent": (
            "🎉 Ariza yuborildi! Tez orada yozamiz va <b>bepul muqova</b> yuboramiz.\n\n"
            "Fayllar bo‘lsa (matn, shablon, talablar) — shu yerga yuborishingiz mumkin."
        ),
        "app_file_ok": "✅ Yetkazildi. Yana yuborishingiz mumkin.",
        "app_sent_src": (
            "🎉 Ariza yuborildi! Tez orada yozamiz va <b>bepul muqova</b> yuboramiz.\n\n"
            "📎 <b>Endi manbalaringizni boshqa chatlardan shu yerga forward qiling</b> — telefonga saqlash shart emas.\n"
            "Qanday: fayl xabarini bosib turing → «Forward» → shu botni tanlang.\n\n"
            "Istalgan fayllar (PDF, Word, PowerPoint, Excel, rasm, video, audio, arxiv) va havolalar mos."
        ),
        "sources": "Manbalar",
        "tpl": "Shablon",
        "tpl_ask": "\n\n🎨 <b>Shablon faylini</b> (PPTX, PDF, skrinshot) yoki havolasini (Google Slides, Canva) shu yerga yuboring. 🔓 Havola uchun kirishni oching: «Havolaga ega barcha».",
        "qf_ask": "📎 Fayl qabul qilindi! Shu bo‘yicha taqdimot tayyorlaymiz.\n\nNechta <b>slayd</b> kerak? 👇",
        "qf_deadline": "⏰ Qaysi <b>muddatgacha</b>?",
        "qf_more": "✅ Fayl qo‘shildi (jami: {n}). Yuqoridagi tugmani tanlang 👆",
        "comment": "Istaklar",
        "btn_faq": "❓ Savollar",
        "btn_lang": "🌐 Til",
        "price": (
            "📌 <b>NARXLAR</b>\n\n"
            "🟢 Mini — 10 slaydgacha — 19 000 so‘m\n"
            "🎁 <b>Birinchi Mini buyurtma — 9 900 so‘m</b>\n"
            "🔵 Standart — 11–20 slayd — 29 000 so‘m\n"
            "🟣 Katta — 21–30 slayd — 39 000 so‘m\n\n"
            "⚡ Shoshilinch (20 slaydgacha): +50%\n"
            "➕ Matnni ham yozib beraman: +5 000 so‘m\n"
            "➕ Chiqish uchun konspekt: +5 000 so‘m\n"
            "✏️ 2 marta tuzatish bepul\n\n"
            "✅ Narxga kiradi: noyob dizayn, rasm va illyustratsiyalar tanlash, grafiklar, PPTX + PDF"
        ),
        "examples": "🎨 Barcha ishlar va uslublar — kanalimizda:\n{url}",
        "examples_caption": "🎨 Ishlarimiz namunalari. Har bir taqdimot — mavzuga mos o‘z uslubida.",
        "examples_soon": "🎨 Ishlar namunalari tez orada shu yerda bo‘ladi. Hozircha «📝 Buyurtma» ni bosing — mavzuingiz uslubida bepul muqova yuboramiz 🎁",
        "faq": (
            "❓ <b>Ko‘p beriladigan savollar</b>\n\n"
            "<b>Qancha vaqtda?</b> Muddatni ish boshlanishidan oldin chatda kelishamiz va unga amal qilamiz — odatda bir kun ichida. Juda tez — «Shoshilinch» (20 slaydgacha), +50%."
            "<b>Qanday to‘lanadi?</b> Muqova — bepul. Yoqsa — buyurtmani Uzum Bank / Payme / Zoomrad kartasiga (rekvizitlarni bot yuboradi) yoki Telegram yulduzlari bilan bir bosishda to‘laysiz.\n\n"
            "<b>Yoqmasa-chi?</b> Avval bepul muqova tayyorlaymiz. "
            "Keyin 2 marta tuzatish bepul. Tuzatishdan keyin ham yoqmasa — oldindan to‘lovni qaytaramiz.\n\n"
            "<b>Qaysi formatda?</b> PPTX (PowerPoint, Google Slides) va PDF.\n\n"
            "<b>Matn yo‘qmi?</b> O‘zimiz yozamiz (+5 000 so‘m).\n\n"
            "<b>O‘z shabloningiz yoki korporativ uslubingiz bormi?</b> Yuboring — shunda bezaymiz. "
            "Yo‘q bo‘lsa — mavzuingizga mos dizayn o‘ylab topamiz.\n\n"
            "<b>Ishimni boshqalarga ko‘rsatasizmi?</b> Yo‘q, faqat ruxsatingiz bilan."
        ),
        "faq_contact": "Savollar qoldimi? Yozing: @{admin}",
        "q_topic": "📝 1/7-qadam. <b>Taqdimot mavzusini</b> yozing:",
        "q_slides": "📊 2/7-qadam. Nechta <b>slayd</b> kerak?",
        "slides": {"s10": "10 gacha", "s20": "11–20", "s30": "21–30"},
        "q_deadline": "⏰ 3/7-qadam. Qaysi <b>muddatgacha</b>?",
        "deadline": {"d1": "⚡ Shoshilinch (+50%)", "d2": "📅 Odatiy — muddatni chatda kelishamiz", "d3": "🐢 Shoshilmayman"},
        "q_plang": "🌐 4/7-qadam. Taqdimot qaysi <b>tilda</b>?",
        "plang": {"ru": "Rus", "uz": "O‘zbek", "en": "Ingliz"},
        "q_design": (
            "🎨 5/7-qadam. <b>Dizayn</b>: sizda o‘z shabloningiz, korporativ uslub yoki "
            "qanday ko‘rinishi kerakligi haqida namuna bormi?"
        ),
        "design": {"own": "📎 O‘z dizaynim / shablonim bor", "ours": "✨ Mavzuga mos dizaynni o‘zingiz qiling"},
        "files_own_hint": "\n\n📎 <b>O‘z shabloningiz yoki dizayn namunasini yuborishni unutmang</b> (PPTX, PDF yoki skrinshotlar).",
        "q_extras": "➕ 6/7-qadam. Yana nima kerak? Belgilash uchun bosing, keyin «Davom etish».",
        "extra_text": "Matnni yozib berish (+5 000)",
        "extra_notes": "Konspekt (+5 000)",
        "next": "Davom etish ➡️",
        "q_files": (
            "📎 7/7-qadam. <b>Materiallarni</b> yuboring: matn, o‘qituvchi talablari, rasm, namunalar.\n"
            "Bir nechta fayl bo‘lishi mumkin. Tugatgach «Tayyor» tugmasini bosing."
        ),
        "files_got": "✅ Qabul qilingan fayllar: {n}. Yana yuboring yoki «Tayyor» ni bosing.",
        "btn_done": "✅ Tayyor",
        "btn_skip": "Material yo‘q",
        "q_contact": (
            "📞 Siz bilan qanday bog‘lanamiz? Raqamni yuborish uchun tugmani bosing "
            "yoki nik / telefonni matn bilan yozing."
        ),
        "btn_phone": "📱 Raqamni yuborish",
        "summary": (
            "🧾 <b>Sizning buyurtmangiz</b>\n\n"
            "Mavzu: {topic}\n"
            "Slaydlar: {slides}\n"
            "Muddat: {deadline}\n"
            "Til: {plang}\n"
            "Dizayn: {design}\n"
            "Qo‘shimcha: {extras}\n"
            "Fayllar: {files}\n\n"
            "💰 Taxminiy narx: <b>{price}</b>\n\n"
            "Hammasi to‘g‘rimi?"
        ),
        "price_fmt": "{n} so‘m",
        "price_fmt_from": "{n} so‘mdan",
        "extras_none": "—",
        "btn_confirm": "✅ Buyurtmani yuborish",
        "btn_restart": "🔄 Qaytadan to‘ldirish",
        "sent": (
            "🎉 Buyurtma yuborildi! Tez orada yozamiz va <b>bepul muqova</b> yuboramiz.\n"
            "Odatda bir soat ichida javob beramiz."
        ),
        "cancelled": "Buyurtma bekor qilindi. Menyuga qaytaman.",
        "use_buttons": "Iltimos, yuqoridagi tugmalardan birini tanlang 👆",
        "send_text": "Iltimos, matn bilan yozing.",
        "error_admin": "⚠️ Buyurtmani yuborib bo‘lmadi. To‘g‘ridan-to‘g‘ri yozing: @{admin}",
    },
}

# ───────────────────────── АНГЛИЙСКИЙ ─────────────────────────
T["en"] = {
    "choose_lang": "Выберите язык / Tilni tanlang / Choose language:",
    "welcome": ("👋 Hi! This is <b>SlideLab</b> — beautiful presentations made to order.\n\n"
                "🎨 A unique style for every topic: photos, illustrations, charts\n"
                "📝 Speaker notes for your talk\n"
                "🎁 Free cover — see the style first, pay later\n\n"
                "📎 Or just forward a lecture / assignment here — order in 2 taps\n\n"
                "Choose what you need 👇"),
    "btn_price": "💰 Prices",
    "btn_examples": "🎨 Our work",
    "btn_order": "💬 Order in chat",
    "btn_app": "✨ Order",
    "plan_names": {"week": "2 presentations", "month": "4 presentations", "vip": "VIP · 10 presentations"},
    "sub_req_sent": "📦 Your request for the «{plan}» pack is accepted! The pack is activated after payment — see what's left in the app: 👤 Profile.",
    "sub_on": "📦 The «{plan}» pack is active! Presentations available: {limit}, valid until {end}. Order as usual — each presentation is deducted from the pack.",
    "sub_line": "\n\n📦 Deducted from your pack: {cost}, left: {left}.",
    "sub_pay": " Extra to pay: {pay} UZS (urgency / text).",
    "sub_empty": "\n\n📦 Your pack is used up — this order is at the regular price. You can buy a new pack any time: «✨ Order» → 👤 Profile.",
    "sub_status": "📦 Your pack: {left} of {limit} presentations left, until {end}.",
    "btn_my": "📦 My orders",
    "my_empty": "📦 You have no orders yet. Tap «✨ Order» — it takes a couple of minutes.",
    "my_title": "📦 <b>Your orders</b>\n",
    "order_line": "\n\n📦 Order number: <b>#{id}</b>. Track the status in «📦 My orders».",
    "status_note": "📦 Order <b>#{id}</b> «{topic}»: {status}",
    "st": {"new": "🆕 Received", "cover": "🎨 Cover ready", "work": "🛠 In progress",
           "edit": "✏️ Making edits", "done": "✅ Done", "cancel": "✖️ Cancelled"},
    "done_hint": "\n\n✏️ Need to change something? Tap «Request edits» below — 2 rounds of edits are free.",
    "btn_edit": "✏️ Request edits #{id}",
    "menu_refresh": "📦 The status is updated in the app too: «✨ Order» → 👤 Profile.",
    "pres_saved": "🎞 The presentation is saved in the app: «✨ Order» → 👤 Profile → My presentations.",
    "edit_prompt": ("✏️ <b>Edits for order #{id}</b>\nWrite what to change (e.g. «slide 3 — a different chart») and send "
                    "screenshots or files — I'll pass everything on. When you're done, just go back to the menu."),
    "edit_got": "✅ Edits passed on. You can send more — text, screenshots, files.",
    "cv_ready": "🎨 The cover for order #{id} is ready! It's free. Do you like it?",
    "cv_ok": "👍 I like it — go on",
    "cv_chg": "✏️ I want changes",
    "cv_chg_prompt": "✏️ Write what to change on the cover (colour, style, photo, text) — a screenshot of an example helps.",
    "cv_go": "🚀 Great! We're starting the full presentation — we'll send it as soon as it's ready.",
    "cv_pay": "🙌 Great! Just the payment left — and we'll start the full presentation right away.",
    "pay_head": "💳 <b>Payment for order #{id}</b> — {sum} UZS\n\n",
    "pay_head_sub": "💳 <b>Payment for the «{plan}» pack</b> — {sum} UZS\n\n",
    "pay_cards": ("Transfer to any card (tap the number to copy it):\n{cards}{name}\n\n"
                  "After paying by card, tap «✅ I paid by card» and send a screenshot of the receipt."),
    "pay_name": "\nRecipient: <b>{n}</b>",
    "pay_order_note": ("🎁 The cover is free, no prepayment. You can pay now or after you like the cover — "
                       "then we start the full presentation right away.\n\n"),
    "pay_nocards": "The manager will tell you how to pay.",
    "btn_paid": "✅ I paid by card",
    "btn_stars": "⭐ Pay with Stars — {n} ⭐",
    "pay_or_stars": "\n\n⭐ Or pay with Telegram Stars — one tap, confirmed automatically.",
    "pay_stars_only": "Pay with Telegram Stars — button below, confirmation comes automatically.",
    "inv_order": "SlideLab presentation #{id}",
    "inv_order_d": "«{topic}» · {sl} slides. Payment for the full presentation (the cover is free).",
    "inv_sub": "Pack «{plan}»",
    "inv_sub_d": "Presentations: {limit}, valid for {days} days. The balance doesn't expire when you buy a new pack.",
    "inv_done": "Already paid 👍",
    "inv_credit": " Order #{id} credited (−{sum} UZS).",
    "cr_text": ("🔥 <b>Liked it? Let's make it cheaper!</b>\n\nTake a pack by <b>{date}</b> — this order ({sum} UZS) "
                "counts towards it. You only pay the difference:\n\n{lines}\n\nThe balance doesn't expire, order as usual."),
    "cr_line": "📦 {plan}: <s>{full}</s> → <b>{pay} UZS</b> · {more} more",
    "cr_btn": "📦 {plan} — pay {pay}",
    "cr_expired": "The credit period is over — you can buy a pack at the regular price in the app.",
    "paysupport": ("💬 Questions about payments and refunds: write here in the chat or to the manager @{admin} — "
                   "we'll help. If an order is cancelled before work starts, we refund the Stars."),
    "pay_send_check": "📸 Send a screenshot or photo of the payment receipt (or as text: amount, time, which card).",
    "pay_thanks": "🙏 Thank you! We'll check the payment and confirm — usually within an hour.",
    "paid_go": "✅ We received the payment for order #{id}, thank you! Starting the full presentation.",
    "deck_ready": "🎉 Your presentation for order #{id} is ready!",
    "fmt_ask": ("🎉 <b>Your presentation for order #{id} is ready!</b>\n\nWhich format should we send? Choose — it will come here, to the chat.\n"
                "Google Slides and Canva open in your own account: you edit it yourself, without ours."),
    "fmt_btn": {"pptx": "📊 PowerPoint (PPTX)", "pdf": "📄 PDF", "png": "🖼 As images", "gslides": "🟢 Google Slides", "canva": "🎨 Canva"},
    "fmt_all": "📦 All formats",
    "lnk_gslides": ("🟢 <b>Google Slides</b> — your own copy:\n{url}\n\nTap «Make a copy» — the presentation is saved to your Google Drive "
                    "and you can edit it however you like (any Google account works)."),
    "lnk_canva": ("🎨 <b>Canva</b> — your own copy:\n{url}\n\nOpen the link and tap «Use template» — a copy appears in your Canva "
                  "account (a free one works) and you can edit it as much as you want."),
    "fmt_sending": "Sending…",
    "how_gslides": ("🟢 <b>How to open in Google Slides</b> (in your own account):\n"
                    "1. Save the PPTX file above\n2. Open drive.google.com → «New» → «File upload»\n"
                    "3. Click the file → «Open with Google Slides» — and edit"),
    "how_canva": ("🎨 <b>How to open in Canva</b> (in your own account, a free one works):\n"
                  "1. Save the PPTX file above\n2. In Canva tap «Create a design» → «Import file»\n"
                  "3. Choose the PPTX — all slides become editable"),
    "fmt_none": "Couldn't find a file in this format — write to us and we'll send it.",
    "fmt_more": "\n\n📎 Need another format — tap a button in the message above again.",
    "gift_text": "Thank you for choosing SlideLab! May your presentations always get top marks 🎓",
    "gift_sent": "🎁 SlideLab promo: a gift for buying a pack! It's already in your Telegram profile.",
    "paid_early": ("✅ We received the payment for order #{id}, thank you! First we'll send the cover — "
                   "as soon as you approve it, we make the full presentation."),
    "q_sent": "✅ Question sent! We'll reply right here in the chat.",
    "ask_prompt": "❓ Write your question in one message — I'll pass it to the manager.",
    "reply_prefix": "💬 <b>SlideLab reply:</b>",
    "app_sent": ("🎉 Request sent! We'll message you soon and send a <b>free cover</b>.\n\n"
                 "If you have files (text, template, requirements), just send them here."),
    "app_file_ok": "✅ Passed on. You can send more.",
    "app_sent_src": ("🎉 Request sent! We'll message you soon and send a <b>free cover</b>.\n\n"
                     "📎 <b>Now forward your sources here</b> straight from other chats — no need to save them to your phone.\n"
                     "How: press and hold the message with the file → «Forward» → choose this bot.\n\n"
                     "Any files work (PDF, Word, PowerPoint, Excel, photos, video, audio, archives) and links."),
    "sources": "Sources",
    "tpl": "Template",
    "tpl_ask": ("\n\n🎨 <b>Forward the template file here</b> (PPTX, PDF, screenshots) or a link to it (Google Slides, Canva). "
                "🔓 For a link, open access: «Anyone with the link»."),
    "qf_ask": "📎 Got the file! We'll make a presentation from it.\n\nHow many <b>slides</b>? 👇",
    "qf_deadline": "⏰ By what <b>deadline</b>?",
    "qf_more": "✅ File added (total: {n}). Choose an option with the button above 👆",
    "comment": "Wishes",
    "btn_faq": "❓ FAQ",
    "btn_lang": "🌐 Language",
    "price": ("📌 <b>PRICES</b>\n\n"
              "🟢 Mini — up to 10 slides — 19 000 UZS\n"
              "🎁 <b>First Mini order — 9 900 UZS</b>\n"
              "🔵 Standard — 11–20 slides — 29 000 UZS\n"
              "🟣 Large — 21–30 slides — 39 000 UZS\n\n"
              "⚡ Urgent (up to 20 slides): +50%\n"
              "➕ Full text written for you: +5 000 UZS\n"
              "➕ Speaker notes: +5 000 UZS\n"
              "✏️ 2 rounds of edits free\n\n"
              "✅ Included: unique design, photos and illustrations, charts, PPTX + PDF"),
    "examples": "🎨 All our work and styles are in our channel:\n{url}",
    "examples_caption": "🎨 Examples of our work. Every presentation has its own style for the topic.",
    "examples_soon": "🎨 Examples will appear here soon. Meanwhile tap «✨ Order» — we'll send a free cover in the style of your topic 🎁",
    "faq": ("❓ <b>FAQ</b>\n\n"
            "<b>How fast?</b> We agree the deadline in the chat before starting and keep it — usually within a day. "
            "Very urgent — «Urgent» (up to 20 slides), +50%.\n\n"
            "<b>How to pay?</b> The cover is free. If you like it, you pay for the order: by Uzum Bank / Payme / Zoomrad card "
            "(the bot sends the details) or with Telegram Stars in one tap.\n\n"
            "<b>What if I don't like it?</b> First we make a free cover. Then 2 rounds of edits are free. "
            "If it still doesn't fit after the edits, we refund the payment.\n\n"
            "<b>What format?</b> PPTX (PowerPoint, Google Slides) and PDF.\n\n"
            "<b>No text?</b> We'll write it (+5 000 UZS).\n\n"
            "<b>Have your own template or brand style?</b> Send it — we'll design in it. If not, we'll create a design for your topic.\n\n"
            "<b>Will my work be shown to others?</b> No, only with your permission."),
    "faq_contact": "Still have questions? Write: @{admin}",
    "q_topic": "📝 Step 1/7. Write the <b>presentation topic</b>:",
    "q_slides": "📊 Step 2/7. How many <b>slides</b>?",
    "slides": {"s10": "up to 10", "s20": "11–20", "s30": "21–30"},
    "q_deadline": "⏰ Step 3/7. By what <b>deadline</b>?",
    "deadline": {"d1": "⚡ Urgent (+50%)", "d2": "📅 Regular — we'll agree the deadline in the chat", "d3": "🐢 No rush"},
    "q_plang": "🌐 Step 4/7. What <b>language</b> is the presentation in?",
    "plang": {"ru": "Russian", "uz": "Uzbek", "en": "English"},
    "q_design": "🎨 Step 5/7. <b>Design</b>: do you have your own template, brand style or an example of how it should look?",
    "design": {"own": "📎 I have my own design / template", "ours": "✨ Create a design for the topic"},
    "files_own_hint": "\n\n📎 <b>Don't forget to send your template or a design example</b> (PPTX, PDF or screenshots).",
    "q_extras": "➕ Step 6/7. Anything else? Tap to select, then «Next».",
    "extra_text": "Full text (+5 000)",
    "extra_notes": "Speaker notes (+5 000)",
    "next": "Next ➡️",
    "q_files": ("📎 Step 7/7. Send the <b>materials</b>: text, teacher's requirements, photos, examples.\n"
                "You can send several files. When you're done, tap «Done»."),
    "files_got": "✅ Files received: {n}. Send more or tap «Done».",
    "btn_done": "✅ Done",
    "btn_skip": "No materials",
    "q_contact": "📞 How can we reach you? Tap the button to share your number, or write your username / phone.",
    "btn_phone": "📱 Share my number",
    "summary": ("🧾 <b>Your request</b>\n\nTopic: {topic}\nSlides: {slides}\nDeadline: {deadline}\nLanguage: {plang}\n"
                "Design: {design}\nExtras: {extras}\nFiles: {files}\n\n💰 Estimated price: <b>{price}</b>\n\nIs everything correct?"),
    "price_fmt": "{n} UZS",
    "price_fmt_from": "from {n} UZS",
    "extras_none": "—",
    "btn_confirm": "✅ Send request",
    "btn_restart": "🔄 Start over",
    "sent": "🎉 Request sent! We'll message you soon and send a <b>free cover</b>.\nWe usually reply within an hour.",
    "cancelled": "Request cancelled. Back to the menu.",
    "use_buttons": "Please choose an option with the button above 👆",
    "send_text": "Please write it as text.",
    "error_admin": "⚠️ Couldn't send the request. Write directly: @{admin}",
}


# ───────────────────────── СОСТОЯНИЯ АНКЕТЫ ─────────────────────────
class Order(StatesGroup):
    topic = State()
    slides = State()
    deadline = State()
    plang = State()
    design = State()
    extras = State()
    files = State()
    contact = State()
    confirm = State()
    after_app = State()   # заявка из приложения уже отправлена, ждём файлы (необязательно)
    quick = State()       # клиент переслал файл — быстрый заказ в 2 нажатия
    ask = State()         # клиент пишет вопрос менеджеру
    edit = State()        # клиент присылает правки к готовому заказу
    paycheck = State()    # клиент присылает чек об оплате


router = Router()
admin_router = Router()   # ответы владельца клиентам (реплаем)


async def get_lang(state: FSMContext) -> str:
    data = await state.get_data()
    return data.get("lang", "ru")


def load_orders() -> dict:
    try:
        return json.loads(ORDERS_DB.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {"last_id": 0, "orders": {}}


def save_orders(db: dict) -> None:
    ORDERS_DB.write_text(json.dumps(db, ensure_ascii=False, indent=1), encoding="utf-8")
    refresh_menu_buttons(db)


# ───── Кнопка «Открыть» у каждого клиента — со своими заказами ─────
# Приложение без сервера: список «Мои работы» зашит в ссылку. Общая кнопка меню открывала
# приложение без заказов, поэтому ставим каждому клиенту личную кнопку и обновляем её,
# когда у его заказов что-то меняется.
_BOT_REF: list = []
_MENU_URL: dict = {}
_MENU_TEXT = {"ru": "Открыть", "uz": "Ochish", "en": "Open"}


def refresh_menu_buttons(db: dict | None = None, only_uid: int | None = None) -> None:
    if not _BOT_REF or not MINIAPP_URL.startswith("https://"):
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    db = db or load_orders()
    langs: dict = {}
    for o in sorted(db["orders"].values(), key=lambda o: o["id"]):
        if o.get("uid"):
            langs[o["uid"]] = o.get("lang", "ru") if o.get("lang") in _MENU_TEXT else "ru"
    if only_uid is not None:
        langs = {only_uid: langs.get(only_uid, "ru")}
    from aiogram.types import MenuButtonWebApp
    for uid, lang in langs.items():
        url = app_url(lang, uid)
        if _MENU_URL.get(uid) == url:
            continue
        _MENU_URL[uid] = url

        async def _set(uid=uid, lang=lang, url=url):
            try:
                await _BOT_REF[0].set_chat_menu_button(chat_id=uid, menu_button=MenuButtonWebApp(
                    text=_MENU_TEXT[lang], web_app=WebAppInfo(url=url)))
            except Exception as e:  # noqa: BLE001
                _MENU_URL.pop(uid, None)
                logging.warning("Кнопка меню для %s: %s", uid, e)
        loop.create_task(_set())


def user_orders(uid: int) -> list[dict]:
    db = load_orders()
    return sorted((o for o in db["orders"].values() if o.get("uid") == uid),
                  key=lambda o: o["id"], reverse=True)


def load_subs() -> dict:
    try:
        return json.loads(SUBS_DB.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def save_subs(db: dict) -> None:
    SUBS_DB.write_text(json.dumps(db, ensure_ascii=False, indent=1), encoding="utf-8")
    refresh_menu_buttons()


def active_sub(uid: int) -> dict | None:
    sub = load_subs().get(str(uid))
    if not sub or datetime.now().strftime("%Y-%m-%d") > sub["end"]:
        return None
    sub.setdefault("limit", PLANS[sub["plan"]]["limit"])
    sub["left"] = sub["limit"] - sub.get("used", 0)
    return sub


def activate_sub(uid: int, plan: str, minus: int = 0) -> dict:
    from datetime import timedelta
    db = load_subs()
    today = datetime.now().strftime("%Y-%m-%d")
    end = (datetime.now() + timedelta(days=PLANS[plan]["days"])).strftime("%Y-%m-%d")
    limit = PLANS[plan]["limit"] - minus   # minus — презентации, уже засчитанные из прошлого заказа
    old = db.get(str(uid))
    if old and old["end"] >= today:  # пакеты складываются: остаток + новый, срок — самый дальний
        limit += max(0, old.get("limit", PLANS[old["plan"]]["limit"]) - old.get("used", 0))
        end = max(end, old["end"])
        if old["plan"] == "vip":
            plan = "vip"
    db[str(uid)] = {"plan": plan, "start": today, "end": end, "used": 0, "limit": limit}
    save_subs(db)
    return db[str(uid)]


def use_sub(uid: int, cost: int) -> None:
    db = load_subs()
    if str(uid) in db:
        db[str(uid)]["used"] = max(0, db[str(uid)].get("used", 0) + cost)
        save_subs(db)


def fmt_date(d: str) -> str:
    return f"{d[8:10]}.{d[5:7]}"


def app_url(lang: str, uid: int | None) -> str:
    """Ссылка на приложение. Последние заказы клиента зашиты в ссылку (сервера у нас нет)."""
    url = f"{MINIAPP_URL}?lang={lang}"
    if uid:
        mine = []
        for o in [x for x in user_orders(uid) if not x.get("hidden")][:8]:
            row = [o["id"], o["topic"][:32], o["slides"], o["status"], o["price"]]
            view = (o.get("deliver_links") or {}).get("view", "")
            if o.get("link") or o.get("has_file") or view:
                row += [(o.get("link") or "")[:120], 1 if o.get("has_file") else 0, view[:160],
                        ",".join(_app_formats(o))]
            mine.append(row)
        if mine:
            raw = json.dumps(mine, ensure_ascii=False, separators=(",", ":")).encode()
            url += "&o=" + base64.urlsafe_b64encode(raw).decode().rstrip("=")
        if FIRST_PRICE and is_new_client(uid):
            url += f"&n={FIRST_PRICE}"
        sub = active_sub(uid)
        if sub:
            url += f"&s={sub['plan']}.{sub['left']}.{sub['limit']}.{sub['end']}"
    return url


def _app_formats(o: dict) -> list[str]:
    """Какие кнопки «Скачать» показать в приложении у готового заказа."""
    if not o.get("deliver_dir"):
        return []
    fm = [x for x in formats_of([Path(n) for n in o.get("deliver_files", [])]) if x != "docx"]
    links = o.get("deliver_links") or {}
    fm += [k for k in ("gslides", "canva") if k in links or "pptx" in fm]
    return fm


def main_menu(lang: str, uid: int | None = None) -> ReplyKeyboardMarkup:
    t = T[lang]
    uid = uid or CURRENT_USER.get()
    return ReplyKeyboardMarkup(
        keyboard=[
            *([[KeyboardButton(text=t["btn_app"], web_app=WebAppInfo(url=app_url(lang, uid)))]]
              if MINIAPP_URL.startswith("https://") else []),
            [KeyboardButton(text=t["btn_price"]), KeyboardButton(text=t["btn_examples"])],
            [KeyboardButton(text=t["btn_faq"]), KeyboardButton(text=t["btn_order"])],
            [KeyboardButton(text=t["btn_my"]), KeyboardButton(text=t["btn_lang"])],
        ],
        resize_keyboard=True,
    )


def lang_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="🇷🇺 Русский", callback_data="lang:ru")
    kb.button(text="🇺🇿 O‘zbekcha", callback_data="lang:uz")
    kb.button(text="🇬🇧 English", callback_data="lang:en")
    kb.adjust(3)
    return kb.as_markup()


def options_kb(prefix: str, options: dict, cols: int = 2):
    kb = InlineKeyboardBuilder()
    for key, label in options.items():
        kb.button(text=label, callback_data=f"{prefix}:{key}")
    kb.adjust(cols)
    return kb.as_markup()


def extras_kb(lang: str, need_text: bool, need_notes: bool):
    t = T[lang]
    kb = InlineKeyboardBuilder()
    kb.button(text=("✅ " if need_text else "⬜ ") + t["extra_text"], callback_data="ex:text")
    kb.button(text=("✅ " if need_notes else "⬜ ") + t["extra_notes"], callback_data="ex:notes")
    kb.button(text=t["next"], callback_data="ex:next")
    kb.adjust(1)
    return kb.as_markup()


def files_kb(lang: str):
    t = T[lang]
    kb = InlineKeyboardBuilder()
    kb.button(text=t["btn_done"], callback_data="files:done")
    kb.button(text=t["btn_skip"], callback_data="files:skip")
    kb.adjust(2)
    return kb.as_markup()


def confirm_kb(lang: str):
    t = T[lang]
    kb = InlineKeyboardBuilder()
    kb.button(text=t["btn_confirm"], callback_data="ok:send")
    kb.button(text=t["btn_restart"], callback_data="ok:restart")
    kb.adjust(1)
    return kb.as_markup()


def all_button_texts(key: str) -> set[str]:
    return {T[lg][key] for lg in T}


# ───────────────────────── СТАРТ И МЕНЮ ─────────────────────────
@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, command: CommandObject):
    if (command.args or "").startswith("edit_") and (command.args or "")[5:].isdigit():
        if await start_edit(message, state, int(command.args[5:]), message.from_user.id):
            return
    if (command.args or "").startswith("hide_") and (command.args[5:].isdigit() or command.args[5:] == "all"):
        await app_hide_order(message, command.args[5:])
        return
    if (command.args or "").startswith("get_"):
        parts = command.args.split("_")
        if len(parts) == 3:
            await app_get_format(message, parts[1], parts[2])
            return
    if (command.args or "").startswith("sub_") and command.args[4:] in PLANS:
        await request_sub(message, state, command.args[4:])
        return
    if (command.args or "") == "ask":
        lang = await get_lang(state)
        await state.set_state(Order.ask)
        await message.answer(T[lang]["ask_prompt"])
        return
    d = decode_start_code(command.args or "")
    if d:
        await handle_app_order(message, state, d)
        return
    await state.clear()
    await message.answer(T["ru"]["choose_lang"], reply_markup=lang_kb())


@router.message(Command("id"))
async def cmd_id(message: Message):
    """Помогает владельцу узнать свой Telegram ID для настройки ADMIN_ID."""
    await message.answer(f"Ваш Telegram ID: <code>{message.from_user.id}</code>")


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    lang = await get_lang(state)
    await state.clear()
    await state.update_data(lang=lang)
    await message.answer(T[lang]["cancelled"], reply_markup=main_menu(lang))


@router.callback_query(F.data.startswith("lang:"))
async def set_lang(cb: CallbackQuery, state: FSMContext):
    lang = cb.data.split(":")[1]
    await state.clear()
    await state.update_data(lang=lang)
    await cb.message.edit_reply_markup(reply_markup=None)
    await cb.message.answer(T[lang]["welcome"], reply_markup=main_menu(lang))
    await cb.answer()


@router.message(F.text.in_(all_button_texts("btn_lang")))
async def menu_lang(message: Message, state: FSMContext):
    await message.answer(T["ru"]["choose_lang"], reply_markup=lang_kb())


@router.message(F.text.in_(all_button_texts("btn_price")))
async def menu_price(message: Message, state: FSMContext):
    lang = await get_lang(state)
    await message.answer(T[lang]["price"])


def channel_ok() -> bool:
    """Ссылка на канал задана и это не ссылка на самого бота."""
    url = CHANNEL_URL.lower().rstrip("/")
    return bool(url) and "t.me/" in url and not url.endswith("bot")


def portfolio_images() -> list[Path]:
    if not PORTFOLIO_DIR.is_dir():
        return []
    files = [p for p in sorted(PORTFOLIO_DIR.iterdir())
             if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp")]
    return files[:10]  # Telegram: максимум 10 фото в одном альбоме


@router.message(F.text.in_(all_button_texts("btn_examples")))
async def menu_examples(message: Message, state: FSMContext):
    lang = await get_lang(state)
    images = portfolio_images()
    if images:
        media = [InputMediaPhoto(media=FSInputFile(p)) for p in images]
        media[0].caption = T[lang]["examples_caption"]
        try:
            await message.answer_media_group(media)
        except Exception as e:  # noqa: BLE001
            logging.exception("Не удалось отправить портфолио: %s", e)
            images = []
    if channel_ok():
        await message.answer(T[lang]["examples"].format(url=CHANNEL_URL))
    elif not images:
        await message.answer(T[lang]["examples_soon"])


@router.message(F.text.in_(all_button_texts("btn_faq")))
async def menu_faq(message: Message, state: FSMContext):
    lang = await get_lang(state)
    text = T[lang]["faq"]
    if ADMIN_USERNAME:
        text += "\n\n" + T[lang]["faq_contact"].format(admin=ADMIN_USERNAME)
    await message.answer(text)


# ───────────────────────── АНКЕТА ЗАКАЗА ─────────────────────────
@router.message(F.web_app_data)
async def order_from_app(message: Message, state: FSMContext):
    """Заявка из Mini App: данные анкеты приходят одним JSON, дальше — файлы и подтверждение."""
    try:
        d = json.loads(message.web_app_data.data)
    except Exception:  # noqa: BLE001
        d = {}
    if d.get("type") == "sub" and d.get("plan") in PLANS:
        await request_sub(message, state, d["plan"], d.get("lang"))
        return
    if d.get("type") == "edit":
        try:
            oid = int(d.get("id"))
        except Exception:  # noqa: BLE001
            oid = 0
        if oid and await start_edit(message, state, oid, message.from_user.id, quiet=True):
            await forward_edit(message, state, message.bot, text=str(d.get("text", ""))[:1500])
        return
    if d.get("type") == "q":
        await send_question(message, state, str(d.get("text", ""))[:1500], d.get("lang"))
        return
    if d.get("type") == "hide":
        await app_hide_order(message, str(d.get("id", "")))
        return
    if d.get("type") == "get":
        await app_get_format(message, str(d.get("id", "")), str(d.get("fmt", "")))
        return
    await handle_app_order(message, state, d)


_HIDE_OK = {"ru": "🗑 Убрал #{id} из «Мои работы». Файлы в чате остались.",
            "uz": "🗑 #{id} «Ishlarim»dan olib tashlandi. Chatdagi fayllar qoldi.",
            "en": "🗑 Removed #{id} from «My work». Files in the chat are still here."}


async def app_hide_order(message: Message, oid: str) -> None:
    """Клиент убирает готовый/отменённый заказ из списка в приложении (данные у нас сохраняются)."""
    db = load_orders()
    mine = [o for o in db["orders"].values() if o.get("uid") == message.from_user.id
            and o.get("status") in ("done", "cancel") and not o.get("hidden")]
    if oid != "all":
        mine = [o for o in mine if str(o["id"]) == oid]
    if not mine:
        return
    for o in mine:
        o["hidden"] = True
    save_orders(db)   # здесь же обновится личная кнопка «Открыть»
    lang = mine[-1].get("lang", "ru") if mine[-1].get("lang") in _HIDE_OK else "ru"
    ids = ", #".join(str(o["id"]) for o in mine)
    await message.answer(_HIDE_OK[lang].format(id=ids), reply_markup=main_menu(lang, message.from_user.id))


async def app_get_format(message: Message, oid: str, choice: str) -> None:
    """Кнопка «Скачать» в приложении → бот присылает файл/ссылку в нужном формате."""
    o = load_orders()["orders"].get(oid) or {}
    if not oid.isdigit() or o.get("uid") != message.from_user.id or choice not in (
            "pptx", "pdf", "png", "gslides", "canva", "all"):
        return
    t = T[o.get("lang", "ru")]
    key = (message.from_user.id, oid, choice)
    now = asyncio.get_event_loop().time()
    if now - _FMT_RECENT.get(key, -1e9) < 60:
        return
    _FMT_RECENT[key] = now
    await message.answer(t["fmt_sending"])
    if not await deliver_formats(message.bot, oid, choice):
        await message.answer(t["fmt_none"])


async def send_question(message: Message, state: FSMContext, text: str, lang: str | None = None):
    lang = lang if lang in T else await get_lang(state)
    u = message.from_user
    who = f"@{u.username}" if u.username else "(без ника)"
    try:
        await message.bot.send_message(
            ADMIN_ID,
            f"❓ <b>ВОПРОС</b>\nКлиент: {html.escape(u.full_name)} {who}\nID: <code>{u.id}</code>\n\n"
            f"{html.escape(text)}\n\n<i>Ответьте (reply) на это сообщение — я перешлю ответ клиенту.</i>")
        await message.answer(T[lang]["q_sent"], reply_markup=main_menu(lang))
    except Exception as e:  # noqa: BLE001
        logging.exception("Не удалось отправить вопрос: %s", e)
        await message.answer(T[lang]["error_admin"].format(admin=ADMIN_USERNAME or "slidelab_uz"))
    await state.set_state(None)


def decode_start_code(code: str) -> dict | None:
    """Заявка из приложения, открытого кнопкой «Открыть» (приходит как /start o...)."""
    if len(code) < 8 or code[0] != "o":
        return None
    try:
        b = code[8:]
        topic = base64.urlsafe_b64decode(b + "=" * (-len(b) % 4)).decode("utf-8", "ignore")
        return {
            "slides": {"1": "s10", "2": "s20", "3": "s30"}[code[1]],
            "deadline": {"1": "d1", "2": "d2", "3": "d3"}[code[2]],
            "plang": {"r": "ru", "u": "uz", "e": "en"}[code[3]],
            "design": "own" if code[4] == "w" else "ours",
            "text": code[5] == "1", "notes": code[6] == "1",
            "lang": {"u": "uz", "e": "en"}.get(code[7].lower(), "ru"),
            "humor": code[7].isupper(),  # заглавная буква языка = «С юмором»
            "topic": topic + ("…" if len(code) >= 64 else ""),
        }
    except Exception:  # noqa: BLE001
        return None


async def handle_app_order(message: Message, state: FSMContext, d: dict):
    lang = d.get("lang") if d.get("lang") in T else await get_lang(state)
    t = T[lang]
    slides = d.get("slides") if d.get("slides") in PACKAGES else None
    deadline = d.get("deadline") if d.get("deadline") in t["deadline"] else "d2"
    if slides == "s30" and deadline == "d1":
        deadline = "d2"
    topic = str(d.get("topic", "")).strip()[:300]
    if not slides or not topic:
        await message.answer(t["use_buttons"], reply_markup=main_menu(lang))
        return
    await state.clear()
    await state.set_data({
        "lang": lang, "from_app": True, "files": [],
        "topic": topic, "slides": slides, "deadline": deadline,
        "plang": d.get("plang") if d.get("plang") in t["plang"] else lang,
        "design": "own" if d.get("design") == "own" else "ours",
        "need_text": bool(d.get("text")), "need_notes": bool(d.get("notes")),
        "need_humor": bool(d.get("humor")),
        "contact": str(d.get("contact", "")).strip()[:60],
        "comment": ((f"Стиль из витрины: {str(d.get('style'))[:40]}. " if d.get("style") else "")
                    + str(d.get("comment", "")).strip())[:450],
        "sources": str(d.get("sources", "")).strip()[:1500],
        "srcfiles": bool(d.get("srcfiles")),
        "dlink": str(d.get("dlink", "")).strip()[:500],
    })
    if not (await state.get_data()).get("contact"):
        u = message.from_user
        await state.update_data(contact=f"@{u.username}" if u.username else "Telegram")
    ok = await deliver_order(message.bot, message.from_user, state)
    if not ok:
        await message.answer(t["error_admin"].format(admin=ADMIN_USERNAME or "slidelab_uz"),
                             reply_markup=main_menu(lang))
        await state.clear()
        await state.update_data(lang=lang)
        return
    await state.set_state(Order.after_app)
    need_tpl = d.get("design") == "own" and not str(d.get("dlink", "")).strip()
    await message.answer((t["app_sent_src"] if d.get("srcfiles") else t["app_sent"])
                         + (t["tpl_ask"] if need_tpl else "")
                         + t["order_line"].format(id=ok) + (await state.get_data()).get("sub_note", ""), reply_markup=main_menu(lang))


@router.message(Order.after_app, F.document | F.photo | F.video | F.audio | F.voice | F.video_note | F.animation | (F.text & ~F.text.in_(
    set().union(*(all_button_texts(k) for k in ("btn_order", "btn_price", "btn_examples", "btn_faq", "btn_lang", "btn_my", "btn_app"))))))
async def after_app_file(message: Message, state: FSMContext, bot: Bot):
    """Файлы после заявки из приложения — сразу пересылаем владельцу."""
    lang = await get_lang(state)
    u = message.from_user
    who = f"@{u.username}" if u.username else u.full_name
    group = message.media_group_id
    first_in_group = not group or (await state.get_data()).get("last_group") != group
    try:
        if first_in_group:
            await bot.send_message(ADMIN_ID, f"📎 Материал к заявке от {html.escape(who)} (ID <code>{u.id}</code>):")
        await bot.copy_message(ADMIN_ID, from_chat_id=u.id, message_id=message.message_id)
        oid = (await state.get_data()).get("order_id")
        if oid:
            asyncio.create_task(save_refs(bot, oid, [media_ref(message)]))
        if group:
            await state.update_data(last_group=group)
        if first_in_group:
            await message.answer(T[lang]["app_file_ok"])
    except Exception as e:  # noqa: BLE001
        logging.exception("Не удалось переслать файл: %s", e)
        await message.answer(T[lang]["error_admin"].format(admin=ADMIN_USERNAME or "slidelab_uz"))


@router.message(F.text.in_(all_button_texts("btn_order")))
async def order_start(message: Message, state: FSMContext):
    lang = await get_lang(state)
    await state.set_data({"lang": lang, "files": [], "need_text": False, "need_notes": False})
    await state.set_state(Order.topic)
    await message.answer(T[lang]["q_topic"], reply_markup=ReplyKeyboardRemove())


@router.message(Order.topic)
async def order_topic(message: Message, state: FSMContext):
    lang = await get_lang(state)
    if not message.text:
        await message.answer(T[lang]["send_text"])
        return
    await state.update_data(topic=message.text.strip()[:500])
    await state.set_state(Order.slides)
    await message.answer(T[lang]["q_slides"], reply_markup=options_kb("sl", T[lang]["slides"]))


@router.callback_query(Order.slides, F.data.startswith("sl:"))
async def order_slides(cb: CallbackQuery, state: FSMContext):
    lang = await get_lang(state)
    await state.update_data(slides=cb.data.split(":")[1])
    await state.set_state(Order.deadline)
    await cb.message.edit_reply_markup(reply_markup=None)
    opts = dict(T[lang]["deadline"])
    if cb.data.split(":")[1] == "s30":
        opts.pop("d1", None)  # срочно — только до 20 слайдов
    await cb.message.answer(T[lang]["q_deadline"], reply_markup=options_kb("dl", opts, 1))
    await cb.answer()


@router.callback_query(Order.deadline, F.data.startswith("dl:"))
async def order_deadline(cb: CallbackQuery, state: FSMContext):
    lang = await get_lang(state)
    await state.update_data(deadline=cb.data.split(":")[1])
    await state.set_state(Order.plang)
    await cb.message.edit_reply_markup(reply_markup=None)
    await cb.message.answer(T[lang]["q_plang"], reply_markup=options_kb("pl", T[lang]["plang"], 3))
    await cb.answer()


@router.callback_query(Order.plang, F.data.startswith("pl:"))
async def order_plang(cb: CallbackQuery, state: FSMContext):
    lang = await get_lang(state)
    await state.update_data(plang=cb.data.split(":")[1])
    await state.set_state(Order.design)
    await cb.message.edit_reply_markup(reply_markup=None)
    await cb.message.answer(T[lang]["q_design"], reply_markup=options_kb("ds", T[lang]["design"], 1))
    await cb.answer()


@router.callback_query(Order.design, F.data.startswith("ds:"))
async def order_design(cb: CallbackQuery, state: FSMContext):
    lang = await get_lang(state)
    await state.update_data(design=cb.data.split(":")[1])
    await state.set_state(Order.extras)
    await cb.message.edit_reply_markup(reply_markup=None)
    await cb.message.answer(T[lang]["q_extras"], reply_markup=extras_kb(lang, False, False))
    await cb.answer()


@router.callback_query(Order.extras, F.data.startswith("ex:"))
async def order_extras(cb: CallbackQuery, state: FSMContext):
    lang = await get_lang(state)
    data = await state.get_data()
    action = cb.data.split(":")[1]
    if action == "text":
        await state.update_data(need_text=not data.get("need_text"))
    elif action == "notes":
        await state.update_data(need_notes=not data.get("need_notes"))
    elif action == "next":
        await state.set_state(Order.files)
        await cb.message.edit_reply_markup(reply_markup=None)
        hint = T[lang]["files_own_hint"] if data.get("design") == "own" else ""
        await cb.message.answer(T[lang]["q_files"] + hint, reply_markup=files_kb(lang))
        await cb.answer()
        return
    data = await state.get_data()
    await cb.message.edit_reply_markup(
        reply_markup=extras_kb(lang, data.get("need_text"), data.get("need_notes"))
    )
    await cb.answer()


@router.message(Order.files, F.document | F.photo | F.video | F.audio | F.voice | F.video_note | F.animation | F.text)
async def order_files_add(message: Message, state: FSMContext):
    """Принимаем файлы, фото и текст-материалы (сохраняем id сообщений, чтобы переслать владельцу)."""
    lang = await get_lang(state)
    data = await state.get_data()
    files = data.get("files", [])
    files.append(message.message_id)
    await state.update_data(files=files, refs=data.get("refs", []) + [media_ref(message)])
    await message.answer(T[lang]["files_got"].format(n=len(files)), reply_markup=files_kb(lang))


@router.callback_query(Order.files, F.data.startswith("files:"))
async def order_files_done(cb: CallbackQuery, state: FSMContext):
    lang = await get_lang(state)
    if cb.data == "files:skip":
        await state.update_data(files=[])
    await cb.message.edit_reply_markup(reply_markup=None)
    data = await state.get_data()
    if data.get("from_app"):
        # из приложения: контакт необязателен — Telegram-ник у нас уже есть
        if not data.get("contact"):
            u = cb.from_user
            await state.update_data(contact=f"@{u.username}" if u.username else "Telegram")
        await state.set_state(Order.confirm)
        await cb.message.answer(await build_summary(state), reply_markup=confirm_kb(lang))
        await cb.answer()
        return
    await state.set_state(Order.contact)
    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=T[lang]["btn_phone"], request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
    await cb.message.answer(T[lang]["q_contact"], reply_markup=kb)
    await cb.answer()


@router.message(Order.contact, F.contact | F.text)
async def order_contact(message: Message, state: FSMContext):
    lang = await get_lang(state)
    if message.contact:
        contact = message.contact.phone_number
    else:
        contact = message.text.strip()[:100]
    await state.update_data(contact=contact)
    await state.set_state(Order.confirm)
    await message.answer("👌", reply_markup=ReplyKeyboardRemove())
    await message.answer(await build_summary(state), reply_markup=confirm_kb(lang))


async def build_summary(state: FSMContext, for_admin: bool = False) -> str:
    data = await state.get_data()
    lang = "ru" if for_admin else data.get("lang", "ru")
    t = T[lang]
    price, is_from = calc_price(
        data["slides"], data["deadline"], data.get("need_text"), data.get("need_notes")
    )
    extras = []
    if data.get("need_text"):
        extras.append(t["extra_text"])
    if data.get("need_notes"):
        extras.append(t["extra_notes"])
    if data.get("need_humor"):
        extras.append({"uz": "😄 Hazil bilan", "en": "😄 With humor"}.get(lang, "😄 С юмором"))
    price_str = t["price_fmt_from" if is_from else "price_fmt"].format(n=fmt_sum(price))
    return t["summary"].format(
        topic=html.escape(data.get("topic", "")),
        slides=t["slides"][data["slides"]],
        deadline=t["deadline"][data["deadline"]],
        plang=t["plang"][data["plang"]],
        design=t["design"].get(data.get("design", "ours"), "—"),
        extras=", ".join(extras) if extras else t["extras_none"],
        files=len(data.get("files", [])),
        price=price_str,
    ).replace("\n\n💰", (f"\n{t['comment']}: {html.escape(data['comment'])}" if data.get("comment") else "")
              + (f"\n🎨 {t['tpl']}: {html.escape(data['dlink'])}" if data.get("dlink") else "")
              + (f"\n📚 {t['sources']}:\n{html.escape(data['sources'])[:1500]}" if data.get("sources") else "")
              + ("\n📎 Файлы-источники пришлёт в чат" if data.get("srcfiles") else "") + "\n\n💰", 1)


@router.callback_query(Order.confirm, F.data == "ok:restart")
async def order_restart(cb: CallbackQuery, state: FSMContext):
    lang = await get_lang(state)
    await cb.message.edit_reply_markup(reply_markup=None)
    await state.set_data({"lang": lang, "files": [], "need_text": False, "need_notes": False})
    await state.set_state(Order.topic)
    await cb.message.answer(T[lang]["q_topic"])
    await cb.answer()


def status_kb(oid: int, current: str):
    kb = InlineKeyboardBuilder()
    for code, label in T["ru"]["st"].items():
        if code != "new":
            kb.button(text=("• " if code == current else "") + label, callback_data=f"st:{oid}:{code}")
    o = load_orders()["orders"].get(str(oid)) or {}
    kb.button(text="✅ Оплачено" if o.get("paid") else "💰 Отметить оплату", callback_data=f"paid:{oid}")
    kb.adjust(2)
    return kb.as_markup()


async def deliver_order(bot: Bot, user, state: FSMContext) -> int:
    """Отправляет заявку владельцу, сохраняет в orders.csv и orders.json. Возвращает номер (0 — не дошла)."""
    lang = await get_lang(state)
    data = await state.get_data()
    first = first_discount(data["slides"])
    price, _ = calc_price(data["slides"], data["deadline"], data.get("need_text"), data.get("need_notes"))
    db = load_orders()
    oid = db["last_id"] + 1
    t_cl = T[lang]
    sub = active_sub(user.id)
    sub_cost, sub_note, sub_admin, pay = (2 if data["slides"] == "s30" else 1), "", "", None
    covered = bool(sub) and sub["left"] >= sub_cost
    if covered:
        plan = sub["plan"]
        base = PACKAGES[data["slides"]][0]
        pay = (int(base * URGENT_EXTRA) if data["deadline"] == "d1" else 0) \
            + (TEXT_EXTRA if data.get("need_text") else 0) \
            + (NOTES_EXTRA if data.get("need_notes") and not PLANS[plan]["notes"] else 0)
        price = pay
        sub_note = t_cl["sub_line"].format(plan=t_cl["plan_names"][plan], cost=sub_cost, left=sub["left"] - sub_cost) \
            + (t_cl["sub_pay"].format(pay=fmt_sum(pay)) if pay else "")
        sub_admin = (f"\n\n📦 <b>ИЗ ПАКЕТА</b>: списано {sub_cost}, "
                     f"осталось {sub['left'] - sub_cost}. К оплате сверх подписки: {fmt_sum(pay)} сум")
    elif sub:
        sub_note = t_cl["sub_empty"].format(plan=t_cl["plan_names"][sub["plan"]])
        sub_admin = f"\n\n📦 Пакет клиента закончился — заказ по обычной цене"
    who = f"@{user.username}" if user.username else "(без ника)"
    header = (
        f"🔔 <b>НОВАЯ ЗАЯВКА #{oid}</b>\n"
        f"Клиент: {html.escape(user.full_name)} {who}\n"
        f"ID: <code>{user.id}</code>\n"
        f"Контакт: {html.escape(str(data.get('contact')))}\n"
        f"Язык общения: {({'ru': 'русский', 'uz': 'узбекский', 'en': 'английский'}).get(lang, lang)}\n"
        f"Откуда: {data.get('source') or ('✨ Mini App' if data.get('from_app') else 'анкета в чате')}\n\n"
    )
    admin_text = header + (await build_summary(state, for_admin=True)).replace("\n\nВсё верно?", "")
    if first:
        admin_text += f"\n🎁 <b>Первый заказ</b> — Мини по {fmt_sum(FIRST_PRICE)} сум"
    if data.get("from_app"):
        admin_text = admin_text.replace("Файлов: 0\n", "")  # файлы из приложения придут отдельно

    admin_text += sub_admin + ("\n\n✅ <b>Оплачено пакетом</b> — после согласования обложки Claude сразу делает всю презентацию."
                               if covered and not pay else "") \
        + "\n\n🤖 Обложку Claude начнёт делать автоматически (бесплатный этап) и пришлёт вам на проверку." \
        + "\n<i>Статус меняйте кнопками ниже. Ответить клиенту — ответьте (reply) на это сообщение.</i>"
    ok = True
    try:
        await bot.send_message(ADMIN_ID, admin_text, reply_markup=status_kb(oid, "new"))
        for msg_id in data.get("files", []):
            await bot.copy_message(ADMIN_ID, from_chat_id=user.id, message_id=msg_id)
    except Exception as e:  # noqa: BLE001
        logging.exception("Не удалось отправить заявку владельцу: %s", e)
        ok = False
    save_order(user, lang, data)
    if not ok:
        return 0
    db["last_id"] = oid
    db["orders"][str(oid)] = {
        "id": oid, "uid": user.id, "lang": lang, "topic": data.get("topic", "")[:120],
        "slides": data["slides"], "price": price, "status": "new",
        "sub": sub["plan"] if covered else None, "sub_cost": sub_cost if covered else 0,
        "created": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "paid": bool(covered and not price), "stage": "cover_todo",
    }
    save_orders(db)
    try:
        write_brief(db["orders"][str(oid)], data, user)
        asyncio.create_task(save_refs(bot, oid, data.get("refs", [])))
    except Exception as e:  # noqa: BLE001
        logging.exception("Не удалось создать папку заказа: %s", e)
    if covered:
        use_sub(user.id, sub_cost)
    await state.update_data(order_id=oid, sub_note=sub_note)
    if not db["orders"][str(oid)]["paid"] and price > 0:
        asyncio.create_task(send_pay(bot, user.id, lang, price, oid, intro=T[lang]["pay_order_note"], delay=2.5))
    return oid


@router.callback_query(Order.confirm, F.data == "ok:send")
async def order_send(cb: CallbackQuery, state: FSMContext, bot: Bot):
    lang = await get_lang(state)
    await cb.message.edit_reply_markup(reply_markup=None)
    ok = await deliver_order(bot, cb.from_user, state)
    if ok:
        await cb.message.answer(T[lang]["sent"] + T[lang]["order_line"].format(id=ok) + (await state.get_data()).get("sub_note", ""), reply_markup=main_menu(lang))
    else:
        await cb.message.answer(
            T[lang]["error_admin"].format(admin=ADMIN_USERNAME or "slidelab_uz"),
            reply_markup=main_menu(lang),
        )
    await state.clear()
    await state.update_data(lang=lang)
    await cb.answer()


def save_order(user, lang: str, data: dict) -> None:
    price, is_from = calc_price(
        data["slides"], data["deadline"], data.get("need_text"), data.get("need_notes")
    )
    new_file = not ORDERS_FILE.exists()
    with ORDERS_FILE.open("a", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        if new_file:
            w.writerow(["Дата", "Имя", "Ник", "ID", "Контакт", "Тема", "Слайды", "Срок",
                        "Язык", "Дизайн", "Текст", "Конспект", "Файлов", "Цена"])
        w.writerow([
            datetime.now().strftime("%Y-%m-%d %H:%M"),
            user.full_name,
            user.username or "",
            user.id,
            data.get("contact", ""),
            data.get("topic", "") + (f" | {data['comment']}" if data.get("comment") else "")
            + (f" | Источники: {data['sources']}" if data.get("sources") else "")
            + (f" | Шаблон: {data['dlink']}" if data.get("dlink") else ""),
            T["ru"]["slides"][data["slides"]],
            T["ru"]["deadline"][data["deadline"]],
            T["ru"]["plang"][data["plang"]],
            "свой" if data.get("design") == "own" else "по теме",
            "да" if data.get("need_text") else "нет",
            "да" if data.get("need_notes") else "нет",
            len(data.get("files", [])),
            ("от " if is_from else "") + str(price),
        ])


# Если человек нажимает не туда во время анкеты — подсказываем
@router.message(Order.slides)
@router.message(Order.deadline)
@router.message(Order.plang)
@router.message(Order.design)
@router.message(Order.extras)
@router.message(Order.confirm)
@router.message(Order.quick, F.text)
async def order_use_buttons(message: Message, state: FSMContext):
    lang = await get_lang(state)
    await message.answer(T[lang]["use_buttons"])


# ───────────── ПОДПИСКИ: ЗАЯВКА И АКТИВАЦИЯ ─────────────
async def request_sub(message: Message, state: FSMContext, plan: str, lang: str | None = None):
    lang = lang if lang in T else await get_lang(state)
    u = message.from_user
    who = f"@{u.username}" if u.username else "(без ника)"
    p = PLANS[plan]
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Оплачено — включить", callback_data=f"subon:{u.id}:{plan}")
    try:
        await message.bot.send_message(
            ADMIN_ID,
            f"📦 <b>ЗАЯВКА НА ПАКЕТ «{T['ru']['plan_names'][plan]}»</b>\n"
            f"Клиент: {html.escape(u.full_name)} {who}\nID: <code>{u.id}</code>\n"
            f"Презентаций: {p['limit']}, действует {p['days']} дн. · {fmt_sum(p['price'])} сум\n\n" +
            ("<i>Реквизиты клиенту отправлены. Когда деньги придут — нажмите кнопку.</i>" if PAY_CARDS else "<i>Напишите клиенту, как оплатить (reply на это сообщение). После оплаты нажмите кнопку.</i>"),
            reply_markup=kb.as_markup())
        await message.answer(T[lang]["sub_req_sent"].format(plan=T[lang]["plan_names"][plan]), reply_markup=main_menu(lang))
        await send_pay(message.bot, u.id, lang, p["price"], plan=plan)
    except Exception as e:  # noqa: BLE001
        logging.exception("Не удалось отправить заявку на подписку: %s", e)
        await message.answer(T[lang]["error_admin"].format(admin=ADMIN_USERNAME or "slidelab_uz"))


@router.callback_query(F.data.startswith("subon:"))
async def sub_activate(cb: CallbackQuery, bot: Bot):
    if cb.from_user.id != ADMIN_ID:
        await cb.answer()
        return
    _, uid, ref = cb.data.split(":")
    uid = int(uid)
    plan, coid = parse_pack(ref)
    _, credit, units = pack_price(plan, coid)
    sub = activate_sub(uid, plan, minus=units)
    if credit:
        use_credit(coid)
    lang = next((o.get("lang", "ru") for o in load_orders()["orders"].values() if o.get("uid") == uid), "ru")
    t = T[lang]
    await cb.message.edit_reply_markup(reply_markup=None)
    token = CURRENT_USER.set(uid)
    try:
        await bot.send_message(uid, t["sub_on"].format(plan=t["plan_names"][plan], end=fmt_date(sub["end"]),
                                                       limit=sub["limit"]), reply_markup=main_menu(lang))
        await cb.message.answer(f"✅ Пакет «{T['ru']['plan_names'][plan]}» включён ({sub['limit']} през.) до {fmt_date(sub['end'])}, клиент уведомлён.")
        await send_pack_gift(bot, uid, plan, lang)
    except Exception as e:  # noqa: BLE001
        await cb.message.answer(f"Подписка включена, но написать клиенту не удалось: <code>{html.escape(str(e))[:150]}</code>")
    finally:
        CURRENT_USER.reset(token)
    await cb.answer()


@router.message(Command("subs"))
async def cmd_subs(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    db = load_subs()
    today = datetime.now().strftime("%Y-%m-%d")
    rows = [f"• <code>{uid}</code> — {T['ru']['plan_names'][s_['plan']]}, использовано {s_.get('used', 0)}/"
            f"{s_.get('limit', PLANS[s_['plan']]['limit'])}, до {fmt_date(s_['end'])}"
            for uid, s_ in db.items() if s_["end"] >= today]
    await message.answer("📦 <b>Активные пакеты</b>\n" + ("\n".join(rows) if rows else "пока нет"))


# ───────────── МОИ ЗАКАЗЫ, СТАТУСЫ, ВОПРОСЫ ─────────────
@router.message(F.text.in_(all_button_texts("btn_my")))
async def my_orders(message: Message, state: FSMContext):
    lang = await get_lang(state)
    t = T[lang]
    mine = user_orders(message.from_user.id)[:10]
    sub = active_sub(message.from_user.id)
    if sub:
        await message.answer(t["sub_status"].format(plan=t["plan_names"][sub["plan"]], left=sub["left"],
                                                    limit=sub["limit"], end=fmt_date(sub["end"])))
    if not mine:
        await message.answer(t["my_empty"], reply_markup=main_menu(lang))
        return
    lines = [t["my_title"]]
    for o in mine:
        lines.append(f"<b>#{o['id']}</b> · {html.escape(o['topic'][:60])}\n"
                     f"   {t['slides'].get(o['slides'], '')} · {t['st'].get(o['status'], o['status'])}")
    kb = InlineKeyboardBuilder()
    for o in mine:
        if o["status"] in ("done", "edit"):
            kb.button(text=t["btn_edit"].format(id=o["id"]), callback_data=f"edit:{o['id']}")
    kb.adjust(1)
    await message.answer("\n".join(lines), reply_markup=kb.as_markup() if list(kb.buttons) else main_menu(lang))


@router.callback_query(F.data.startswith("st:"))
async def set_status(cb: CallbackQuery, bot: Bot):
    if cb.from_user.id != ADMIN_ID:
        await cb.answer()
        return
    _, oid, code = cb.data.split(":")
    db = load_orders()
    o = db["orders"].get(oid)
    if not o or code not in T["ru"]["st"]:
        await cb.answer("Заказ не найден", show_alert=True)
        return
    if code == "cancel" and o.get("sub_cost") and o.get("status") != "cancel":
        use_sub(o["uid"], -o["sub_cost"])   # отмена — возвращаем презентацию в лимит
        o["sub_cost"] = 0
    o["status"] = code
    save_orders(db)
    await cb.message.edit_reply_markup(reply_markup=status_kb(int(oid), code))
    t = T[o.get("lang", "ru")]
    token = CURRENT_USER.set(o["uid"])
    try:
        note = t["status_note"].format(id=oid, topic=html.escape(o["topic"][:60]), status=t["st"][code])
        if code == "done":
            asyncio.create_task(offer_credit(bot, oid))
            await bot.send_message(o["uid"], note + t["done_hint"], reply_markup=edit_kb(o.get("lang", "ru"), int(oid)))
            await bot.send_message(o["uid"], t["menu_refresh"], reply_markup=main_menu(o.get("lang", "ru"), o["uid"]))
        else:
            await bot.send_message(o["uid"], note, reply_markup=main_menu(o.get("lang", "ru"), o["uid"]))
        await cb.answer(f"#{oid}: {T['ru']['st'][code]} — клиент уведомлён")
    except Exception as e:  # noqa: BLE001
        logging.exception("Не удалось уведомить клиента: %s", e)
        await cb.answer("Статус сохранён, но клиенту написать не удалось", show_alert=True)
    finally:
        CURRENT_USER.reset(token)


def edit_kb(lang: str, oid: int):
    kb = InlineKeyboardBuilder()
    kb.button(text=T[lang]["btn_edit"].format(id=oid), callback_data=f"edit:{oid}")
    return kb.as_markup()


async def start_edit(message: Message, state: FSMContext, oid: int, uid: int, quiet: bool = False) -> bool:
    o = load_orders()["orders"].get(str(oid))
    if not o or o["uid"] != uid:
        return False
    lang = o.get("lang", "ru")
    await state.update_data(lang=lang, edit_id=oid, edit_group=None)
    await state.set_state(Order.edit)
    if not quiet:
        await message.answer(T[lang]["edit_prompt"].format(id=oid), reply_markup=main_menu(lang))
    return True


async def forward_edit(message: Message, state: FSMContext, bot: Bot, text: str | None = None):
    """Текст правок — сразу владельцу с шапкой; скриншоты/файлы — копией (альбом — одной шапкой)."""
    data = await state.get_data()
    oid = data.get("edit_id")
    lang = data.get("lang", "ru")
    u = message.from_user
    who = f"@{u.username}" if u.username else u.full_name
    db = load_orders()
    o = db["orders"].get(str(oid))
    if o:
        if o.get("stage") in ("cover_sent", "cover_todo", "cover_review"):
            o["stage"] = "cover_todo"        # клиент просит поменять обложку
        elif o.get("stage") in (None, "done", "edit_todo", "edit_review"):
            o["status"] = "edit"
            o["stage"] = "edit_todo"
        save_orders(db)
        sync_brief(o)
        if text is not None:
            add_note(oid, "Клиент (правки)", text)
        else:
            asyncio.create_task(save_refs(bot, oid, [media_ref(message)], sub="edits"))
    head = f"✏️ <b>ПРАВКИ к заказу #{oid}</b>\nКлиент: {html.escape(who)}\nID: <code>{u.id}</code>"
    group = message.media_group_id
    same_album = bool(group) and group == data.get("edit_group")
    try:
        if text is not None:
            await bot.send_message(ADMIN_ID, head + f"\n\n{html.escape(text)}", reply_markup=status_kb(int(oid), "edit"))
        else:
            if not same_album:
                await bot.send_message(ADMIN_ID, head + "\n📎 файлы:", reply_markup=status_kb(int(oid), "edit"))
            await bot.copy_message(ADMIN_ID, from_chat_id=u.id, message_id=message.message_id)
            await state.update_data(edit_group=group)
        if not same_album:
            await message.answer(T[lang]["edit_got"])
    except Exception as e:  # noqa: BLE001
        logging.exception("Не удалось переслать правки: %s", e)
        await message.answer(T[lang]["error_admin"].format(admin=ADMIN_USERNAME or "slidelab_uz"))


@router.callback_query(F.data.startswith("edit:"))
async def edit_button(cb: CallbackQuery, state: FSMContext):
    oid = int(cb.data.split(":")[1])
    if not await start_edit(cb.message, state, oid, cb.from_user.id):
        await cb.answer("Заказ не найден", show_alert=True)
        return
    await cb.answer()


@router.message(Order.edit, F.document | F.photo | F.video | F.audio | F.voice | F.video_note | F.animation | (F.text & ~F.text.in_(
    set().union(*(all_button_texts(k) for k in ("btn_order", "btn_price", "btn_examples", "btn_faq", "btn_lang", "btn_my", "btn_app"))))))
async def edit_message(message: Message, state: FSMContext, bot: Bot):
    if message.text:
        await forward_edit(message, state, bot, text=message.text)
    else:
        await forward_edit(message, state, bot)


@router.message(Order.ask, F.text)
async def ask_text(message: Message, state: FSMContext):
    await send_question(message, state, message.text)


# ───────────── ПЕРЕСЛАННЫЙ ФАЙЛ → БЫСТРЫЙ ЗАКАЗ ─────────────
@router.message(StateFilter(None), F.document | F.photo | F.video | F.audio | F.voice | F.video_note | F.animation)
async def quick_from_file(message: Message, state: FSMContext):
    lang = await get_lang(state)
    media = message.document or message.audio or message.video or message.animation
    name = getattr(media, "file_name", None) or ("фото" if message.photo else "файл")
    await state.set_data({
        "lang": lang, "from_app": True, "source": "📎 пересланный файл",
        "files": [message.message_id], "refs": [media_ref(message)], "topic": f"По файлу: {name}"[:300],
        "plang": lang, "design": "ours", "need_text": False, "need_notes": False,
    })
    await state.set_state(Order.quick)
    await message.answer(T[lang]["qf_ask"], reply_markup=options_kb("qf", T[lang]["slides"], 3))


@router.message(Order.quick, F.document | F.photo | F.video | F.audio | F.voice | F.video_note | F.animation)
async def quick_more_files(message: Message, state: FSMContext):
    lang = await get_lang(state)
    data = await state.get_data()
    files = data.get("files", []) + [message.message_id]
    await state.update_data(files=files, refs=data.get("refs", []) + [media_ref(message)])
    await message.answer(T[lang]["qf_more"].format(n=len(files)))


@router.callback_query(Order.quick, F.data.startswith("qf:"))
async def quick_choose(cb: CallbackQuery, state: FSMContext, bot: Bot):
    lang = await get_lang(state)
    t = T[lang]
    key = cb.data.split(":")[1]
    await cb.message.edit_reply_markup(reply_markup=None)
    if key in PACKAGES:
        await state.update_data(slides=key)
        opts = dict(t["deadline"])
        if key == "s30":
            opts.pop("d1", None)
        await cb.message.answer(t["qf_deadline"], reply_markup=options_kb("qf", opts, 1))
        await cb.answer()
        return
    if key in t["deadline"] and (await state.get_data()).get("slides"):
        u = cb.from_user
        await state.update_data(deadline=key, contact=f"@{u.username}" if u.username else "Telegram")
        ok = await deliver_order(bot, u, state)
        if ok:
            await state.set_state(Order.after_app)
            await cb.message.answer(t["app_sent"] + t["order_line"].format(id=ok) + (await state.get_data()).get("sub_note", ""), reply_markup=main_menu(lang))
        else:
            await state.clear()
            await state.update_data(lang=lang)
            await cb.message.answer(t["error_admin"].format(admin=ADMIN_USERNAME or "slidelab_uz"),
                                    reply_markup=main_menu(lang))
    await cb.answer()


def parse_pack(ref: str) -> tuple[str, str | None]:
    """«week» или «week.12» (пакет с зачётом заказа #12) → (план, номер заказа)."""
    plan, _, oid = ref.partition(".")
    return plan, (oid or None)


def pack_price(plan: str, oid: str | None) -> tuple[int, int, int]:
    """(к оплате, засчитано сум, засчитано презентаций) — с учётом зачёта заказа, если он ещё действует."""
    full = PLANS[plan]["price"]
    if not oid:
        return full, 0, 0
    o = load_orders()["orders"].get(oid) or {}
    if not o.get("credit_until") or o.get("credit_used") or datetime.now().strftime("%Y-%m-%d") > o["credit_until"]:
        return full, 0, 0
    credit, units = o.get("price", 0), (2 if o.get("slides") == "s30" else 1)
    if credit >= full or units >= PLANS[plan]["limit"]:
        return full, 0, 0
    return full - credit, credit, units


def use_credit(oid: str | None) -> None:
    if not oid:
        return
    db = load_orders()
    if oid in db["orders"]:
        db["orders"][oid]["credit_used"] = True
        save_orders(db)


async def offer_credit(bot: Bot, oid: str) -> None:
    """После сдачи оплаченного заказа: «возьмите пакет за N дней — этот заказ засчитаем»."""
    if not CREDIT_DAYS:
        return
    from datetime import timedelta
    db = load_orders()
    o = db["orders"].get(str(oid))
    if not o or o.get("credit_offered") or o.get("sub") or not o.get("paid") or o.get("price", 0) <= 0:
        return
    o["credit_offered"] = True
    o["credit_until"] = (datetime.now() + timedelta(days=CREDIT_DAYS)).strftime("%Y-%m-%d")
    save_orders(db)
    lang = o.get("lang", "ru")
    t = T[lang]
    kb = InlineKeyboardBuilder()
    lines = []
    for plan in PLANS:
        pay, credit, units = pack_price(plan, str(oid))
        if not credit:
            continue
        more = PLANS[plan]["limit"] - units
        lines.append(t["cr_line"].format(plan=t["plan_names"][plan], full=fmt_sum(PLANS[plan]["price"]), pay=fmt_sum(pay), more=more))
        kb.button(text=t["cr_btn"].format(plan=t["plan_names"][plan], pay=fmt_sum(pay)), callback_data=f"pk:{plan}.{oid}")
    if not lines:
        return
    kb.adjust(1)
    await bot.send_message(o["uid"], t["cr_text"].format(sum=fmt_sum(o["price"]), date=fmt_date(o["credit_until"]),
                                                         lines="\n".join(lines)), reply_markup=kb.as_markup())


@router.callback_query(F.data.startswith("pk:"))
async def credit_pick(cb: CallbackQuery, state: FSMContext, bot: Bot):
    plan, oid = parse_pack(cb.data[3:])
    o = load_orders()["orders"].get(oid or "") or {}
    lang = o.get("lang") or await get_lang(state)
    if o.get("uid") != cb.from_user.id or plan not in PLANS:
        await cb.answer()
        return
    pay, credit, _ = pack_price(plan, oid)
    if not credit:
        await cb.answer(T[lang]["cr_expired"], show_alert=True)
        return
    await send_pay(bot, cb.from_user.id, lang, pay, plan=f"{plan}.{oid}")
    await cb.answer()


def invoice_params(ref: str, lang: str):
    """Название, описание, сумма (сум) и payload счёта в звёздах."""
    t = T[lang]
    if ref.startswith("s_"):
        plan, oid = parse_pack(ref[2:])
        p = PLANS[plan]
        pay, credit, units = pack_price(plan, oid)
        return (t["inv_sub"].format(plan=t["plan_names"][plan]),
                t["inv_sub_d"].format(limit=p["limit"] - units, days=p["days"])
                + (t["inv_credit"].format(id=oid, sum=fmt_sum(credit)) if credit else ""),
                pay, f"s:{plan}.{oid}" if credit else f"s:{plan}")
    o = load_orders()["orders"].get(ref) or {}
    return (t["inv_order"].format(id=ref),
            t["inv_order_d"].format(topic=o.get("topic", "")[:80], sl=t["slides"].get(o.get("slides"), "")),
            o.get("price", 0), f"o:{ref}")


async def stars_link(bot: Bot, ref: str, lang: str) -> str | None:
    """Ссылка, которая сразу открывает окно оплаты звёздами (без лишнего сообщения-счёта)."""
    try:
        title, desc, amount, payload = invoice_params(ref, lang)
        return await bot.create_invoice_link(title=title[:32], description=desc[:255], payload=payload, provider_token="",
                                             currency="XTR", prices=[LabeledPrice(label=title[:32], amount=to_stars(amount))])
    except Exception as e:  # noqa: BLE001
        logging.warning("Ссылка на оплату звёздами не создана: %s", e)
        return None


async def pay_block(bot: Bot, lang: str, amount: int, oid=None, plan: str | None = None, intro: str = "") -> tuple[str, InlineKeyboardMarkup | None]:
    t = T[lang]
    head = t["pay_head_sub"].format(plan=t["plan_names"][parse_pack(plan)[0]], sum=fmt_sum(amount)) if plan \
        else t["pay_head"].format(id=oid, sum=fmt_sum(amount))
    ref = "s_" + plan if plan else str(oid)
    kb = InlineKeyboardBuilder()
    if STARS_ON:
        link = await stars_link(bot, ref, lang)
        if link:
            kb.button(text=t["btn_stars"].format(n=to_stars(amount)), url=link)
        else:
            kb.button(text=t["btn_stars"].format(n=to_stars(amount)), callback_data=f"stars:{ref}")
    if not PAY_CARDS:
        body = (t["pay_stars_only"] if STARS_ON else t["pay_nocards"])
        return head + intro + body, (kb.as_markup() if STARS_ON else None)
    cards = "\n".join(f"• {label}: <code>{html.escape(num)}</code>" for label, num in PAY_CARDS)
    name = t["pay_name"].format(n=html.escape(PAY_NAME)) if PAY_NAME else ""
    kb.button(text=t["btn_paid"], callback_data=f"ipaid:{ref}")
    kb.adjust(1)
    return head + intro + t["pay_cards"].format(cards=cards, name=name) + (t["pay_or_stars"] if STARS_ON else ""), kb.as_markup()


async def send_pay(bot: Bot, uid: int, lang: str, amount: int, oid=None, plan=None, intro: str = "", delay: float = 0) -> None:
    if amount <= 0:
        return
    if delay:
        await asyncio.sleep(delay)
    text, kb = await pay_block(bot, lang, amount, oid, plan, intro)
    try:
        await bot.send_message(uid, text, reply_markup=kb)
    except Exception as e:  # noqa: BLE001
        logging.warning("Не удалось отправить реквизиты: %s", e)


@router.callback_query(F.data.startswith("ipaid:"))
async def client_paid(cb: CallbackQuery, state: FSMContext):
    ref = cb.data.split(":", 1)[1]
    lang = await get_lang(state)
    await state.update_data(pay_ref=ref)
    await state.set_state(Order.paycheck)
    await cb.message.answer(T[lang]["pay_send_check"])
    await cb.answer()


@router.message(Order.paycheck, F.document | F.photo | (F.text & ~F.text.in_(
    set().union(*(all_button_texts(k) for k in ("btn_order", "btn_price", "btn_examples", "btn_faq", "btn_lang", "btn_my", "btn_app"))))))
async def client_paycheck(message: Message, state: FSMContext, bot: Bot):
    lang = await get_lang(state)
    ref = (await state.get_data()).get("pay_ref", "")
    u = message.from_user
    who = f"@{u.username}" if u.username else html.escape(u.full_name)
    kb = InlineKeyboardBuilder()
    if ref.startswith("s_"):
        plan, coid = parse_pack(ref[2:])
        pay, credit, _ = pack_price(plan, coid)
        what = f"пакета «{T['ru']['plan_names'].get(plan, plan)}» — {fmt_sum(pay)} сум" \
            + (f" (засчитан заказ #{coid}: −{fmt_sum(credit)})" if credit else "")
        kb.button(text="✅ Оплата пришла — включить пакет", callback_data=f"subon:{u.id}:{plan}.{coid}" if credit else f"subon:{u.id}:{plan}")
    else:
        o = load_orders()["orders"].get(ref) or {}
        what = f"заказа #{ref} — {fmt_sum(o.get('price', 0))} сум"
        kb.button(text="💰 Оплата получена", callback_data=f"paid:{ref}")
        if o:
            add_note(ref, "Клиент", "сообщил об оплате (чек у владельца в Telegram)")
    try:
        await bot.send_message(ADMIN_ID, f"💳 <b>Клиент сообщил об оплате</b> {what}\nКлиент: {who}\nID: <code>{u.id}</code>\n\n"
                                         "Проверьте поступление на карту и нажмите кнопку. Чек ниже 👇", reply_markup=kb.as_markup())
        await bot.copy_message(ADMIN_ID, from_chat_id=u.id, message_id=message.message_id)
        await message.answer(T[lang]["pay_thanks"], reply_markup=main_menu(lang))
    except Exception as e:  # noqa: BLE001
        logging.exception("Не удалось переслать чек: %s", e)
        await message.answer(T[lang]["error_admin"].format(admin=ADMIN_USERNAME or "slidelab_uz"))
    await state.set_state(None)


@router.callback_query(F.data.startswith("stars:"))
async def stars_invoice(cb: CallbackQuery, state: FSMContext, bot: Bot):
    ref = cb.data.split(":", 1)[1]
    lang = await get_lang(state)
    t = T[lang]
    if not ref.startswith("s_"):
        o = load_orders()["orders"].get(ref)
        if not o or o["uid"] != cb.from_user.id:
            await cb.answer()
            return
        if o.get("paid"):
            await cb.answer(t["inv_done"], show_alert=True)
            return
        lang = o.get("lang", lang)
    title, desc, amount, payload = invoice_params(ref, lang)
    await bot.send_invoice(cb.from_user.id, title=title[:32], description=desc[:255], payload=payload,
                           currency="XTR", prices=[LabeledPrice(label=title[:32], amount=to_stars(amount))])
    await cb.answer()


@router.pre_checkout_query()
async def stars_precheck(q: PreCheckoutQuery):
    kind, _, ref = q.invoice_payload.partition(":")
    if kind == "o":
        o = load_orders()["orders"].get(ref)
        if not o or o.get("paid") or o.get("status") == "cancel":
            await q.answer(ok=False, error_message="Заказ уже оплачен или отменён / Buyurtma to‘langan yoki bekor qilingan")
            return
    elif kind != "s" or parse_pack(ref)[0] not in PLANS:
        await q.answer(ok=False, error_message="Счёт устарел — откройте оплату заново")
        return
    await q.answer(ok=True)


@admin_router.message(F.successful_payment)  # раньше всех, чтобы оплату не перехватили другие шаги
async def stars_paid(message: Message, state: FSMContext, bot: Bot):
    sp = message.successful_payment
    kind, _, ref = sp.invoice_payload.partition(":")
    u = message.from_user
    who = f"@{u.username}" if u.username else html.escape(u.full_name)
    charge = sp.telegram_payment_charge_id
    if kind == "o":
        await apply_paid(bot, ref, paid_by="stars", stars=sp.total_amount, star_charge=charge)
        add_note(ref, "Оплата", f"{sp.total_amount} ⭐ звёздами Telegram")
        await bot.send_message(ADMIN_ID, f"⭐ <b>Оплата звёздами</b>: {sp.total_amount} ⭐ за заказ #{ref}\nКлиент: {who}\n"
                                         f"Возврат при необходимости: <code>/refund {ref}</code>")
    else:
        plan, coid = parse_pack(ref)
        lang = await get_lang(state)
        t = T[lang]
        _, credit, units = pack_price(plan, coid)
        sub = activate_sub(u.id, plan, minus=units)
        if credit:
            use_credit(coid)
        db = load_subs()
        db[str(u.id)]["star_charge"] = charge
        save_subs(db)
        await message.answer(t["sub_on"].format(plan=t["plan_names"][plan], end=fmt_date(sub["end"]), limit=sub["limit"]),
                             reply_markup=main_menu(lang))
        await bot.send_message(ADMIN_ID, f"⭐ <b>Оплата звёздами</b>: {sp.total_amount} ⭐ — пакет «{T['ru']['plan_names'][plan]}» "
                                         f"включён автоматически\nКлиент: {who}, ID <code>{u.id}</code>")
        await send_pack_gift(bot, u.id, plan, lang)


@admin_router.message(Command("paysupport"))
async def cmd_paysupport(message: Message, state: FSMContext):
    lang = await get_lang(state)
    await message.answer(T[lang]["paysupport"].format(admin=ADMIN_USERNAME or "slidelab_uz"))


@router.message(Command("refund"))
async def cmd_refund(message: Message, command: CommandObject, bot: Bot):
    """/refund <номер заказа> — вернуть звёзды клиенту (только владелец)."""
    if message.from_user.id != ADMIN_ID:
        return
    oid = (command.args or "").strip().lstrip("#")
    db = load_orders()
    o = db["orders"].get(oid)
    if not o or not o.get("star_charge"):
        await message.answer("Нет оплаты звёздами по этому заказу. Пример: <code>/refund 12</code>")
        return
    try:
        await bot.refund_star_payment(o["uid"], o["star_charge"])
    except Exception as e:  # noqa: BLE001
        await message.answer(f"⚠️ Не получилось: <code>{html.escape(str(e))[:200]}</code>")
        return
    o.update(paid=False, star_charge=None, status="cancel")
    save_orders(db)
    sync_brief(o)
    await message.answer(f"↩️ {o.get('stars', '')} ⭐ возвращены клиенту, заказ #{oid} отменён.")


@router.message(Command("branding"))
async def cmd_branding(message: Message, bot: Bot):
    if message.from_user.id != ADMIN_ID:
        return
    (Path(__file__).with_name("media") / f"branding_{BRANDING_VERSION}.done").unlink(missing_ok=True)
    await setup_branding(bot)


@router.message()
async def fallback(message: Message, state: FSMContext):
    lang = await get_lang(state)
    await message.answer(T[lang]["welcome"], reply_markup=main_menu(lang))


# ───────────────────────── АВТОПЕРЕЗАПУСК ─────────────────────────
# Если меняются bot.py, publisher.py или settings.txt — бот сам перезапускается.
# Перед перезапуском код проверяется: если в нём ошибка, бот продолжит работать
# на старой версии и сообщит владельцу.
RESTART_CODE = 3
WATCH_FILES = ["bot.py", "publisher.py", "settings.txt"]
_restart_requested = False


def _mtimes() -> dict:
    base = Path(__file__).parent
    return {n: (base / n).stat().st_mtime for n in WATCH_FILES if (base / n).exists()}


async def watch_for_changes(bot: Bot, dp: Dispatcher) -> None:
    global _restart_requested
    known = _mtimes()
    while True:
        await asyncio.sleep(5)
        now = _mtimes()
        changed = [n for n in now if now[n] != known.get(n)]
        if not changed:
            continue
        await asyncio.sleep(2)  # даём файлу дописаться
        errors = []
        for n in changed:
            if n.endswith(".py"):
                try:
                    py_compile.compile(str(Path(__file__).with_name(n)), doraise=True)
                except py_compile.PyCompileError as e:
                    errors.append(f"{n}: {e.msg[-300:]}")
        known = _mtimes()
        if errors:
            logging.error("Новый код с ошибкой, перезапуск отменён: %s", errors)
            if ADMIN_ID:
                try:
                    await bot.send_message(
                        ADMIN_ID,
                        "⚠️ В обновлении бота ошибка, работаю на старой версии:\n<code>"
                        + html.escape("\n".join(errors)) + "</code>")
                except Exception:  # noqa: BLE001
                    pass
            continue
        print(f"🔄 Изменены файлы: {', '.join(changed)}. Перезапускаюсь...")
        _restart_requested = True
        await dp.stop_polling()
        return


# ───────────── СИНХРОНИЗАЦИЯ С GITHUB ─────────────
# GitHub — главное место кода. Раз в несколько минут бот сверяет папку bot/ в репозитории
# с файлами на этом компьютере и подтягивает изменения: bot.py, publisher.py и посты (posts/*.txt).
# Секреты (settings.txt), заказы и state.json не трогаются — их в репозитории нет.
GH_REPO = os.getenv("GH_REPO", "ReptileU/slidelab-app").strip()
GH_BRANCH = os.getenv("GH_BRANCH", "main").strip()
GH_SYNC_MIN = int(os.getenv("GH_SYNC_MIN", "3") or 0)   # 0 — выключить
GH_SYNC_STATE = Path(__file__).with_name(".gh_sync.json")


def _git_blob_sha(data: bytes) -> str:
    import hashlib
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def _gh_wanted(path: str) -> str | None:
    """bot/… в репозитории → путь относительно папки бота, или None, если файл не синхронизируем."""
    if not path.startswith("bot/"):
        return None
    rel = path[4:]
    if rel in ("bot.py", "publisher.py"):
        return rel
    if rel.startswith("posts/") and rel.endswith(".txt") and rel.count("/") == 1:
        return rel
    return None


async def github_sync_once(bot: Bot | None = None) -> list[str]:
    import aiohttp
    base = Path(__file__).parent
    try:
        state = json.loads(GH_SYNC_STATE.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        state = {}
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "slidelab-bot"}
    tree_url = f"https://api.github.com/repos/{GH_REPO}/git/trees/{GH_BRANCH}?recursive=1"
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=40), trust_env=True) as http:
        async with http.get(tree_url, headers=headers) as r:
            if r.status != 200:
                logging.warning("GitHub sync: дерево не получено (%s)", r.status)
                return []
            tree = (await r.json()).get("tree", [])
        updated = []
        for item in tree:
            rel = _gh_wanted(item.get("path", "")) if item.get("type") == "blob" else None
            if not rel:
                continue
            remote_sha = item["sha"]
            if state.get(rel) == remote_sha:
                continue   # с прошлой синхронизации на GitHub ничего не менялось
            local = base / rel
            if local.exists() and _git_blob_sha(local.read_bytes()) == remote_sha:
                state[rel] = remote_sha
                continue
            raw = f"https://raw.githubusercontent.com/{GH_REPO}/{GH_BRANCH}/{item['path']}"
            async with http.get(raw) as r:
                if r.status != 200:
                    continue
                data = await r.read()
            if _git_blob_sha(data) != remote_sha:
                continue   # кэш raw ещё старый — попробуем в следующий раз
            if rel.endswith(".py"):
                tmp = base / (rel + ".gh_new")
                tmp.write_bytes(data)
                try:
                    py_compile.compile(str(tmp), doraise=True)
                except py_compile.PyCompileError as e:
                    tmp.unlink(missing_ok=True)
                    state[rel] = remote_sha   # эту версию не берём, ждём исправленную
                    if bot and ADMIN_ID:
                        try:
                            await bot.send_message(ADMIN_ID, f"⚠️ На GitHub в {rel} ошибка — не обновляю:\n<code>"
                                                   + html.escape(e.msg[-300:]) + "</code>")
                        except Exception:  # noqa: BLE001
                            pass
                    continue
                tmp.unlink(missing_ok=True)
            local.parent.mkdir(parents=True, exist_ok=True)
            local.write_bytes(data)
            state[rel] = remote_sha
            updated.append(rel)
    GH_SYNC_STATE.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    if updated:
        logging.info("GitHub sync: обновлено %s", updated)
        if bot and ADMIN_ID:
            try:
                await bot.send_message(ADMIN_ID, "🔄 Подтянул с GitHub: " + ", ".join(updated))
            except Exception:  # noqa: BLE001
                pass
    return updated


async def github_sync_loop(bot: Bot) -> None:
    if not GH_SYNC_MIN:
        return
    await asyncio.sleep(20)
    while True:
        try:
            await github_sync_once(bot)
        except Exception as e:  # noqa: BLE001
            logging.warning("GitHub sync: %s", e)
        await asyncio.sleep(GH_SYNC_MIN * 60)


@admin_router.message(Command("sync"))
async def cmd_sync(message: Message, bot: Bot):
    """/sync — подтянуть изменения с GitHub прямо сейчас."""
    if message.from_user.id != ADMIN_ID:
        return
    try:
        upd = await github_sync_once(None)
    except Exception as e:  # noqa: BLE001
        await message.answer(f"⚠️ Не получилось: <code>{html.escape(str(e))[:200]}</code>")
        return
    await message.answer(("🔄 Подтянул с GitHub: " + ", ".join(upd)) if upd else "✅ С GitHub всё совпадает.")


# ───────────── ОТВЕТ ВЛАДЕЛЬЦА КЛИЕНТУ (REPLY) ─────────────
_ID_RE = re.compile(r"ID:?\s*(\d{5,})")


def _reply_target(m: Message):
    src = m.reply_to_message
    if not (m.from_user and m.from_user.id == ADMIN_ID and src):
        return None
    found = _ID_RE.search(src.text or src.caption or "")
    return int(found.group(1)) if found else None


_URL_RE = re.compile(r"https://\S+")
_OID_RE = re.compile(r"#(\d+)")


def _remember_result(src_text: str, uid: int, msg: Message) -> str:
    """Ответ админа с файлом/ссылкой на сообщение заказа → в «Мои презентации» клиента."""
    found = _OID_RE.search(src_text)
    if not found:
        return ""
    link = _URL_RE.search(msg.text or msg.caption or "")
    if not (msg.document or link):
        return ""
    db = load_orders()
    o = db["orders"].get(found.group(1))
    if not o or o.get("uid") != uid:
        return ""
    if link:
        o["link"] = link.group(0).rstrip(").,;")
    if msg.document:
        o["has_file"] = True
    save_orders(db)
    return f"\n🎞 Сохранил в «Мои презентации» клиента (заказ #{o['id']})"


@admin_router.message(F.func(lambda m: _reply_target(m) is not None))
async def admin_reply(message: Message, bot: Bot):
    uid = _reply_target(message)
    db = load_orders()
    lang = next((o.get("lang", "ru") for o in db["orders"].values() if o.get("uid") == uid), "ru")
    try:
        await bot.send_message(uid, T[lang]["reply_prefix"])
        await bot.copy_message(uid, from_chat_id=message.chat.id, message_id=message.message_id)
        note = _remember_result(src_text=(message.reply_to_message.text or message.reply_to_message.caption or ""),
                                uid=uid, msg=message)
        if note:
            await bot.send_message(uid, T[lang]["pres_saved"], reply_markup=main_menu(lang, uid))
        await message.reply("✅ Отправил клиенту" + note)
    except Exception as e:  # noqa: BLE001
        await message.reply(f"⚠️ Не удалось отправить: <code>{html.escape(str(e))[:200]}</code>")


# ───────────────────────── КОНВЕЙЕР: Claude делает → вы проверяете → бот отправляет ─────────────────────────
WORK_DIR = Path(__file__).with_name("orders")
TODO_STAGES = {"cover_todo": "cover", "deck_todo": "deck", "edit_todo": "edit"}
KIND_RU = {"cover": "Обложка", "deck": "Презентация", "edit": "Исправленная презентация"}
KIND_ACC = {"cover": "обложку", "deck": "презентацию", "edit": "правки"}


def media_ref(m: Message) -> dict:
    if m.document:
        return {"fid": m.document.file_id, "name": m.document.file_name or f"file_{m.message_id}"}
    if m.photo:
        return {"fid": m.photo[-1].file_id, "name": f"photo_{m.message_id}.jpg"}
    for kind, ext in (("video", "mp4"), ("audio", "mp3"), ("voice", "ogg"), ("video_note", "mp4"), ("animation", "mp4")):
        x = getattr(m, kind)
        if x:
            return {"fid": x.file_id, "name": getattr(x, "file_name", None) or f"{kind}_{m.message_id}.{ext}"}
    return {"text": m.text or m.caption or ""}


def odir(oid) -> Path:
    d = WORK_DIR / str(oid)
    d.mkdir(parents=True, exist_ok=True)
    return d


def add_note(oid, who: str, text: str) -> None:
    with open(odir(oid) / "notes.md", "a", encoding="utf-8") as f:
        f.write(f"\n## {datetime.now():%Y-%m-%d %H:%M} — {who}\n{text.strip()}\n")


def write_brief(o: dict, data: dict, user) -> None:
    t = T["ru"]
    brief = {
        "id": o["id"], "client_lang": o["lang"], "topic": data.get("topic", ""),
        "slides": t["slides"].get(data.get("slides"), data.get("slides")),
        "deadline": t["deadline"].get(data.get("deadline"), ""),
        "presentation_lang": data.get("plang", o["lang"]),
        "design": "свой шаблон клиента" if data.get("design") == "own" else "дизайн делаем мы по теме",
        "template_link": data.get("dlink", ""), "need_text": bool(data.get("need_text")),
        "need_notes": bool(data.get("need_notes")),
        "need_humor": bool(data.get("need_humor")),  # стиль и база мемов — bot/memes.md на GitHub
        "comment": data.get("comment", ""),
        "sources": data.get("sources", ""), "client_will_send_files": bool(data.get("srcfiles")),
        "client": user.full_name, "created": o["created"],
    }
    d = odir(o["id"])
    (d / "brief.json").write_text(json.dumps(brief, ensure_ascii=False, indent=1), encoding="utf-8")
    sync_brief(o)


def sync_brief(o: dict) -> None:
    """status.json — что сейчас нужно делать по заказу (читает Claude)."""
    (odir(o["id"]) / "status.json").write_text(json.dumps(
        {"stage": o.get("stage"), "paid": o.get("paid", False), "status": o.get("status")},
        ensure_ascii=False), encoding="utf-8")


async def save_refs(bot: Bot, oid, refs: list, sub: str = "files") -> None:
    d = odir(oid) / sub
    d.mkdir(exist_ok=True)
    for r in refs:
        try:
            if r.get("fid"):
                name = re.sub(r'[\\/:*?"<>|]', "_", r["name"])[:120]
                await bot.download(r["fid"], destination=d / name)
            elif r.get("text"):
                add_note(oid, "Клиент (материал текстом)", r["text"])
        except Exception as e:  # noqa: BLE001
            logging.warning("Файл к заказу #%s не скачался (%s) — он есть у вас в чате", oid, e)


def set_stage(oid, stage: str, **extra) -> dict | None:
    db = load_orders()
    o = db["orders"].get(str(oid))
    if not o:
        return None
    o["stage"] = stage
    o["stage_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    o.update(extra)
    save_orders(db)
    sync_brief(o)
    return o


def review_kb(oid) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Отправить клиенту", callback_data=f"rv:{oid}:send")
    kb.button(text="✏️ Доработать", callback_data=f"rv:{oid}:fix")
    kb.adjust(1)
    return kb.as_markup()


async def send_files(bot: Bot, chat_id: int, files: list[Path], caption: str | None = None, kb=None) -> None:
    for i, f in enumerate(files):
        last = i == len(files) - 1
        cap, mk = (caption, kb) if last else (None, None)
        if f.suffix.lower() in (".png", ".jpg", ".jpeg") and f.stat().st_size < 9_000_000:
            await bot.send_photo(chat_id, FSInputFile(f), caption=cap, reply_markup=mk)
        else:
            await bot.send_document(chat_id, FSInputFile(f), caption=cap, reply_markup=mk)


async def watch_reviews(bot: Bot) -> None:
    """Claude кладёт результат в orders/<id>/review/ + review.json → бот присылает вам на проверку."""
    while True:
        await asyncio.sleep(20)
        try:
            for man in WORK_DIR.glob("*/review/review.json"):
                oid = man.parent.parent.name
                o = load_orders()["orders"].get(oid)
                if not o or o.get("stage") not in TODO_STAGES:
                    continue
                r = json.loads(man.read_text(encoding="utf-8"))
                kind = r.get("kind") or TODO_STAGES[o["stage"]]
                # Claude может дать ссылки (экспорт из Canva) — скачиваем их здесь, на компьютере
                for item in r.get("urls", []):
                    name = re.sub(r'[\\/:*?"<>|]', "_", item.get("name") or "file")[:120]
                    if not (man.parent / name).exists():
                        import aiohttp
                        async with aiohttp.ClientSession() as http:
                            async with http.get(item["url"]) as resp:
                                resp.raise_for_status()
                                (man.parent / name).write_bytes(await resp.read())
                    if name not in r.setdefault("files", []):
                        r["files"].append(name)
                man.write_text(json.dumps(r, ensure_ascii=False), encoding="utf-8")
                files = [man.parent / f for f in r.get("files", []) if (man.parent / f).exists()]
                text = (f"🤖 <b>{KIND_RU.get(kind, kind)} к заказу #{oid} готова — проверьте</b>\n"
                        f"«{html.escape(o['topic'][:80])}»\n\n{html.escape(r.get('message', ''))[:700]}")
                if r.get("canva"):
                    text += f"\n\n🖊 Поправить самому: {html.escape(r['canva'])}"
                await bot.send_message(ADMIN_ID, text, disable_web_page_preview=True)
                if files:
                    await send_files(bot, ADMIN_ID, files, f"#{oid} · {KIND_RU.get(kind, kind)}", review_kb(oid))
                else:
                    await bot.send_message(ADMIN_ID, f"#{oid}: файлов нет", reply_markup=review_kb(oid))
                man.rename(man.with_name("review.sent.json"))
                (man.parent / "claim.json").unlink(missing_ok=True)
                set_stage(oid, kind + "_review")
        except Exception as e:  # noqa: BLE001
            logging.exception("Проверка папки заказов: %s", e)


# ───── СТОРОЖ: заказ застрял или не сделан → предупредить вас и дать кнопку «Переделать» ─────
STUCK_HOURS = float(os.getenv("STUCK_HOURS", "3") or 3)      # сколько ждать результат по *_todo
STUCK_REPEAT_H = 12                                           # повторное напоминание


def _hours_since(o: dict) -> float:
    try:
        t = datetime.strptime(o.get("stage_at") or "", "%Y-%m-%d %H:%M")
    except ValueError:
        st = WORK_DIR / str(o["id"]) / "status.json"
        if not st.exists():
            return 0.0
        t = datetime.fromtimestamp(st.stat().st_mtime)
    return (datetime.now() - t).total_seconds() / 3600


def stuck_reason(o: dict) -> tuple[str, str] | None:
    """(ключ, текст) — что не так с заказом, или None, если всё идёт как надо."""
    if o.get("hidden") or o.get("no_alert") or o.get("status") in ("done", "cancel") or o.get("stage") == "done":
        return None
    oid, stage = str(o["id"]), o.get("stage")
    if not stage:
        return ("legacy", "заказ не попал в автоматическую работу: создан до запуска конвейера, "
                          "задания (brief.json) нет — Claude его не видит")
    if stage in TODO_STAGES:
        rv = WORK_DIR / oid / "review"
        fail = rv / "failed.json"
        if fail.exists():
            try:
                why = json.loads(fail.read_text(encoding="utf-8")).get("reason", "")
            except Exception:  # noqa: BLE001
                why = ""
            return (f"{stage}|failed", f"Claude не смог сделать {KIND_ACC[TODO_STAGES[stage]]}: {why or 'причина не указана'}")
        if (rv / "review.json").exists():
            return None
        h = _hours_since(o)
        if h >= STUCK_HOURS:
            return (f"{stage}|late", f"{KIND_RU[TODO_STAGES[stage]]}: результата нет уже {h:.0f} ч "
                                     f"(Claude берёт заказы каждые 2 часа с 9:27 до 23:27)")
    return None


def stuck_kb(oid, legacy: bool) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    if legacy:
        kb.button(text="🎨 Сделать обложку", callback_data=f"stk:{oid}:cover_todo")
        kb.button(text="📊 Сделать всю презентацию", callback_data=f"stk:{oid}:deck_todo")
    else:
        kb.button(text="🔁 Переделать", callback_data=f"stk:{oid}:redo")
    kb.button(text="🙈 Не напоминать", callback_data=f"stk:{oid}:mute")
    kb.adjust(1)
    return kb.as_markup()


async def watch_stuck(bot: Bot) -> None:
    await asyncio.sleep(60)
    while True:
        try:
            db = load_orders()
            changed = False
            for o in db["orders"].values():
                r = stuck_reason(o)
                if not r:
                    continue
                key, why = r
                last = o.get("alerted_at", "")
                again = True
                if o.get("alerted") == key and last:
                    try:
                        again = (datetime.now() - datetime.strptime(last, "%Y-%m-%d %H:%M")).total_seconds() > STUCK_REPEAT_H * 3600
                    except ValueError:
                        pass
                if not again:
                    continue
                await bot.send_message(
                    ADMIN_ID, f"⚠️ <b>Заказ #{o['id']} не сделан</b>\n«{html.escape(str(o.get('topic', ''))[:80])}»\n\n"
                              f"{html.escape(why)[:600]}", reply_markup=stuck_kb(o["id"], key == "legacy"))
                o["alerted"], o["alerted_at"] = key, datetime.now().strftime("%Y-%m-%d %H:%M")
                changed = True
            if changed:
                save_orders(db)
        except Exception as e:  # noqa: BLE001
            logging.exception("Сторож заказов: %s", e)
        await asyncio.sleep(600)


def ensure_brief(o: dict) -> None:
    """Для старых заказов без задания — собрать brief.json из того, что есть в базе."""
    f = odir(o["id"]) / "brief.json"
    if f.exists():
        return
    t = T["ru"]
    f.write_text(json.dumps({
        "id": o["id"], "client_lang": o.get("lang", "ru"), "topic": o.get("topic", ""),
        "slides": t["slides"].get(o.get("slides"), o.get("slides")), "deadline": "",
        "presentation_lang": o.get("lang", "ru"), "design": "дизайн делаем мы по теме", "template_link": "",
        "need_text": False, "need_notes": False, "need_humor": False,
        "comment": "Старый заказ (до автоматизации): подробностей нет — делай по теме; что неясно — напиши Тимуру в message.",
        "sources": "", "client_will_send_files": False, "client": "", "created": o.get("created", ""),
    }, ensure_ascii=False, indent=1), encoding="utf-8")


@router.callback_query(F.data.startswith("stk:"))
async def stuck_action(cb: CallbackQuery):
    if cb.from_user.id != ADMIN_ID:
        await cb.answer()
        return
    _, oid, act = cb.data.split(":")
    db = load_orders()
    o = db["orders"].get(oid)
    if not o:
        await cb.answer("Заказ не найден", show_alert=True)
        return
    if act == "mute":
        o["no_alert"] = True
        save_orders(db)
        await cb.message.edit_reply_markup(reply_markup=None)
        await cb.answer("Больше не напоминаю об этом заказе")
        return
    stage = o.get("stage") if act == "redo" else act
    if stage not in TODO_STAGES:
        await cb.answer("Заказ уже в другом статусе", show_alert=True)
        return
    ensure_brief(o)
    rv = WORK_DIR / oid / "review"
    for n in ("failed.json", "claim.json"):
        (rv / n).unlink(missing_ok=True)
    add_note(oid, "Владелец (доработать)", "Предыдущая попытка не получилась — сделай заново.")
    o2 = set_stage(oid, stage)
    if o2:
        db = load_orders()
        db["orders"][oid].pop("alerted", None)
        save_orders(db)
    await cb.message.edit_reply_markup(reply_markup=None)
    await cb.message.reply(f"🔁 #{oid} снова в работе ({KIND_ACC[TODO_STAGES[stage]]}). "
                           f"Claude возьмёт его в ближайший запуск (каждые 2 часа, в :27).")
    await cb.answer()


def cover_kb(lang: str, oid) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=T[lang]["cv_ok"], callback_data=f"cv:{oid}:ok")
    kb.button(text=T[lang]["cv_chg"], callback_data=f"cv:{oid}:chg")
    kb.adjust(1)
    return kb.as_markup()


@router.callback_query(F.data.startswith("rv:"))
async def review_action(cb: CallbackQuery, bot: Bot):
    if cb.from_user.id != ADMIN_ID:
        await cb.answer()
        return
    _, oid, act = cb.data.split(":")
    o = load_orders()["orders"].get(oid)
    if not o or not str(o.get("stage", "")).endswith("_review"):
        await cb.answer("Уже обработано", show_alert=True)
        return
    kind = o["stage"][:-7]
    if act == "fix":
        await cb.message.edit_reply_markup(reply_markup=None)
        await bot.send_message(ADMIN_ID, f"✏️ Доработка #{oid}: что исправить? "
                                         f"Ответьте (reply) на это сообщение — текстом, можно со скриншотом.",
                               reply_markup=ForceReply(selective=True))
        await cb.answer()
        return
    sent = sorted(p for p in (WORK_DIR / oid / "review").iterdir() if p.is_file() and not p.name.endswith(".json"))
    man = WORK_DIR / oid / "review" / "review.sent.json"
    names = json.loads(man.read_text(encoding="utf-8")).get("files", []) if man.exists() else []
    files = [WORK_DIR / oid / "review" / n for n in names if (WORK_DIR / oid / "review" / n).exists()] or sent
    lang = o.get("lang", "ru")
    t = T[lang]
    try:
        if kind == "cover":
            await send_files(bot, o["uid"], files, t["cv_ready"].format(id=oid), cover_kb(lang, oid))
            set_stage(oid, "cover_sent", status="cover")
        else:
            arch = WORK_DIR / oid / f"sent_{kind}_{datetime.now():%m%d_%H%M}"
            (WORK_DIR / oid / "review").rename(arch)
            files = [arch / f.name for f in files]
            man_sent = arch / "review.sent.json"
            links = json.loads(man_sent.read_text(encoding="utf-8")).get("links", {}) if man_sent.exists() else {}
            links = {k: v for k, v in links.items() if k in ("gslides", "canva", "view") and str(v).startswith("https://")}
            set_stage(oid, "done", status="done", has_file=True, deliver_dir=str(arch.relative_to(WORK_DIR)),
                      deliver_files=[f.name for f in files], deliver_links=links,
                      **({"link": links.get("gslides") or links.get("canva")} if links else {}))
            fmts = formats_of(files)
            fmts += [k for k in ("gslides", "canva") if k in links or "pptx" in fmts]
            if len(fmts) > 1:
                await bot.send_message(o["uid"], t["fmt_ask"].format(id=oid), reply_markup=formats_kb(lang, oid, fmts))
            else:
                await deliver_formats(bot, oid, "all")
            await cb.message.edit_reply_markup(reply_markup=None)
            await cb.message.reply(f"📨 Готово #{oid}: " + ("клиенту отправлен выбор формата ("
                                   + ", ".join(FMT_LABEL.get(x, x) for x in fmts) + ")." if len(fmts) > 1 else "файл отправлен клиенту."))
            await cb.answer()
            return
    except Exception as e:  # noqa: BLE001
        await cb.answer(f"Не отправилось: {str(e)[:150]}", show_alert=True)
        return
    # архив отправленного, чтобы следующий этап начинался с чистой папки
    arch = WORK_DIR / oid / f"sent_{kind}_{datetime.now():%m%d_%H%M}"
    (WORK_DIR / oid / "review").rename(arch)
    await cb.message.edit_reply_markup(reply_markup=None)
    await cb.message.reply(f"📨 Отправлено клиенту: {KIND_ACC[kind]} #{oid}."
                           + ("\nЖдём, когда клиент одобрит обложку." if kind == "cover" else ""))
    await cb.answer()


# ── выбор формата готовой презентации ──
FMT_LABEL = {"pptx": "PowerPoint", "pdf": "PDF", "docx": "Word", "png": "картинки",
             "gslides": "Google Slides", "canva": "Canva"}


def fmt_of(f: Path) -> str:
    ext = f.suffix.lower().lstrip(".")
    return {"ppt": "pptx", "jpg": "png", "jpeg": "png", "doc": "docx"}.get(ext, ext)


def formats_of(files: list[Path]) -> list[str]:
    order = ["pptx", "pdf", "png", "docx"]
    found = {fmt_of(f) for f in files}
    return [x for x in order if x in found] + sorted(found - set(order))


def formats_kb(lang: str, oid, fmts: list[str]) -> InlineKeyboardMarkup:
    t = T[lang]
    kb = InlineKeyboardBuilder()
    for x in fmts:
        if x == "docx":   # конспект идёт вместе с любым форматом
            continue
        kb.button(text=t["fmt_btn"].get(x, x.upper()), callback_data=f"fmt:{oid}:{x}")
    kb.button(text=t["fmt_all"], callback_data=f"fmt:{oid}:all")
    kb.adjust(2)
    return kb.as_markup()


async def deliver_formats(bot: Bot, oid: str, choice: str) -> bool:
    o = load_orders()["orders"].get(str(oid))
    if not o or not o.get("deliver_dir"):
        return False
    d = WORK_DIR / o["deliver_dir"]
    files = [d / n for n in o.get("deliver_files", []) if (d / n).exists()]
    links = {k: v for k, v in o.get("deliver_links", {}).items() if k != "view"}
    first = not o.get("delivered")
    howto = []
    if choice in ("gslides", "canva") and choice not in links:
        # ссылки нет — даём PPTX и короткую инструкцию, как открыть его в Google Slides / Canva в своём аккаунте
        files = [f for f in files if fmt_of(f) == "pptx" or (first and fmt_of(f) == "docx")]
        howto = [choice]
        links = {}
    elif choice != "all":
        files = [f for f in files if fmt_of(f) == choice or (first and fmt_of(f) == "docx")]
        links = {k: v for k, v in links.items() if k == choice}
    if not files and not links:
        return False
    lang = o.get("lang", "ru")
    t = T[lang]
    if files:
        await send_files(bot, o["uid"], files, t["deck_ready"].format(id=oid) if first and not links else None)
    for k, url in links.items():
        await bot.send_message(o["uid"], t["lnk_" + k].format(url=html.escape(url)), disable_web_page_preview=True)
    for k in howto:
        await bot.send_message(o["uid"], t["how_" + k])
    if first:
        db = load_orders()
        db["orders"][str(oid)]["delivered"] = True
        save_orders(db)
        await bot.send_message(o["uid"], t["done_hint"].strip() + t["fmt_more"], reply_markup=edit_kb(lang, int(oid)))
        await bot.send_message(o["uid"], t["menu_refresh"], reply_markup=main_menu(lang, o["uid"]))
        asyncio.create_task(offer_credit(bot, oid))
    return True


_FMT_RECENT: dict = {}


@router.callback_query(F.data.startswith("fmt:"))
async def format_pick(cb: CallbackQuery, bot: Bot):
    _, oid, choice = cb.data.split(":")
    o = load_orders()["orders"].get(oid) or {}
    if o.get("uid") != cb.from_user.id:
        await cb.answer()
        return
    # защита от двойного нажатия: тот же формат не шлём повторно в течение 2 минут
    key = (cb.from_user.id, oid, choice)
    now = asyncio.get_event_loop().time()
    if now - _FMT_RECENT.get(key, -1e9) < 120:
        await cb.answer(T[o.get("lang", "ru")]["fmt_sending"])
        return
    _FMT_RECENT[key] = now
    await cb.answer(T[o.get("lang", "ru")]["fmt_sending"])
    if not await deliver_formats(bot, oid, choice):
        await cb.message.answer(T[o.get("lang", "ru")]["fmt_none"])


def _canva_target(m: Message):
    src = m.reply_to_message
    if not (m.from_user and m.from_user.id == ADMIN_ID and src and m.text and "canva." in m.text):
        return None
    found = re.match(r"#(\d+) · ", src.caption or src.text or "")
    return found.group(1) if found else None


@admin_router.message(F.func(lambda m: _canva_target(m) is not None))
async def review_canva_link(message: Message):
    oid = _canva_target(message)
    url = _URL_RE.search(message.text or "")
    o = load_orders()["orders"].get(oid)
    if not url or not o:
        return
    url = url.group(0).rstrip(").,;")
    key = "view" if re.search(r"/view(\?|$|/)", url) else "canva"
    if str(o.get("stage", "")).endswith("_review"):
        man = WORK_DIR / oid / "review" / "review.sent.json"
        r = json.loads(man.read_text(encoding="utf-8")) if man.exists() else {}
        r.setdefault("links", {})[key] = url
        man.write_text(json.dumps(r, ensure_ascii=False), encoding="utf-8")
        await message.reply(f"👀 Ссылку для просмотра добавил к #{oid} — клиент сможет листать презентацию в приложении."
                            if key == "view" else f"🎨 Ссылку Canva добавил к #{oid} — клиент увидит её среди форматов.")
    elif o.get("deliver_dir") and key == "view":
        db = load_orders()
        db["orders"][oid].setdefault("deliver_links", {})["view"] = url
        save_orders(db)
        await message.reply(f"👀 Ссылку для просмотра добавил к #{oid} — в приложении у клиента появилась кнопка «Листать презентацию».")
    elif o.get("deliver_dir"):
        db = load_orders()
        db["orders"][oid].setdefault("deliver_links", {})["canva"] = url
        save_orders(db)
        await message.reply(f"🎨 Ссылку Canva добавил к #{oid}. Клиент получит её кнопкой «📦 Все форматы» или я пришлю сейчас:",
                            reply_markup=InlineKeyboardBuilder().button(text="Отправить клиенту", callback_data=f"sendcanva:{oid}").as_markup())


@router.callback_query(F.data.startswith("sendcanva:"))
async def send_canva_now(cb: CallbackQuery, bot: Bot):
    if cb.from_user.id != ADMIN_ID:
        await cb.answer()
        return
    oid = cb.data.split(":")[1]
    ok = await deliver_formats(bot, oid, "canva")
    await cb.answer("Отправлено" if ok else "Нет ссылки", show_alert=not ok)


def _fix_target(m: Message):
    src = m.reply_to_message
    if not (m.from_user and m.from_user.id == ADMIN_ID and src and src.text):
        return None
    found = re.match(r"✏️ Доработка #(\d+)", src.text)
    return found.group(1) if found else None


@admin_router.message(F.func(lambda m: _fix_target(m) is not None))
async def review_fix(message: Message, bot: Bot):
    oid = _fix_target(message)
    o = load_orders()["orders"].get(oid)
    if not o or not str(o.get("stage", "")).endswith("_review"):
        await message.reply("Этот заказ уже не на проверке.")
        return
    kind = o["stage"][:-7]
    add_note(oid, "Владелец (доработать)", message.text or message.caption or "(см. файл)")
    if not message.text:
        await save_refs(bot, oid, [media_ref(message)], sub="edits")
    set_stage(oid, kind + "_todo")
    rv = WORK_DIR / oid / "review"
    if rv.exists():
        rv.rename(WORK_DIR / oid / f"rejected_{kind}_{datetime.now():%m%d_%H%M}")
    await message.reply(f"👌 Записал. Claude переделает {KIND_ACC[kind]} #{oid} и пришлёт снова.")


@router.callback_query(F.data.startswith("cv:"))
async def cover_answer(cb: CallbackQuery, state: FSMContext, bot: Bot):
    _, oid, act = cb.data.split(":")
    o = load_orders()["orders"].get(oid)
    if not o or o["uid"] != cb.from_user.id:
        await cb.answer()
        return
    lang = o.get("lang", "ru")
    t = T[lang]
    await cb.message.edit_reply_markup(reply_markup=None)
    if act == "chg":
        await start_edit(cb.message, state, int(oid), cb.from_user.id, quiet=True)
        await cb.message.answer(t["cv_chg_prompt"])
        await cb.answer()
        return
    if o.get("stage") != "cover_sent":
        await cb.answer()
        return
    if o.get("paid"):
        set_stage(oid, "deck_todo", status="work")
        await cb.message.answer(t["cv_go"])
        await bot.send_message(ADMIN_ID, f"👍 Клиент одобрил обложку #{oid}. Оплачено — Claude делает всю презентацию.")
    else:
        set_stage(oid, "cover_ok")
        await cb.message.answer(t["cv_pay"])
        await send_pay(bot, o["uid"], lang, o["price"], oid)
        await bot.send_message(ADMIN_ID, f"👍 Клиент одобрил обложку #{oid}.\n💰 К оплате: {fmt_sum(o['price'])} сум — "
                                         "реквизиты клиенту отправлены. Когда деньги придут, нажмите кнопку.",
                               reply_markup=InlineKeyboardBuilder().button(text="💰 Оплата получена", callback_data=f"paid:{oid}").as_markup())
    await cb.answer()


async def apply_paid(bot: Bot, oid: str, **extra) -> bool:
    """Отметить заказ оплаченным; если обложка уже согласована — сразу в работу. Возвращает True, если стартовали."""
    o = load_orders()["orders"].get(oid)
    start = o.get("stage") in ("cover_ok", "cover_sent")
    o = set_stage(oid, "deck_todo" if start else o.get("stage"), paid=True, **extra, **({"status": "work"} if start else {}))
    await bot.send_message(o["uid"], T[o.get("lang", "ru")]["paid_go" if start else "paid_early"].format(id=oid))
    return start


@router.callback_query(F.data.startswith("paid:"))
async def mark_paid(cb: CallbackQuery, bot: Bot):
    if cb.from_user.id != ADMIN_ID:
        await cb.answer()
        return
    oid = cb.data.split(":")[1]
    o = load_orders()["orders"].get(oid)
    if not o:
        await cb.answer("Заказ не найден", show_alert=True)
        return
    if o.get("paid"):
        await cb.answer("Уже отмечено как оплаченное")
        return
    start = await apply_paid(bot, oid)
    o = load_orders()["orders"][oid]
    try:
        await cb.message.edit_reply_markup(reply_markup=status_kb(int(oid), o["status"]) if cb.message.text and "ЗАЯВКА" in cb.message.text else None)
    except Exception:  # noqa: BLE001
        pass
    await cb.answer("✅ Оплата отмечена" + (" — Claude делает презентацию" if start else " — презентацию начнём после согласования обложки"),
                    show_alert=True)


async def user_ctx_middleware(handler, event, data):
    u = data.get("event_from_user")
    token = CURRENT_USER.set(u.id if u else None)
    try:
        return await handler(event, data)
    finally:
        CURRENT_USER.reset(token)


# ───────────────────────── ОПИСАНИЕ БОТА ─────────────────────────
BOT_DESCRIPTIONS = [
    (None,
     "🎨 SlideLab — презентации на заказ\n"
     "✏️ Живой PPTX: каждый текст и график редактируется\n"
     "🎁 Обложка бесплатно — оплата только после согласования\n"
     "⏱ Срок обсудим в чате · RU / UZ / EN\n"
     "📢 Примеры работ: @slidelab_uz",
     "Презентации на заказ: живой PPTX, свой дизайн, обложка бесплатно. Примеры — @slidelab_uz"),
    ("uz",
     "🎨 SlideLab — buyurtma asosida taqdimotlar\n"
     "✏️ Jonli PPTX: har bir matn va grafik tahrirlanadi\n"
     "🎁 Muqova bepul — to‘lov faqat kelishuvdan keyin\n"
     "⏱ Muddatni chatda kelishamiz · RU / UZ / EN\n"
     "📢 Ishlar namunasi: @slidelab_uz",
     "Buyurtma asosida taqdimotlar: jonli PPTX, o‘z dizayni, muqova bepul. Namunalar — @slidelab_uz"),
    ("en",
     "🎨 SlideLab — presentations made to order\n"
     "✏️ Editable PPTX: every text and chart can be changed\n"
     "🎁 Free cover — pay only after you approve it\n"
     "⏱ Deadline agreed in the chat · RU / UZ / EN\n"
     "📢 Our work: @slidelab_uz",
     "Presentations made to order: editable PPTX, unique design, free cover. Examples — @slidelab_uz"),
]


# ───────────────────────── АВАТАРКИ ─────────────────────────
# Один раз после обновления: бот ставит фото канала сам, а аватарку бота
# присылает владельцу (её можно поменять только через @BotFather).
BRANDING_VERSION = "v1"
CHANNEL_AVATAR_URL = ("https://d8j0ntlcm91z4.cloudfront.net/user_3Kg776n2YVTxhk4uIcG7vcKL8Pt/"
                      "hf_20261025_142833_a8f65733-3d46-4438-93d5-b6fa07893862.png")
BOT_AVATAR_URL = ("https://d8j0ntlcm91z4.cloudfront.net/user_3Kg776n2YVTxhk4uIcG7vcKL8Pt/"
                  "hf_20261025_142833_4bf80e39-f9dc-464b-b800-e1bf2df7664a.png")


async def _download(url: str) -> bytes:
    import aiohttp
    async with aiohttp.ClientSession() as s:
        async with s.get(url, timeout=aiohttp.ClientTimeout(total=60)) as r:
            r.raise_for_status()
            return await r.read()


async def setup_branding(bot: Bot) -> None:
    flag = Path(__file__).with_name("media") / f"branding_{BRANDING_VERSION}.done"
    if flag.exists() or not ADMIN_ID:
        return
    await asyncio.sleep(3)
    report = []
    try:
        ch = await _download(CHANNEL_AVATAR_URL)
        await bot.set_chat_photo(POST_CHANNEL, BufferedInputFile(ch, "channel.png"))
        report.append("✅ Фото канала обновлено.")
    except Exception as e:  # noqa: BLE001
        logging.exception("Не удалось поставить фото канала: %s", e)
        report.append("⚠️ Фото канала поставить не смог: дайте боту в админах канала право "
                      "«Изменение профиля канала» и напишите мне /branding. "
                      f"Ошибка: <code>{html.escape(str(e))[:200]}</code>")
    try:
        bt = await _download(BOT_AVATAR_URL)
        await bot.send_document(
            ADMIN_ID, BufferedInputFile(bt, "slidelab_bot_avatar.png"),
            caption="🖼 Аватарка для бота. Telegram разрешает менять её только через @BotFather:\n"
                    "1) откройте @BotFather → /setuserpic\n2) выберите @slidelab_order_bot\n"
                    "3) перешлите или отправьте эту картинку.")
    except Exception as e:  # noqa: BLE001
        report.append(f"⚠️ Не смог скачать аватарку бота: <code>{html.escape(str(e))[:200]}</code>")
    try:
        await bot.send_message(ADMIN_ID, "\n".join(report))
    except Exception:  # noqa: BLE001
        pass
    if report and report[0].startswith("✅"):
        flag.parent.mkdir(exist_ok=True)
        flag.write_text("ok", encoding="utf-8")


# ───────────────────────── ЗАПУСК ─────────────────────────
async def main():
    if not BOT_TOKEN:
        raise SystemExit("❌ Не найден BOT_TOKEN. Откройте settings.txt и впишите токен.")
    if not ADMIN_ID:
        print("⚠️  ADMIN_ID не задан — заявки некуда пересылать. "
              "Напишите боту /id и впишите число в settings.txt")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    _BOT_REF.append(bot)
    dp = Dispatcher(storage=MemoryStorage())
    dp.update.outer_middleware(user_ctx_middleware)
    dp.include_router(admin_router)

    # Публикация постов в канал (если настроены ADMIN_ID и канал)
    post_task = None
    if ADMIN_ID and POST_CHANNEL and not POST_CHANNEL.lower().endswith("bot"):
        import publisher
        post_bot = (Bot(POST_BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
                    if POST_BOT_TOKEN else bot)
        dp.include_router(publisher.setup(ADMIN_ID, POST_CHANNEL, post_bot))
        post_task = asyncio.create_task(publisher.loop(bot))
        print(f"📢 Публикация постов включена: канал {POST_CHANNEL}, папка posts")
    else:
        print("ℹ️  Публикация постов выключена: нужен ADMIN_ID и CHANNEL_URL канала в settings.txt")

    dp.include_router(router)
    watcher = asyncio.create_task(watch_for_changes(bot, dp))
    review_task = asyncio.create_task(watch_reviews(bot))  # noqa: F841
    sync_task = asyncio.create_task(github_sync_loop(bot))  # noqa: F841
    stuck_task = asyncio.create_task(watch_stuck(bot))  # noqa: F841
    if POST_CHANNEL:
        asyncio.create_task(setup_branding(bot))
    try:  # описание бота: до «Старт» и в профиле (ru по умолчанию, uz для узбекского Telegram)
        for lc, d, sd in BOT_DESCRIPTIONS:
            await bot.set_my_description(description=d, language_code=lc)
            await bot.set_my_short_description(short_description=sd, language_code=lc)
    except Exception as e:  # noqa: BLE001
        logging.warning("Не удалось обновить описание бота: %s", e)
    if MINIAPP_URL.startswith("https://"):
        try:  # кнопка «Открыть» слева от поля ввода в чате с ботом
            from aiogram.types import MenuButtonWebApp
            await bot.set_chat_menu_button(menu_button=MenuButtonWebApp(
                text="Открыть", web_app=WebAppInfo(url=MINIAPP_URL)))
        except Exception as e:  # noqa: BLE001
            logging.warning("Не удалось поставить кнопку меню: %s", e)
        refresh_menu_buttons()   # личные кнопки с заказами — всем, у кого есть заказы
    print("✅ Бот SlideLab запущен. Не закрывайте это окно. Остановить: Ctrl+C")
    print("🔄 Автоперезапуск включён: после изменений бот перезапустится сам.")
    await dp.start_polling(bot, handle_signals=False)
    watcher.cancel()
    if post_task:
        post_task.cancel()
    await bot.session.close()
    if _restart_requested:
        sys.exit(RESTART_CODE)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Бот остановлен.")
    except SystemExit as e:
        if e.code == RESTART_CODE:
            sys.exit(RESTART_CODE)
        if e.code not in (None, 0):
            print(e.code)
            sys.exit(1)
