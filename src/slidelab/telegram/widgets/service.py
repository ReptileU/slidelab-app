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
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

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
    if q.data.startswith("p:"):
        await handle_pay_query(dp, bot, q)
        return
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


async def _username(bot: Bot) -> str | None:
    try:
        return (await bot.me()).username
    except TelegramAPIError:
        return None


async def send_status_card(bot: Bot, order: Order, user: User, store: CardStore) -> None:
    lang = cards.lang_or_ru(user.lang)
    state = cards.status_state(order, lang, await _username(bot))
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
        state = cards.status_state(order, cards.lang_or_ru(card.get("lang")), await _username(bot))
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


# --- оплата переводом на карту -------------------------------------------------------------


async def send_pay_card(
    bot: Bot,
    user: User,
    store: CardStore,
    *,
    title: str,
    amount: str,
    hint: str,
    card_list: list[tuple[str, str]],
    name: str,
    kind: str,
    ref: str,
    credit: int,
    markup: InlineKeyboardMarkup | None,
) -> bool:
    """Карточка оплаты: номера карт копируются касанием, «Я оплатил» → просим чек. False — не принята."""
    lang = cards.lang_or_ru(user.lang)
    data: dict[str, Any] = {
        "t": title,
        "a": amount,
        "h": hint,
        "cs": [[label, num] for label, num in card_list],
        "n": name,
        "k": kind,
        "r": ref,
        "c": credit,
        "st": 0,
    }
    try:
        msg = await bot(
            SendWidget(
                chat_id=user.tg_id,
                html=cards.pay_html(lang),
                caption=cards.PAY_TEXTS[lang]["caption"],
                chat_data=cards.pay_state(data),
                allow_queries=True,
                reply_markup=markup,
            )
        )
    except (TelegramAPIError, ValueError) as e:
        log.warning("Карточка оплаты не отправилась: %s", e)
        return False
    store.update(f"pay:{user.tg_id}:{msg.message_id}", {"data": data})
    return True


async def set_pay_step(bot: Bot, store: CardStore, chat_id: int, message_id: int, st: int) -> None:
    key = f"pay:{chat_id}:{message_id}"
    card = store.load().get(key)
    if not card:
        return
    data = dict(card["data"], st=st)
    if await edit_data(bot, chat_id, message_id, cards.pay_state(data)):
        store.update(key, {"data": data})


async def handle_pay_query(dp: Dispatcher, bot: Bot, q: WidgetQuery) -> None:
    """«Я оплатил» в карточке — как кнопка «Я оплатил картой»: ждём чек, карточка просит скриншот."""
    from slidelab.core.i18n import t
    from slidelab.telegram.states import ReceiptForm

    parsed = cards.parse_pay_request(q.data)
    tg = q.from_user
    if parsed is None or tg is None or q.chat_id is None:
        await bot(AnswerWidgetQuery(widget_query_id=q.id, data="bad"))
        return
    kind, ref, credit = parsed
    state = dp.fsm.get_context(bot, chat_id=q.chat_id, user_id=tg.id)
    await state.set_state(ReceiptForm.waiting)
    await state.update_data(kind=kind, ref=ref, credit=credit, w_msg=q.message_id)
    await bot(AnswerWidgetQuery(widget_query_id=q.id, data="ok"))
    store = store_for(dp["settings"].data_dir)
    if q.message_id:
        await set_pay_step(bot, store, q.chat_id, q.message_id, 1)
    sessionmaker: async_sessionmaker[AsyncSession] = dp["sessionmaker"]
    async with sessionmaker() as session:
        user = await repo.get_user_by_tg(session, tg.id)
    await bot.send_message(q.chat_id, t(user.lang if user else None, "receipt_ask"))


def remember_payment(store: CardStore, payment_id: int, chat_id: int, message_id: int) -> None:
    """Чек получен: запоминаем, какую карточку отметить «оплата подтверждена»."""
    store.update(f"payment:{payment_id}", {"chat_id": chat_id, "message_id": message_id})


async def payment_confirmed(bot: Bot, store: CardStore, payment_id: int) -> None:
    card = store.load().get(f"payment:{payment_id}")
    if not card:
        return
    await set_pay_step(bot, store, card["chat_id"], card["message_id"], 3)
    store.update(f"payment:{payment_id}", None)
    store.update(f"pay:{card['chat_id']}:{card['message_id']}", None)
