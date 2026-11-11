"""Методы Bot API 10.4 для виджетов — пока их нет в aiogram."""

from __future__ import annotations

import zlib
from typing import Any

from aiogram.methods import TelegramMethod
from aiogram.types import InlineKeyboardMarkup, Message, TelegramObject, User

HTML_MAX = 32768  # байт UTF-8
HTML_ZLIB_MAX = 4096  # байт после zlib -9
DATA_MAX = 1024  # байт состояния (chat_data / public_data)


class WidgetTooLarge(ValueError):
    pass


def check_html(html: str) -> str:
    raw = html.encode()
    packed = len(zlib.compress(raw, 9))
    if len(raw) > HTML_MAX or packed > HTML_ZLIB_MAX:
        raise WidgetTooLarge(f"виджет {len(raw)} байт, сжатый {packed} (лимиты {HTML_MAX}/{HTML_ZLIB_MAX})")
    return html


def check_data(data: str) -> str:
    if len(data.encode()) > DATA_MAX:
        raise WidgetTooLarge(f"состояние виджета {len(data.encode())} байт > {DATA_MAX}")
    return data


class SendWidget(TelegramMethod[Message]):
    __returning__ = Message
    __api_method__ = "sendWidget"

    chat_id: int
    html: str
    caption: str | None = None
    parse_mode: str | None = None
    width: int | None = None
    height: int | None = None
    chat_data: str | None = None
    public_data: str | None = None
    allow_queries: bool | None = None
    reply_markup: InlineKeyboardMarkup | None = None


class AnswerWidgetQuery(TelegramMethod[bool]):
    __returning__ = bool
    __api_method__ = "answerWidgetQuery"

    widget_query_id: str
    data: str | None = None


class EditMessageWidgetData(TelegramMethod[Any]):
    """Возвращает Message или True — нам результат не нужен."""

    __returning__ = Any
    __api_method__ = "editMessageWidgetData"

    chat_id: int
    message_id: int
    chat_data: str | None = None
    public_data: str | None = None


class WidgetQuery(TelegramObject):
    """Запрос из виджета: TelegramWidget.request(data) → бот."""

    id: str
    data: str
    from_user: User | None = None
    chat_id: int | None = None
    message_id: int | None = None

    @classmethod
    def parse(cls, raw: dict[str, Any]) -> WidgetQuery:
        chat = raw.get("chat") or {}
        return cls(
            id=str(raw["id"]),
            data=str(raw.get("data", "")),
            from_user=User.model_validate(raw["from"]) if raw.get("from") else None,
            chat_id=chat.get("id"),
            message_id=raw.get("message_id"),
        )
