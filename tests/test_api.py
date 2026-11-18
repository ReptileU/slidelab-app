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
        _env_file=None,
        bot_token=TOKEN,
        managers_chat_id=MANAGERS_CHAT,
        pay_uzum="8600 0000",
        work_dir=tmp_path,
        data_dir=tmp_path / "data",
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
    assert inv | {"cards": [], "name": ""} == inv and inv["url"] == "https://t.me/$fake_invoice"
    assert (inv["provider"], inv["amount"], inv["currency"]) == ("stars", 190, "XTR")
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


async def test_review_can_be_withdrawn_by_author_only(env: dict[str, Any]) -> None:
    c: AsyncClient = env["client"]
    assert (await c.get("/api/reviews/mine", headers=auth())).json() is None
    await c.post("/api/reviews", json={"stars": 4, "text": "Хорошо"}, headers=auth())
    mine = (await c.get("/api/reviews/mine", headers=auth())).json()
    assert mine["stars"] == 4 and mine["text"] == "Хорошо"
    assert (await c.delete(f"/api/reviews/{mine['id']}", headers=auth(888))).status_code == 404  # чужой
    assert (await c.delete(f"/api/reviews/{mine['id']}", headers=auth())).json() == {"ok": True}
    assert (await c.get("/api/reviews/mine", headers=auth())).json() is None
    assert (await c.delete(f"/api/reviews/{mine['id']}", headers=auth())).status_code == 404  # уже отозван


# --- готовая презентация: листать, скачать, правки по слайдам -------------------------


async def test_deck_viewer_downloads_and_slide_marks(env: dict[str, Any]) -> None:
    import base64

    from slidelab.core.enums import OrderStatus

    c: AsyncClient = env["client"]
    oid = (await c.post("/api/orders", json=ORDER, headers=auth())).json()["id"]
    sent = env["work"] / str(oid) / "sent_deck_1"
    sent.mkdir(parents=True)
    (sent / "Японии.pdf").write_bytes(b"%PDF-1.4 fake")
    (sent / "Японии.pptx").write_bytes(b"PK fake")
    async with env["sm"]() as s:
        order = await s.get(Order, oid)
        assert order is not None
        order.status = OrderStatus.DONE
        order.deliver_dir = f"{oid}/sent_deck_1"
        order.deliver_files = ["Японии.pdf", "Японии.pptx"]
        await s.commit()

    assert (await c.get(f"/api/orders/{oid}", headers=auth())).json()["has_deck"] is True
    pdf = await c.get(f"/api/orders/{oid}/deck.pdf", headers=auth())
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    assert (await c.get(f"/api/orders/{oid}/deck.pdf", headers=auth(999))).status_code == 404  # чужой заказ

    links = (await c.get(f"/api/orders/{oid}/downloads", headers=auth())).json()
    assert {item["name"] for item in links} == {"Японии.pdf", "Японии.pptx"}
    url = links[0]["url"]
    path = url[url.index("/api/") :]
    assert (await c.get(path)).status_code == 200  # подписанная ссылка — без initData
    assert (await c.get(path.replace("sig=", "sig=0"))).status_code == 403

    png = "data:image/png;base64," + base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"0" * 20).decode()
    body = {"text": "", "marks": [{"slide": 3, "x": 0.8, "y": 0.1, "text": "Заменить график"}], "shots": [png]}
    assert (await c.post(f"/api/orders/{oid}/revisions", json=body, headers=auth())).status_code == 200
    notes = (env["work"] / str(oid) / "notes.md").read_text(encoding="utf-8")
    assert "Слайд 3 (метка 1, справа, вверху): Заменить график" in notes and "edits/slide_marks_" in notes
    assert list((env["work"] / str(oid) / "edits").glob("slide_marks_*.png"))
    empty = {"text": "", "marks": []}
    assert (await c.post(f"/api/orders/{oid}/revisions", json=empty, headers=auth())).status_code == 422


