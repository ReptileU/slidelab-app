"""Сквозные сценарии бота: апдейты Telegram → Dispatcher → БД и папка конвейера → вызовы Bot API."""

import json
import re
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from itertools import count
from pathlib import Path
from typing import Any

import pytest
from aiogram import Bot
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery,
    Chat,
    Document,
    Message,
    ReplyKeyboardMarkup,
    SuccessfulPayment,
    Update,
    User,
    WebAppData,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from fakes import TOKEN, FakeSession, make_bot
from slidelab.bot import tasks
from slidelab.bot.main import build_dispatcher
from slidelab.config import Settings
from slidelab.core.enums import Lang, OrderStatus, PaymentProvider, PaymentStatus, Stage
from slidelab.core.models import Base, Order, Payment
from slidelab.core.models import User as DbUser
from slidelab.core.seed import seed
from slidelab.telegram.callbacks import FmtCb, FormCb, LangCb, MgrCb, OrderCb, PayCb, QuickCb
from slidelab.telegram.flows import Flows
from slidelab.telegram.notifier import Notifier

CLIENT, ADMIN = 777, 555
ids = count(1)


class SessionmakerProxy:
    """Роутеры aiogram подключаются к диспетчеру один раз — диспетчер общий, а БД у каждого теста своя."""

    current: async_sessionmaker[AsyncSession] | None = None

    def __call__(self) -> AsyncSession:
        assert self.current is not None
        return self.current()


PROXY = SessionmakerProxy()
SETTINGS = Settings(  # type: ignore[call-arg]
    _env_file=None,
    bot_token=TOKEN,
    admin_id=ADMIN,
    pay_uzum="8600 1234 5678 9012",
    pay_name="Тимур",
    legacy_webapp=True,
)
DP = build_dispatcher(SETTINGS, storage=MemoryStorage(), sessionmaker=PROXY)  # type: ignore[arg-type]


class Harness:
    def __init__(self, bot: Bot, tg: FakeSession, sm: async_sessionmaker[AsyncSession], work: Path) -> None:
        self.bot, self.tg, self.sm, self.work = bot, tg, sm, work

    async def send(self, update: Update) -> None:
        await DP.feed_update(self.bot, update)

    async def text(self, text: str, *, user: int = CLIENT, reply_to: Message | None = None) -> None:
        await self.send(Update(update_id=next(ids), message=msg(user, text=text, reply_to_message=reply_to)))

    async def message(self, user: int = CLIENT, **kwargs: Any) -> None:
        await self.send(Update(update_id=next(ids), message=msg(user, **kwargs)))

    async def click(self, data: str, *, user: int = CLIENT) -> None:
        cb = CallbackQuery(
            id=str(next(ids)), from_user=tg_user(user), chat_instance="x", data=data, message=msg(user, text="…")
        )
        await self.send(Update(update_id=next(ids), callback_query=cb))

    def sent(self, method: str, chat_id: int) -> list[Any]:
        return [m for m in self.tg.of(method) if m.chat_id == chat_id]

    def texts(self, chat_id: int) -> list[str]:
        return [m.text for m in self.sent("SendMessage", chat_id)]

    async def order(self) -> Order:
        async with self.sm() as s:
            order = await s.scalar(select(Order).order_by(Order.id.desc()).limit(1))
            assert order is not None
            return order

    def status_json(self, order_id: int) -> dict[str, Any]:
        data: dict[str, Any] = json.loads((self.work / str(order_id) / "status.json").read_text(encoding="utf-8"))
        return data

    def claude_delivers(self, order_id: int, kind: str, files: list[str]) -> None:
        """Сессия Claude кладёт результат в review/."""
        rv = self.work / str(order_id) / "review"
        rv.mkdir(parents=True, exist_ok=True)
        for name in files:
            (rv / name).write_bytes(b"result")
        (rv / "review.json").write_text(json.dumps({"kind": kind, "files": files, "message": "готово"}), "utf-8")

    async def run_reviews(self) -> int:
        async with self.sm() as s:
            return await tasks.check_reviews(Flows(Notifier(self.bot, s, SETTINGS)), s)

    async def run_stuck(self) -> int:
        async with self.sm() as s:
            return await tasks.check_stuck(Flows(Notifier(self.bot, s, SETTINGS)), s)


