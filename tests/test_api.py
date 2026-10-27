import json
import time
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from aiogram.fsm.storage.memory import MemoryStorage
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from fakes import TOKEN, FakeSession, make_bot
from slidelab.api.auth import InitDataError, sign_init_data, validate_init_data
from slidelab.api.main import create_app
from slidelab.config import Settings
from slidelab.core.models import Base, Order
from slidelab.core.seed import seed
from slidelab.core.services.orders import OrderService

MANAGERS_CHAT = -100500
CLIENT_TG = 777


def init_data(tg_id: int = CLIENT_TG, *, token: str = TOKEN, auth_date: int | None = None) -> str:
    user = json.dumps({"id": tg_id, "first_name": "Аня", "username": "anya", "language_code": "ru"})
    return sign_init_data({"user": user, "auth_date": str(auth_date or int(time.time()))}, token)


def auth(tg_id: int = CLIENT_TG) -> dict[str, str]:
    return {"Authorization": f"tma {init_data(tg_id)}"}


ORDER = {
    "topic": "Экономика Японии",
    "slides": "s20",
    "deadline": "normal",
    "pres_lang": "ru",
    "design": "ours",
}


@pytest.fixture
async def env(tmp_path: Path) -> AsyncIterator[dict[str, Any]]:
    engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    async with sessionmaker() as s:
        await seed(s)
        await s.commit()

    settings = Settings(  # type: ignore[call-arg]
        _env_file=None, bot_token=TOKEN, managers_chat_id=MANAGERS_CHAT, pay_uzum="8600 0000", work_dir=tmp_path
    )
    app = create_app(settings)
    bot, tg = make_bot()
    storage = MemoryStorage()
    app.state.sessionmaker, app.state.bot, app.state.storage = sessionmaker, bot, storage
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield {"client": client, "tg": tg, "storage": storage, "sm": sessionmaker, "bot": bot, "work": tmp_path}
    await engine.dispose()


# --- initData ---------------------------------------------------------------


def test_init_data_signature() -> None:
    user = validate_init_data(init_data(), TOKEN, ttl=60)
    assert (user.id, user.username) == (CLIENT_TG, "anya")
    with pytest.raises(InitDataError, match="Подпись"):
        validate_init_data(init_data(token="1:other"), TOKEN, ttl=60)
    with pytest.raises(InitDataError, match="устарела"):
        validate_init_data(init_data(auth_date=int(time.time()) - 120), TOKEN, ttl=60)
    with pytest.raises(InitDataError):
        validate_init_data("user=1", TOKEN, ttl=60)


async def test_requires_telegram_auth(env: dict[str, Any]) -> None:
    c: AsyncClient = env["client"]
    assert (await c.get("/api/me")).status_code == 401
    bad = {"Authorization": f"tma {init_data(token='1:other')}"}
    assert (await c.get("/api/me", headers=bad)).status_code == 401


# --- каталог и профиль ------------------------------------------------------


async def test_catalog_in_uzbek(env: dict[str, Any]) -> None:
    data = (await env["client"].get("/api/catalog", params={"lang": "uz"})).json()
    assert data["prices"]["s20"] == 29000
    assert [p["code"] for p in data["plans"]] == ["week", "month", "vip"]
    assert len(data["styles"]) == 12 and data["styles"][0]["name"] == "Neon-jurnal"
    assert len(data["works"]) == 5 and len(data["faq"]) == 8
    assert data["faq"][0]["q"] == "Qancha vaqtda?"


async def test_me_new_client_and_language(env: dict[str, Any]) -> None:
    c: AsyncClient = env["client"]
    me = (await c.get("/api/me", headers=auth())).json()
    assert (me["first_name"], me["first_order_price"], me["package"], me["lang"]) == ("Аня", 9900, None, None)
    me = (await c.patch("/api/me", json={"lang": "uz"}, headers=auth())).json()
    assert me["lang"] == "uz"


# --- заказ ------------------------------------------------------------------


async def test_create_order_once_and_notify(env: dict[str, Any]) -> None:
    c: AsyncClient = env["client"]
    tg: FakeSession = env["tg"]
    headers = {**auth(), "Idempotency-Key": "draft-123456"}

    quote = (await c.post("/api/orders/quote", json={"slides": "s10", "deadline": "urgent"}, headers=auth())).json()
    assert quote["price"] == 14850 and quote["first_order_discount"]

    first = await c.post("/api/orders", json=ORDER, headers=headers)
    second = await c.post("/api/orders", json=ORDER, headers=headers)
    assert first.status_code == second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    assert first.json()["status"] == "new" and first.json()["events"][0]["status"] == "new"

    to_client = [m for m in tg.of("SendMessage") if m.chat_id == CLIENT_TG]
    to_managers = [m for m in tg.of("SendMessage") if m.chat_id == MANAGERS_CHAT]
    # подтверждение + реквизиты; повтор запроса — без уведомлений
    assert len(to_client) == 2 and len(to_managers) == 1
    assert "8600 0000" in to_client[1].text
    assert len(tg.of("CreateForumTopic")) == 1
    assert "Экономика Японии" in to_managers[0].text

    orders = (await c.get("/api/orders", headers=auth())).json()
    assert [o["id"] for o in orders] == [first.json()["id"]]
    assert (env["work"] / str(first.json()["id"]) / "brief.json").exists()  # задание для Claude