async def test_card_payment_in_app_with_receipt(env: dict[str, Any]) -> None:
    import base64

    c: AsyncClient = env["client"]
    oid = (await c.post("/api/orders", json=ORDER, headers=auth())).json()["id"]
    inv = (await c.post(f"/api/orders/{oid}/invoice", json={"provider": "card", "app": True}, headers=auth())).json()
    assert inv["cards"] == [{"label": "Uzum Bank", "number": "8600 0000"}]
    shot = "data:image/jpeg;base64," + base64.b64encode(b"\xff\xd8\xff fake jpeg").decode()
    r = await c.post(f"/api/orders/{oid}/receipt", json={"image": shot}, headers=auth())
    assert r.status_code == 200 and r.json() == {"ok": True}
    tg = env["tg"]
    assert tg.of("SendPhoto") and any("Деньги пришли?" in m.text for m in tg.of("SendMessage"))
    bad = await c.post(f"/api/orders/{oid}/receipt", json={"image": "data:text/plain;base64,aGVsbG8="}, headers=auth())
    assert bad.status_code >= 400
    assert (await c.post("/api/packages/month/receipt", json={"image": shot}, headers=auth())).status_code == 200


async def test_order_thumb_is_first_slide(env: dict[str, Any]) -> None:
    from PIL import Image

    from slidelab.core.enums import OrderStatus

    c: AsyncClient = env["client"]
    oid = (await c.post("/api/orders", json=ORDER, headers=auth())).json()["id"]
    assert (await c.get(f"/api/orders/{oid}/thumb", headers=auth())).status_code == 404  # ни обложки, ни PDF
    sent = env["work"] / str(oid) / "sent_deck_1"
    sent.mkdir(parents=True)
    Image.new("RGB", (160, 90), (200, 30, 30)).save(sent / "deck.pdf")
    async with env["sm"]() as s:
        order = await s.get(Order, oid)
        assert order is not None
        order.status = OrderStatus.DONE
        order.deliver_dir = f"{oid}/sent_deck_1"
        order.deliver_files = ["deck.pdf"]
        await s.commit()
    r = await c.get(f"/api/orders/{oid}/thumb", headers=auth())
    assert r.status_code == 200 and r.content[:2] == b"\xff\xd8"
    assert (sent / ".thumb.jpg").exists()


async def test_cancelled_order_can_be_removed_from_list(env: dict[str, Any]) -> None:
    from slidelab.core.enums import OrderStatus

    c: AsyncClient = env["client"]
    oid = (await c.post("/api/orders", json=ORDER, headers=auth())).json()["id"]
    assert (await c.post(f"/api/orders/{oid}/hide", headers=auth())).status_code == 409  # ещё не отменён
    async with env["sm"]() as s:  # отменил менеджер, как старый заказ #6
        order = await s.get(Order, oid)
        assert order is not None
        order.status = OrderStatus.CANCELLED
        await s.commit()
    assert (await c.post(f"/api/orders/{oid}/hide", headers=auth(888))).status_code == 404  # чужой
    assert (await c.post(f"/api/orders/{oid}/hide", headers=auth())).json() == {"ok": True}
    assert oid not in [o["id"] for o in (await c.get("/api/orders", headers=auth())).json()]


async def test_wallet_cover_from_photo(env: dict[str, Any]) -> None:
    import base64
    from io import BytesIO

    from PIL import Image

    c: AsyncClient = env["client"]
    buf = BytesIO()
    Image.new("RGB", (900, 1600), (200, 40, 90)).save(buf, "JPEG")  # вертикальное фото с телефона
    photo = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
    assert (await c.get("/api/me/wallet-cover", headers=auth())).status_code == 404
    me = (await c.post("/api/me/wallet-cover", json={"image": photo}, headers=auth())).json()
    assert me["wallet_cover"]
    res = await c.get("/api/me/wallet-cover", headers=auth())
    assert res.status_code == 200 and Image.open(BytesIO(res.content)).size == (1200, 760)  # кадр под кошелёк
    bad = await c.post("/api/me/wallet-cover", json={"image": "data:image/jpeg;base64,AAAA"}, headers=auth())
    assert bad.status_code >= 400
    assert (await c.delete("/api/me/wallet-cover", headers=auth())).json()["wallet_cover"] is None
    assert (await c.get("/api/me/wallet-cover", headers=auth())).status_code == 404