def tg_user(user_id: int) -> User:
    return User(id=user_id, is_bot=False, first_name="Тимур" if user_id == ADMIN else "Аня", username="anya")


def msg(user_id: int, **kwargs: Any) -> Message:
    return Message(
        message_id=next(ids),
        date=datetime.now(UTC),
        chat=Chat(id=user_id, type="private"),
        from_user=tg_user(user_id),
        **kwargs,
    )


def bot_msg(chat_id: int, text: str) -> Message:
    return Message(
        message_id=next(ids),
        date=datetime.now(UTC),
        chat=Chat(id=chat_id, type="private"),
        from_user=User(id=42, is_bot=True, first_name="SlideLab"),
        text=text,
    )


@pytest.fixture
async def h(tmp_path: Path) -> AsyncIterator[Harness]:
    engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = async_sessionmaker(engine, expire_on_commit=False)
    async with sm() as s:
        await seed(s)
        await s.commit()
    PROXY.current = sm
    DP.fsm.storage = MemoryStorage()
    SETTINGS.work_dir = tmp_path
    bot, tg = make_bot()
    yield Harness(bot, tg, sm, tmp_path)
    await engine.dispose()


async def onboard(h: Harness) -> None:
    await h.text("/start")
    await h.click(LangCb(code=Lang.RU).pack())


async def order_in_chat(h: Harness, topic: str = "Экономика Японии после 1990 года") -> Order:
    await h.text("Новая презентация")
    await h.text(topic)
    await h.click(FormCb(field="slides", value="s20").pack())
    await h.click(FormCb(field="deadline", value="normal").pack())
    await h.click(FormCb(field="plang", value="ru").pack())
    await h.click(FormCb(field="design", value="ours").pack())
    await h.click(FormCb(field="extra", value="humor").pack())
    await h.click(FormCb(field="extra", value="next").pack())
    await h.click(FormCb(field="files", value="skip").pack())
    await h.click(FormCb(field="action", value="send").pack())
    return await h.order()


# --- вход -------------------------------------------------------------------------


async def test_first_start_asks_language_then_shows_menu(h: Harness) -> None:
    await h.text("/start")
    assert "Tilni tanlang" in h.texts(CLIENT)[-1]
    await h.click(LangCb(code=Lang.UZ).pack())
    last = h.sent("SendMessage", CLIENT)[-1]
    assert last.text.startswith("<b>SlideLab</b>\nMavzuingizga")
    menu = last.reply_markup
    assert isinstance(menu, ReplyKeyboardMarkup)
    app = menu.keyboard[0][0].web_app
    assert app is not None and "lang=uz" in app.url and "n=9900" in app.url  # старая витрина с данными клиента
    assert [b.text for b in menu.keyboard[1]] == ["Yangi taqdimot", "Buyurtmalarim"]


async def test_prices_from_database(h: Harness) -> None:
    await onboard(h)
    await h.text("Цены")
    assert "29 000 сум" in h.texts(CLIENT)[-1] and "9 900" in h.texts(CLIENT)[-1]


# --- заказ в чате ----------------------------------------------------------------


async def test_order_dialog(h: Harness) -> None:
    await onboard(h)
    order = await order_in_chat(h)
    assert (order.price, order.status, order.stage, order.need_humor) == (
        29000,
        OrderStatus.NEW,
        Stage.COVER_TODO,
        True,
    )
    assert order.contact == "@anya"

    brief = json.loads((h.work / str(order.id) / "brief.json").read_text(encoding="utf-8"))
    assert brief["topic"] == "Экономика Японии после 1990 года" and brief["need_humor"] is True

    card = h.texts(ADMIN)[-1]
    assert f"Заказ #{order.id}" in card and "ID: <code>777</code>" in card and "с юмором" in card
    assert any(f"Заказ #{order.id} принят" in m for m in h.texts(CLIENT))
    pay = h.sent("SendMessage", CLIENT)[-1]
    assert "8600 1234 5678 9012" in pay.text and "Обложку делаем бесплатно" in pay.text
    assert pay.reply_markup.inline_keyboard[0][0].url == "https://t.me/$fake_invoice"  # звёзды — ссылкой


