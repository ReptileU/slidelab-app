"""Премиум-эмодзи в сообщениях и на кнопках бота.

С Bot API 9.4 бот может показывать анимированные премиум-эмодзи в личных чатах и группах,
если у владельца бота есть Telegram Premium. Каналы не поддерживаются.

Как устроено:
- в текстах (core/i18n) стоят метки ⟦ключ⟧ или ⟦ключ|запасной эмодзи⟧;
- владелец присылает боту «/emoji ключ <премиум-эмодзи>» — id сохраняется в content/emoji.json;
- перед отправкой каждого сообщения middleware меняет метку на <tg-emoji>, а если для ключа
  ничего не выбрано — на запасной эмодзи (или убирает метку совсем). Клиент меток не видит никогда;
- кнопкам меню и анкеты (ключи btn_*, ds_*, dl_*, fmt_*…) ставится значок icon_custom_emoji_id.
"""

from __future__ import annotations

import html
import json
import logging
import re
import threading
from pathlib import Path
from typing import Any

from aiogram import Bot
from aiogram.client.session.middlewares.base import BaseRequestMiddleware, NextRequestMiddlewareType
from aiogram.methods import TelegramMethod
from aiogram.methods.base import TelegramType
from aiogram.types import InlineKeyboardMarkup, ReplyKeyboardMarkup

log = logging.getLogger(__name__)

MARK = re.compile(r"⟦([a-z_]+)(?:\|([^⟧]*))?⟧ ?")

# Метки в текстах: ключ → что это (для подсказки в /emoji)
MARKS: dict[str, str] = {
    "logo": "приветствие и главное меню",
    "price": "цены и оплата",
    "pack": "пакеты",
    "gift": "подарок за пакет",
    "works": "примеры работ",
    "help": "вопросы и ответ менеджера",
    "order": "заказ принят",
    "cover": "обложка готова",
    "paid": "оплата получена",
    "done": "презентация готова",
    "revise": "правки",
    "orders": "мои заказы",
    "star": "звёзды Telegram",
}

# Поля сообщения, где может быть текст с метками
TEXT_FIELDS = ("text", "caption")


class EmojiStore:
    """content/emoji.json: {"marks": {"logo": {"id": "...", "alt": "💎"}}, "buttons": {"btn_new": {...}}}."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()
        self._mtime = -1.0
        self._data: dict[str, dict[str, dict[str, str]]] = {"marks": {}, "buttons": {}}

    def data(self) -> dict[str, dict[str, dict[str, str]]]:
        try:
            mtime = self.path.stat().st_mtime
        except FileNotFoundError:
            return {"marks": {}, "buttons": {}}
        if mtime != self._mtime:
            with self._lock:
                try:
                    raw = json.loads(self.path.read_text(encoding="utf-8"))
                    self._data = {"marks": dict(raw.get("marks") or {}), "buttons": dict(raw.get("buttons") or {})}
                except (OSError, ValueError) as e:
                    log.warning("emoji.json не прочитан: %s", e)
                self._mtime = mtime
        return self._data

    def set(self, group: str, key: str, emoji_id: str | None, alt: str = "") -> None:
        data = {g: dict(v) for g, v in self.data().items()}
        if emoji_id:
            data[group][key] = {"id": emoji_id, "alt": alt}
        else:
            data[group].pop(key, None)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(self.path)


def render(text: str, marks: dict[str, dict[str, str]], premium: bool) -> str:
    """Метки → <tg-emoji> (premium) или запасной эмодзи / ничего."""
    if "⟦" not in text:
        return text

    def sub(m: re.Match[str]) -> str:
        key, fallback = m.group(1), m.group(2) or ""
        item = marks.get(key)
        if premium and item and item.get("id"):
            alt = html.escape(item.get("alt") or fallback or "⭐")
            return f'<tg-emoji emoji-id="{html.escape(item["id"])}">{alt}</tg-emoji> '
        return f"{fallback} " if fallback else ""

    return MARK.sub(sub, text)


def strip(text: str) -> str:
    """Убрать метки совсем — для мест, где разметка не нужна (Mini App, логи)."""
    return render(text, {}, premium=False)


def _button_keys() -> dict[str, str]:
    """Текст кнопки на любом языке → ключ (btn_new, ds_ours…)."""
    from slidelab.core.i18n import TEXTS

    out: dict[str, str] = {}
    for texts in TEXTS.values():
        for key, value in texts.items():
            if key.startswith(("btn_", "ds_", "dl_", "fmt_", "slides_", "plang_", "x_")) and "{" not in value:
                out.setdefault(strip(value), key)
    return out


def button_keys() -> dict[str, str]:
    global _BUTTONS
    if _BUTTONS is None:
        _BUTTONS = _button_keys()
    return _BUTTONS


_BUTTONS: dict[str, str] | None = None


def _with_icons(markup: Any, icons: dict[str, dict[str, str]]) -> Any:
    if not icons or not isinstance(markup, (ReplyKeyboardMarkup, InlineKeyboardMarkup)):
        return markup
    keys = button_keys()
    attr = "keyboard" if isinstance(markup, ReplyKeyboardMarkup) else "inline_keyboard"
    changed = False
    rows = []
    for row in getattr(markup, attr):
        new_row = []
        for btn in row:
            key = keys.get(btn.text)
            item = icons.get(key or "")
            if item and item.get("id") and not getattr(btn, "icon_custom_emoji_id", None):
                btn = btn.model_copy(update={"icon_custom_emoji_id": item["id"]})
                changed = True
            new_row.append(btn)
        rows.append(new_row)
    return markup.model_copy(update={attr: rows}) if changed else markup


class PremiumEmojiMiddleware(BaseRequestMiddleware):
    def __init__(self, store: EmojiStore) -> None:
        self.store = store

    async def __call__(
        self,
        make_request: NextRequestMiddlewareType[TelegramType],
        bot: Bot,
        method: TelegramMethod[TelegramType],
    ) -> Any:
        try:
            method = self._apply(method)
        except Exception:  # оформление не должно ломать отправку
            log.exception("Премиум-эмодзи: не удалось обработать %s", type(method).__name__)
        return await make_request(bot, method)

    def _apply(self, method: TelegramMethod[TelegramType]) -> TelegramMethod[TelegramType]:
        update: dict[str, Any] = {}
        has_text = any(isinstance(getattr(method, f, None), str) and "⟦" in getattr(method, f) for f in TEXT_FIELDS)
        markup = getattr(method, "reply_markup", None)
        if not has_text and markup is None:
            return method
        data = self.store.data()
        chat_id = getattr(method, "chat_id", None)
        # премиум — только в личных чатах и группах (каналы Telegram не пускает; id канала тоже отрицательный,
        # поэтому для надёжности — только личные чаты)
        premium = isinstance(chat_id, int) and chat_id > 0
        for field in TEXT_FIELDS:
            value = getattr(method, field, None)
            if isinstance(value, str) and "⟦" in value:
                update[field] = render(value, data["marks"], premium)
        if markup is not None and premium:
            new = _with_icons(markup, data["buttons"])
            if new is not markup:
                update["reply_markup"] = new
        return method.model_copy(update=update) if update else method


def install(bot: Bot, content_dir: Path) -> EmojiStore:
    store = EmojiStore(Path(content_dir) / "emoji.json")
    bot.session.middleware(PremiumEmojiMiddleware(store))
    return store
