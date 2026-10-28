"""Поддельный Telegram Bot API: запоминает вызовы и отвечает правдоподобными объектами."""

import types
import typing
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from itertools import count
from typing import Any

from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.methods import TelegramMethod
from aiogram.types import Chat, File, ForumTopic, Message, MessageId, TelegramObject, User

TOKEN = "42:TEST-token-for-slidelab"


class FakeSession(BaseSession):
    def __init__(self) -> None:
        super().__init__()
        self.calls: list[TelegramMethod[Any]] = []
        self._ids = count(100)

    def of(self, name: str) -> list[Any]:
        return [c for c in self.calls if type(c).__name__ == name]

    async def make_request(self, bot: Bot, method: TelegramMethod[Any], timeout: int | None = None) -> Any:
        self.calls.append(method)
        result = self._result(method, method.__returning__)
        # как в настоящем aiogram: ответы привязаны к боту (message.delete() и т.п. работают)
        return result.as_(bot) if isinstance(result, TelegramObject) else result

    def _result(self, method: TelegramMethod[Any], returning: Any) -> Any:
        origin = typing.get_origin(returning)
        if origin in (typing.Union, types.UnionType):
            returning = typing.get_args(returning)[0]
        if returning is bool:
            return True
        if returning is str:
            return "https://t.me/$fake_invoice"
        if returning is Message:
            chat_id = getattr(method, "chat_id", 1)
            return Message(
                message_id=next(self._ids),
                date=datetime.now(UTC),
                chat=Chat(id=int(chat_id), type="private"),
            )
        if returning is MessageId:
            return MessageId(message_id=next(self._ids))
        if returning is ForumTopic:
            return ForumTopic(message_thread_id=next(self._ids), name="topic", icon_color=0)
        if returning is File:
            return File(file_id="f", file_unique_id="u", file_path="cover.jpg")
        if returning is User:
            return User(id=42, is_bot=True, first_name="SlideLab")
        return True

    async def stream_content(
        self,
        url: str,
        headers: dict[str, Any] | None = None,
        timeout: int = 30,
        chunk_size: int = 65536,
        raise_for_status: bool = True,
    ) -> AsyncGenerator[bytes, None]:
        yield b"\x89PNG fake"

    async def close(self) -> None:
        pass


def make_bot() -> tuple[Bot, FakeSession]:
    session = FakeSession()
    return Bot(TOKEN, session=session), session