async def test_quick_order_from_forwarded_file(h: Harness) -> None:
    await onboard(h)
    doc = Document(file_id="lecture-1", file_unique_id="l1", file_name="lecture.pdf")
    await h.message(document=doc)
    await h.click(QuickCb(field="slides", value="s10").pack())
    await h.click(QuickCb(field="deadline", value="relaxed").pack())
    order = await h.order()
    assert order.topic == "По файлу: lecture.pdf" and order.price == 9900
    assert (h.work / str(order.id) / "files" / "lecture.pdf").exists()  # материал скачан для Claude


async def test_legacy_web_app_order(h: Harness) -> None:
    data = {
        "v": 1,
        "lang": "en",
        "topic": "Japan after 1990",
        "slides": "s10",
        "deadline": "d2",
        "plang": "en",
        "design": "ours",
        "text": True,
        "notes": False,
        "humor": True,
        "style": "Minimal",
    }
    await h.message(web_app_data=WebAppData(data=json.dumps(data), button_text="Order"))
    order = await h.order()
    assert (order.topic, order.price, order.need_humor) == ("Japan after 1990", 9900 + 5000, True)
    assert order.comment == "Стиль из витрины: Minimal."
    async with h.sm() as s:
        user = await s.scalar(select(DbUser).where(DbUser.tg_id == CLIENT))
        assert user is not None and user.lang is Lang.EN


# --- полный цикл через конвейер ---------------------------------------------------------


async def test_full_pipeline_cycle(h: Harness) -> None:
    await onboard(h)
    order = await order_in_chat(h)

    # Claude сделал обложку → владельцу на проверку
    h.claude_delivers(order.id, "cover", ["cover.png"])
    assert await h.run_reviews() == 1
    assert h.sent("SendPhoto", ADMIN)[-1].caption == f"#{order.id} · Обложка"
    assert h.status_json(order.id)["stage"] == "cover_review"

    # владелец: «Отправить клиенту»
    await h.click(MgrCb(action="rv_send", order_id=order.id).pack(), user=ADMIN)
    assert f"Обложка к заказу #{order.id}" in h.sent("SendPhoto", CLIENT)[-1].caption
    assert (await h.order()).status is OrderStatus.COVER

    # клиент: «Нравится» → ждём оплату
    await h.click(OrderCb(action="cover_ok", order_id=order.id).pack())
    assert (await h.order()).status is OrderStatus.AWAITING_PAYMENT
    assert h.status_json(order.id)["stage"] == "cover_ok"

    # Telegram подтверждает звёзды (платёж создан вместе со ссылкой на оплату)
    async with h.sm() as s:
        payment = await s.scalar(
            select(Payment)
            .where(Payment.order_id == order.id, Payment.provider == PaymentProvider.STARS)
            .order_by(Payment.id.desc())
        )
        assert payment is not None
    paid = SuccessfulPayment(
        currency="XTR",
        total_amount=payment.amount,
        invoice_payload=f"pay:{payment.id}",
        telegram_payment_charge_id="charge-1",
        provider_payment_charge_id="p-1",
    )
    await h.message(successful_payment=paid)
    order = await h.order()
    assert (order.status, order.stage, order.is_paid) == (OrderStatus.WORK, Stage.DECK_TODO, True)
    assert h.status_json(order.id) == {"stage": "deck_todo", "paid": True, "status": "work"}

    # Claude сделал презентацию → проверка → клиенту выбор формата
    h.claude_delivers(order.id, "deck", ["deck.pptx", "deck.pdf"])
    assert await h.run_reviews() == 1
    await h.click(MgrCb(action="rv_send", order_id=order.id).pack(), user=ADMIN)
    order = await h.order()
    assert (order.status, order.stage) == (OrderStatus.DONE, Stage.DONE)
    assert any(f"Презентация #{order.id} готова" in m for m in h.texts(CLIENT))

    await h.click(FmtCb(order_id=order.id, fmt="pdf").pack())
    sent = h.sent("SendDocument", CLIENT)
    assert sent and Path(sent[-1].document.path).name == "deck.pdf"
    texts = h.texts(CLIENT)
    assert any("Две правки — бесплатно" in m for m in texts)
    assert any("Сделаем выгоднее" in m for m in texts)  # зачёт заказа в пакет


