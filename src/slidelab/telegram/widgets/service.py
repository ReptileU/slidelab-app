"""Отправка карточек, ответы на запросы из них и живое обновление статуса заказа."""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from slidelab.core import repositories as repo
from slidelab.core.enums import OrderStatus
from slidelab.core.models import Order, User
from slidelab.core.services.packages import PackageService

from . import cards
from .api import AnswerWidgetQuery, EditMessageWidgetData, SendWidget, WidgetQuery

if TYPE_CHECKING:
    from aiogram import Dispatcher

log = logging.getLogger(__name__)
STATUS_EVERY = 20  # секунд между проверками статусов
FINAL = {OrderStatus.DONE, OrderStatus.CANCELLED}


class WidgetForm(StatesGroup):
    topic = State()  # после «Заказать» в карточке ждём тему сообщением


class CardStore:
    """data/widgets.json: какие сообщения-карточки обновлять. Пишут и бот, и API — запись атомарная."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()

    def load(self) -> dict[str, Any]:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _save(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(f".{threading.get_ident()}.tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.path)

    def update(self, key: str, value: dict[str, Any] | None) -> None:
        with self._lock:
            data = self.load()
            if value is None:
                data.pop(key, None)
            else:
                data[key] = value
            self._save(data)


def store_for(data_dir: Path) -> CardStore:
    return CardStore(Path(data_dir) / "widgets.json")


# --- карточка заказа ------------------------------------------------------------


async def _price_state(session: AsyncSession, user: User, st: int = 0, order_id: int | None = None) -> str:
    rules = await repo.get_price_rules(session)
    first = not await repo.has_orders(session, user.id)
    package = await PackageService(session).balance(user.id)
    prices, olds = cards.price_table(rules, first_order=first, package=package)
    return cards.order_state(prices, olds, st, order_id)


async def send_order_card(
    bot: Bot, session: AsyncSession, user: User, store: CardStore, fallback: InlineKeyboardMarkup | None = None
) -> bool:
    """Карточка «Новая презентация». False — Telegram не принял (старый клиент API и т. п.)."""
    lang = cards.lang_or_ru(user.lang)
    try:
        msg = await bot(
            SendWidget(
                chat_id=user.tg_id,
                html=cards.order_html(lang),
                caption=str(cards.ORDER_TEXTS[lang]["caption"]),
                chat_data=await _price_state(session, user),
                allow_queries=True,
                reply_markup=fallback,
            )
        )
    except (TelegramAPIError, ValueError) as e:
        log.warning("Карточка заказа не отправилась: %s", e)
        return False
    store.update(f"form:{user.tg_id}", {"chat_id": user.tg_id, "message_id": msg.message_id})
    return True


async def handle_query(dp: Dispatcher, bot: Bot, raw: dict[str, Any]) -> None:
    """Тап «Заказать» в карточке: запоминаем выбор, просим тему, карточка показывает «напишите тему»."""
    q = WidgetQuery.parse(raw)
    choice = cards.parse_order_request(q.data)
    tg = q.from_user
    if choice is None or tg is None or q.chat_id is None:
        await bot(AnswerWidgetQuery(widget_query_id=q.id, data="bad"))
        return
    tier, deadline, plang, text, notes, humor = choice
    state = dp.fsm.get_context(bot, chat_id=q.chat_id, user_id=tg.id)
    await state.set_state(WidgetForm.topic)
    await state.update_data(
        w_slides=tier.value,
        w_deadline=deadline.value,
        w_plang=plang.value,
        w_text=text,
        w_notes=notes,
        w_humor=humor,
        w_msg=q.message_id,
    )
    await bot(AnswerWidgetQuery(widget_query_id=q.id, data="ok"))
    sessionmaker: async_sessionmaker[AsyncSession] = dp["sessionmaker"]
    async with sessionmaker() as session:
        user = await repo.get_user_by_tg(session, tg.id)
        if user is None:
            return
        lang = cards.lang_or_ru(user.lang)
        if q.message_id:
            await edit_data(bot, q.chat_id, q.message_id, await _price_state(session, user, st=1))
    await bot.send_message(q.chat_id, str(cards.ORDER_TEXTS[lang]["ask"]))


async def edit_data(bot: Bot, chat_id: int, message_id: int, chat_data: str) -> bool:
    try:
        await bot(EditMessageWidgetData(chat_id=chat_id, message_id=message_id, chat_data=chat_data))
    except TelegramBadRequest as e:
        if "not modified" in str(e):
            return True
        log.info("Карточка %s/%s не обновилась: %s", chat_id, message_id, e)
        return False
    except TelegramAPIError as e:
        log.info("Карточка %s/%s не обновилась: %s", chat_id, message_id, e)
        return False
    return True


async def order_placed(bot: Bot, session: AsyncSession, user: User, message_id: int | None, order: Order) -> None:
    """Заказ из карточки создан: карточка показывает «Заказ #N принят»."""
    if message_id:
        await edit_data(bot, user.tg_id, message_id, await _price_state(session, user, st=2, order_id=order.id))


# --- статус заказа ----------------------------------------------------------------


async def send_status_card(bot: Bot, order: Order, user: User, store: CardStore) -> None:
    lang = cards.lang_or_ru(user.lang)
    state = cards.status_state(order, lang)
    try:
        msg = await bot(
            SendWidget(
                chat_id=user.tg_id,
                html=cards.status_html(lang),
                caption=cards.status_caption(order, lang),
                chat_data=state,
            )
        )
    except (TelegramAPIError, ValueError) as e:
        log.warning("Карточка статуса заказа #%s не отправилась: %s", order.id, e)
        return
    store.update(
        f"order:{order.id}",
        {"chat_id": user.tg_id, "message_id": msg.message_id, "lang": lang.value, "state": state},
    )


async def refresh_statuses(bot: Bot, session: AsyncSession, store: CardStore) -> int:
    """Карточки статуса, у которых заказ сменил стадию, — обновить. Итоговые после обновления забываем."""
    changed = 0
    for key, card in list(store.load().items()):
        if not key.startswith("order:"):
            continue
        order = await session.get(Order, int(key.split(":", 1)[1]))
        if order is None:
            store.update(key, None)
            continue
        state = cards.status_state(order, cards.lang_or_ru(card.get("lang")))
        if state != card.get("state"):
            ok = await edit_data(bot, card["chat_id"], card["message_id"], state)
            if not ok:
                store.update(key, None)  # сообщение удалили или виджет недоступен
                continue
            changed += 1
            card["state"] = state
            store.update(key, None if order.status in FINAL else card)
        elif order.status in FINAL:
            store.update(key, None)
    return changed


async def watch_statuses(bot: Bot, sessionmaker: async_sessionmaker[AsyncSession], store: CardStore) -> None:
    while True:
        await asyncio.sleep(STATUS_EVERY)
        try:
            async with sessionmaker() as session:
                await refresh_statuses(bot, session, store)
        except Exception:
            log.exception("Обновление карточек статуса")