async def test_invalid_order_rejected(env: dict[str, Any]) -> None:
    c: AsyncClient = env["client"]
    urgent_30 = {**ORDER, "slides": "s30", "deadline": "urgent"}
    assert (await c.post("/api/orders", json=urgent_30, headers=auth())).status_code == 422
    assert (await c.post("/api/orders", json={**ORDER, "topic": "x"}, headers=auth())).status_code == 422


async def test_foreign_order_is_hidden(env: dict[str, Any]) -> None:
    c: AsyncClient = env["client"]
    order_id = (await c.post("/api/orders", json=ORDER, headers=auth())).json()["id"]
    assert (await c.get(f"/api/orders/{order_id}", headers=auth(888))).status_code == 404


async def _to_cover(env: dict[str, Any], order_id: int) -> None:
    async with env["sm"]() as s:
        session: AsyncSession = s
        order = await session.get(Order, order_id)
        assert order is not None
        await OrderService(session).cover_sent(order, actor_id=None)
        await session.commit()


async def test_approve_cover_and_pay_with_stars(env: dict[str, Any]) -> None:
    c: AsyncClient = env["client"]
    order_id = (await c.post("/api/orders", json=ORDER, headers=auth())).json()["id"]
    await _to_cover(env, order_id)

    order = (await c.post(f"/api/orders/{order_id}/approve-cover", headers=auth())).json()
    assert order["status"] == "awaiting_payment"

    inv = (await c.post(f"/api/orders/{order_id}/invoice", json={"provider": "stars"}, headers=auth())).json()
    assert inv == {"provider": "stars", "url": "https://t.me/$fake_invoice", "amount": 190, "currency": "XTR"}
    link = env["tg"].of("CreateInvoiceLink")[-1]
    assert link.payload.startswith("pay:") and link.prices[0].amount == 190


async def test_pay_by_card_sends_details_to_chat(env: dict[str, Any]) -> None:
    c: AsyncClient = env["client"]
    order_id = (await c.post("/api/orders", json=ORDER, headers=auth())).json()["id"]
    await _to_cover(env, order_id)
    await c.post(f"/api/orders/{order_id}/approve-cover", headers=auth())

    inv = (await c.post(f"/api/orders/{order_id}/invoice", json={"provider": "card"}, headers=auth())).json()
    assert (inv["provider"], inv["amount"], inv["currency"]) == ("card", 29000, "UZS")
    details = [m for m in env["tg"].of("SendMessage") if "8600 0000" in m.text]
    assert len(details) == 2  # при заказе и по кнопке «Картой» (окно оплаты после «Нравится» — в самом приложении)
    buttons = [b.text for row in details[-1].reply_markup.inline_keyboard for b in row]
    assert "Я оплатил картой" in buttons


async def test_can_pay_before_cover_but_not_twice(env: dict[str, Any]) -> None:
    c: AsyncClient = env["client"]
    order_id = (await c.post("/api/orders", json=ORDER, headers=auth())).json()["id"]
    r = await c.post(f"/api/orders/{order_id}/invoice", json={"provider": "stars"}, headers=auth())
    assert r.status_code == 200  # обложку делаем бесплатно, но оплатить можно сразу
    async with env["sm"]() as s:
        order = await s.get(Order, order_id)
        assert order is not None
        await OrderService(s).mark_paid(order, actor_id=None)
        await s.commit()
    r = await c.post(f"/api/orders/{order_id}/invoice", json={"provider": "stars"}, headers=auth())
    assert r.status_code == 409 and r.json()["code"] == "invalid_transition"


async def test_package_invoice_and_support(env: dict[str, Any]) -> None:
    c: AsyncClient = env["client"]
    inv = (await c.post("/api/packages/month/invoice", json={"provider": "stars"}, headers=auth())).json()
    assert inv["amount"] == 415  # 64 000 / 155 → вверх до 5
    assert (await c.post("/api/support/messages", json={"text": "Когда будет?"}, headers=auth())).json() == {"ok": True}
    assert (await c.post("/api/reviews", json={"stars": 5}, headers=auth())).status_code == 200