async def test_owner_asks_claude_to_redo(h: Harness) -> None:
    await onboard(h)
    order = await order_in_chat(h)
    h.claude_delivers(order.id, "cover", ["cover.png"])
    await h.run_reviews()
    await h.click(MgrCb(action="rv_fix", order_id=order.id).pack(), user=ADMIN)
    await h.text("Фон темнее, без людей", user=ADMIN)
    order = await h.order()
    assert order.stage is Stage.COVER_TODO
    notes = (h.work / str(order.id) / "notes.md").read_text(encoding="utf-8")
    assert "Фон темнее, без людей" in notes
    assert list((h.work / str(order.id)).glob("rejected_cover_*"))


# --- переписка, оплата картой, сторож ----------------------------------------------------


async def test_owner_reply_goes_to_client(h: Harness) -> None:
    await onboard(h)
    await h.text("Здравствуйте, сколько стоит 15 слайдов?")
    question = h.texts(ADMIN)[-1]
    assert "ID: <code>777</code>" in question
    plain = re.sub(r"<[^>]+>", "", question)  # Telegram отдаёт текст реплая без HTML
    await h.text("Добрый день! 29 000 сум", user=ADMIN, reply_to=bot_msg(ADMIN, plain))
    assert [c for c in h.tg.of("CopyMessage") if c.chat_id == CLIENT], "ответ владельца ушёл клиенту"
    assert "Ответ SlideLab" in h.texts(CLIENT)[-1]


async def test_card_receipt_confirmed_by_owner(h: Harness) -> None:
    await onboard(h)
    order = await order_in_chat(h)
    await h.click(PayCb(action="card", kind="order", ref=str(order.id)).pack())
    await h.text("Перевёл 29 000 в 14:05 с карты *1234")
    async with h.sm() as s:
        payment = await s.scalar(select(Payment).where(Payment.provider == PaymentProvider.MANUAL_CARD))
        assert payment is not None and payment.status is PaymentStatus.PENDING
    await h.click(MgrCb(action="pay_ok", payment_id=payment.id).pack(), user=ADMIN)
    order = await h.order()
    assert order.is_paid and order.status is OrderStatus.NEW  # оплатил заранее — ждём обложку
    assert any("Оплата получена" in m for m in h.texts(CLIENT))


async def test_stuck_order_alert_once(h: Harness) -> None:
    await onboard(h)
    order = await order_in_chat(h)
    async with h.sm() as s:
        db_order = await s.get(Order, order.id)
        assert db_order is not None
        db_order.stage_at = datetime.now(UTC) - timedelta(hours=5)
        await s.commit()
    assert await h.run_stuck() == 1
    assert f"Заказ #{order.id} не сделан" in h.texts(ADMIN)[-1]
    assert await h.run_stuck() == 0  # повтор — не раньше чем через 12 часов


async def test_strangers_cannot_use_staff_buttons(h: Harness) -> None:
    await onboard(h)
    order = await order_in_chat(h)
    await h.click(MgrCb(action="cancel_yes", order_id=order.id).pack())  # клиент жмёт кнопку владельца
    assert (await h.order()).status is OrderStatus.NEW