async def test_gift_card_to_forward_and_prepared_share(env: dict[str, Any]) -> None:
    from sqlalchemy import select

    from slidelab.core.enums import CouponOrigin, SlideTier
    from slidelab.core.models import Coupon, User

    c: AsyncClient = env["client"]
    await c.get("/api/me", headers=auth())  # клиент заведён
    async with env["sm"]() as s:
        user = (await s.scalars(select(User).where(User.tg_id == CLIENT_TG))).one()
        coupon = Coupon(user_id=user.id, slides=SlideTier.S20, origin=CouponOrigin.CANCEL)
        s.add(coupon)
        await s.commit()
        cid = coupon.id
    gift = (await c.post("/api/gifts", json={"kind": "coupon", "coupon_id": cid}, headers=auth())).json()
    assert "start=gift_" in gift["link"]
    shared = (await c.post(f"/api/gifts/{gift['id']}/share", headers=auth())).json()
    assert shared["prepared_id"]
    photos = env["tg"].of("SendPhoto")
    assert len(photos) == 1 and gift["link"] in str(photos[0].reply_markup)  # открытка с кнопкой «Забрать»
    assert "дарит тебе презентацию" in photos[0].caption
    await c.post(f"/api/gifts/{gift['id']}/share", headers=auth())
    assert len(env["tg"].of("SendPhoto")) == 1  # открытка уже есть — второй раз в чат не шлём
    assert (await c.post(f"/api/gifts/{gift['id']}/share", headers=auth(888))).status_code == 404


async def test_pipeline_api_for_claude_session(tmp_path: Path) -> None:
    from httpx import ASGITransport, AsyncClient
    from pydantic import SecretStr

    settings = Settings(  # type: ignore[call-arg]
        _env_file=None, bot_token=TOKEN, work_dir=tmp_path, data_dir=tmp_path / "data", pipeline_key=SecretStr("k1")
    )
    (tmp_path / "7" / "files").mkdir(parents=True)
    (tmp_path / "7" / "status.json").write_text('{"stage": "cover_todo", "paid": false}', encoding="utf-8")
    (tmp_path / "7" / "brief.json").write_text('{"topic": "Экономика"}', encoding="utf-8")
    (tmp_path / "7" / "files" / "лекция.pdf").write_bytes(b"%PDF")
    app = create_app(settings)
    key = {"X-Pipeline-Key": "k1"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        assert (await c.get("/pipeline/orders")).status_code == 401
        assert (await c.get("/pipeline/orders", headers={"X-Pipeline-Key": "x"})).status_code == 401
        (order,) = (await c.get("/pipeline/orders", headers=key)).json()
        assert order["id"] == 7 and order["status"]["stage"] == "cover_todo" and order["review"] == []
        files = {f["path"] for f in (await c.get("/pipeline/orders/7", headers=key)).json()}
        assert files == {"status.json", "brief.json", "files/лекция.pdf"}
        brief = await c.get("/pipeline/orders/7/file", params={"path": "brief.json"}, headers=key)
        assert brief.json() == {"topic": "Экономика"}
        put = lambda p, body: c.put("/pipeline/orders/7/file", params={"path": p}, content=body, headers=key)  # noqa: E731
        assert (await put("review/claim.json", b'{"started": "now"}')).status_code == 200
        assert (await put("review/review.json", b"not json")).status_code == 422
        assert (await put("brief.json", b"{}")).status_code == 403  # задание не трогаем
        assert (await put("review/../brief.json", b"{}")).status_code in (400, 403)
        (order,) = (await c.get("/pipeline/orders", headers=key)).json()
        assert order["claim"] == {"started": "now"} and order["review"] == ["claim.json"]
    no_key = create_app(Settings(_env_file=None, bot_token=TOKEN, work_dir=tmp_path))  # type: ignore[call-arg]
    async with AsyncClient(transport=ASGITransport(app=no_key), base_url="http://test") as c:
        assert (await c.get("/pipeline/orders", headers=key)).status_code in (404, 405)  # без ключа — выключено


def test_cloud_database_url_is_normalized() -> None:
    from slidelab.config import normalize_db_url

    neon = "postgresql://u:p@ep-x.eu-central-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"
    assert normalize_db_url(neon) == "postgresql+asyncpg://u:p@ep-x.eu-central-1.aws.neon.tech/neondb?ssl=require"
    assert normalize_db_url("postgres://u:p@h/db") == "postgresql+asyncpg://u:p@h/db"
    assert normalize_db_url("sqlite+aiosqlite:///data/slidelab.db") == "sqlite+aiosqlite:///data/slidelab.db"


def test_render_service_url_becomes_webhook_and_webapp() -> None:
    from slidelab.cloud import with_service_url

    base = Settings(_env_file=None, bot_token=TOKEN)  # type: ignore[call-arg]
    s = with_service_url(base, {"RENDER_EXTERNAL_URL": "https://slidelab.onrender.com"})
    assert (s.webhook_url, s.webapp_url, s.legacy_webapp) == (
        "https://slidelab.onrender.com",
        "https://slidelab.onrender.com/",
        False,
    )
    assert with_service_url(base, {}) is base  # не в облаке — ничего не меняем
