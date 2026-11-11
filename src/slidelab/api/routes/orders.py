import base64
import binascii
import hashlib
import hmac
import html
import time
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Header, HTTPException, Response
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from slidelab.api import payments_flow
from slidelab.api.auth import TgUser
from slidelab.api.deps import BotDep, FlowsDep, SessionDep, SettingsDep, ViewerDep
from slidelab.api.schemas import (
    DownloadOut,
    EventOut,
    InvoiceIn,
    InvoiceOut,
    OkOut,
    OrderOut,
    QuoteIn,
    QuoteOut,
    RevisionIn,
)
from slidelab.config import Settings
from slidelab.core import repositories as repo
from slidelab.core.enums import AttachmentKind, Lang, OrderSource, OrderStatus, PaymentProvider, Stage
from slidelab.core.i18n import guess_lang, t
from slidelab.core.models import Attachment, Order, OrderEvent, ShowcaseStyle, User
from slidelab.core.models.order import REVISION_MAX
from slidelab.core.schemas.order import OrderDraft
from slidelab.core.services import pricing
from slidelab.core.services.orders import OrderService
from slidelab.core.services.payments import PaymentService
from slidelab.core.services.pipeline import Pipeline

router = APIRouter(prefix="/orders", tags=["orders"])


async def _own(session: AsyncSession, user: User, order_id: int) -> Order:
    order = await repo.get_order(session, order_id)
    if order.user_id != user.id:
        raise HTTPException(status_code=404, detail="Заказ не найден")
    return order


async def _out(session: AsyncSession, orders: list[Order], *, with_events: bool = False) -> list[OrderOut]:
    ids = [o.id for o in orders]
    kinds: dict[int, set[AttachmentKind]] = {i: set() for i in ids}
    for order_id, kind in await session.execute(
        select(Attachment.order_id, Attachment.kind).where(Attachment.order_id.in_(ids))
    ):
        kinds[order_id].add(kind)
    style_keys = {sid: key for sid, key in await session.execute(select(ShowcaseStyle.id, ShowcaseStyle.key))}
    events: dict[int, list[EventOut]] = {i: [] for i in ids}
    if with_events:
        for e in await session.scalars(select(OrderEvent).where(OrderEvent.order_id.in_(ids)).order_by(OrderEvent.id)):
            if e.from_status != e.to_status:  # смена цены — не этап
                events[e.order_id].append(EventOut(status=e.to_status, at=e.created_at))
    return [
        OrderOut(
            id=o.id,
            topic=o.topic,
            slides=o.slides,
            deadline=o.deadline,
            pres_lang=o.pres_lang,
            design=o.design,
            style_key=style_keys.get(o.style_id) if o.style_id else None,
            status=o.status,
            price=o.price,
            paid_from=o.paid_from,
            package_cost=o.package_cost,
            revisions_left=o.revisions_left,
            # обложка ушла клиенту (вручную или из конвейера)
            has_cover=AttachmentKind.COVER in kinds[o.id]
            or o.stage not in (None, Stage.COVER_TODO, Stage.COVER_REVIEW),
            has_result=AttachmentKind.RESULT in kinds[o.id] or o.deliver_dir is not None,
            has_deck=any(str(n).lower().endswith(".pdf") for n in (o.deliver_files or [])),
            created_at=o.created_at,
            events=events[o.id],
        )
        for o in orders
    ]


@router.post("/quote")
async def quote(body: QuoteIn, viewer: ViewerDep, session: SessionDep) -> QuoteOut:
    q = await OrderService(session).quote(
        viewer.user.id, pricing.QuoteRequest(body.slides, body.deadline, body.extra_text, body.extra_notes)
    )
    return QuoteOut(
        price=q.price,
        paid_from=q.paid_from,
        package_cost=q.package_cost,
        package_left_after=q.package_left_after,
        first_order_discount=q.first_order_discount,
    )


@router.post("", status_code=201)
async def create(
    body: OrderDraft,
    viewer: ViewerDep,
    session: SessionDep,
    flows: FlowsDep,
    idempotency_key: Annotated[str | None, Header(max_length=64)] = None,
) -> OrderOut:
    key = f"app:{viewer.user.tg_id}:{idempotency_key}"[:64] if idempotency_key else None
    if key and (existing := await repo.get_order_by_idempotency_key(session, viewer.user.id, key)):
        return (await _out(session, [existing], with_events=True))[0]  # повтор запроса — без уведомлений
    order = await OrderService(session).create(
        viewer.user.id, body, idempotency_key=key, source=OrderSource.APP, ui_lang=ui_lang(viewer.user, viewer.tg)
    )
    await session.commit()
    await flows.order_created(order, viewer.user)
    await session.commit()
    return (await _out(session, [order], with_events=True))[0]


def ui_lang(user: User, tg: TgUser) -> Lang:
    return user.lang or guess_lang(tg.language_code)


@router.get("")
async def list_orders(viewer: ViewerDep, session: SessionDep) -> list[OrderOut]:
    orders = [o for o in await repo.list_user_orders(session, viewer.user.id, limit=50) if not o.hidden]
    return await _out(session, orders)


@router.get("/{order_id}")
async def get_order(order_id: int, viewer: ViewerDep, session: SessionDep) -> OrderOut:
    order = await _own(session, viewer.user, order_id)
    return (await _out(session, [order], with_events=True))[0]


@router.get("/{order_id}/cover", response_model=None)
async def cover(
    order_id: int, viewer: ViewerDep, session: SessionDep, bot: BotDep, settings: SettingsDep
) -> Response | FileResponse:
    """Обложка — из конвейера (папка заказа) или присланная менеджером вручную."""
    order = await _own(session, viewer.user, order_id)
    path = Pipeline(settings.work_dir).latest_cover(order.id)
    if path is not None:
        return FileResponse(path, headers={"Cache-Control": "private, max-age=3600"})
    att = await session.scalar(
        select(Attachment)
        .where(Attachment.order_id == order.id, Attachment.kind == AttachmentKind.COVER)
        .order_by(Attachment.id.desc())
        .limit(1)
    )
    if att is None or not att.tg_file_id:
        raise HTTPException(status_code=404, detail="Обложки пока нет")
    file = await bot.get_file(att.tg_file_id)
    buffer = BytesIO()
    assert file.file_path is not None
    await bot.download_file(file.file_path, destination=buffer)
    return Response(
        buffer.getvalue(), media_type=att.mime_type or "image/jpeg", headers={"Cache-Control": "private, max-age=3600"}
    )


@router.post("/{order_id}/approve-cover")
async def approve_cover(order_id: int, viewer: ViewerDep, session: SessionDep, flows: FlowsDep) -> OrderOut:
    await _own(session, viewer.user, order_id)
    order = await OrderService(session).approve_cover(order_id, viewer.user.id)
    await flows.sync(order)
    await session.commit()
    if order.status is OrderStatus.WORK:
        await flows.n.refresh_card(order, "👍 обложка одобрена в приложении, оплачено — Claude делает презентацию")
    else:
        await flows.n.refresh_card(order, "👍 обложка одобрена в приложении — ждём оплату")
    await session.commit()
    return (await _out(session, [order], with_events=True))[0]


@router.post("/{order_id}/redo-cover")
async def redo_cover(order_id: int, body: RevisionIn, viewer: ViewerDep, session: SessionDep, flows: FlowsDep) -> OkOut:
    await _own(session, viewer.user, order_id)
    order = await OrderService(session).request_cover_change(order_id, viewer.user.id)
    flows.pipeline.add_note(order.id, "Клиент (обложка)", body.full_text())
    await flows.sync(order)
    await session.commit()
    await flows.n.refresh_card(order, f"🎨 хочет другую обложку — Claude переделает:\n{html.escape(body.full_text())}")
    await session.commit()
    return OkOut()


@router.post("/{order_id}/invoice")
async def invoice(
    order_id: int, body: InvoiceIn, viewer: ViewerDep, session: SessionDep, flows: FlowsDep
) -> InvoiceOut:
    order = await _own(session, viewer.user, order_id)
    user = viewer.user
    if body.provider == "card":
        out = await payments_flow.card_in_chat(flows.n, user, order.price, order=order)
        await session.commit()
        return out
    payments_flow.ensure_stars(flows.n)
    payment = await PaymentService(session).for_order(order, PaymentProvider.STARS)
    await session.commit()
    slides = t(user.lang, "slides_" + order.slides.value)
    return await payments_flow.stars_invoice(
        payment,
        t(user.lang, "invoice_order", id=order.id),
        t(user.lang, "invoice_order_desc", topic=order.topic[:80], slides=slides),
        bot=flows.bot,
    )


@router.post("/{order_id}/revisions")
async def revise(order_id: int, body: RevisionIn, viewer: ViewerDep, session: SessionDep, flows: FlowsDep) -> OrderOut:
    await _own(session, viewer.user, order_id)
    text = body.full_text()[:REVISION_MAX]
    revision = await OrderService(session).request_revision(order_id, viewer.user.id, text)
    order = await repo.get_order(session, order_id)
    shots = save_shots(flows.pipeline, order.id, body.shots)
    note = text + (f"\nСкриншоты слайдов с метками: edits/{', edits/'.join(shots)}" if shots else "")
    flows.pipeline.add_note(order.id, "Клиент (правки)", note)
    await flows.sync(order)
    await session.commit()
    paid = " · <b>платная</b>" if revision.is_paid else ""
    await flows.n.refresh_card(order, f"✏️ правки{paid} — Claude вносит:\n{html.escape(text)}")
    await session.commit()
    return (await _out(session, [order], with_events=True))[0]


@router.post("/{order_id}/send-files")
async def send_files(order_id: int, viewer: ViewerDep, session: SessionDep, flows: FlowsDep) -> OkOut:
    """Готовые файлы — в чат с ботом: там их удобно сохранить или переслать."""
    order = await _own(session, viewer.user, order_id)
    if not await flows.deliver(order, viewer.user, "all"):
        raise HTTPException(status_code=404, detail="Файлы ещё не готовы")
    await session.commit()
    return OkOut()


# --- готовая презентация: листать в приложении и скачать ---------------------------------


def save_shots(pipeline: Pipeline, order_id: int, shots: list[str]) -> list[str]:
    """Снимки слайдов с метками правок → orders/<id>/edits/ (их смотрит Claude). Битые пропускаем."""
    saved = []
    stamp = datetime.now().strftime("%m%d_%H%M%S")
    for i, raw in enumerate(shots, 1):
        data = raw.split(",", 1)[1] if raw.startswith("data:") else raw
        try:
            blob = base64.b64decode(data, validate=True)
        except (binascii.Error, ValueError):
            continue
        ext = ".png" if blob[:4] == b"\x89PNG" else ".jpg" if blob[:2] == b"\xff\xd8" else None
        if ext is None or len(blob) > 1_500_000:
            continue
        name = f"slide_marks_{stamp}_{i}{ext}"
        pipeline.material_path(order_id, name, "edits").write_bytes(blob)
        saved.append(name)
    return saved


def _deck_file(pipeline: Pipeline, order: Order, suffix: str) -> Path | None:
    files = [p for p in pipeline.delivered_files(order) if p.suffix.lower() == suffix]
    return files[0] if files else None


@router.get("/{order_id}/deck.pdf", response_model=None)
async def deck_pdf(order_id: int, viewer: ViewerDep, session: SessionDep, settings: SettingsDep) -> FileResponse:
    """PDF готовой презентации — приложение рисует из него слайды."""
    order = await _own(session, viewer.user, order_id)
    path = _deck_file(Pipeline(settings.work_dir), order, ".pdf")
    if path is None:
        raise HTTPException(status_code=404, detail="Презентации пока нет")
    return FileResponse(path, media_type="application/pdf", headers={"Cache-Control": "private, max-age=600"})


def _sign(settings: Settings, order_id: int, name: str, exp: int) -> str:
    key = hashlib.sha256(b"slidelab-download:" + settings.bot_token.get_secret_value().encode()).digest()
    return hmac.new(key, f"{order_id}:{name}:{exp}".encode(), hashlib.sha256).hexdigest()[:32]


@router.get("/{order_id}/downloads")
async def downloads(order_id: int, viewer: ViewerDep, session: SessionDep, settings: SettingsDep) -> list[DownloadOut]:
    """Ссылки на файлы на час — для Telegram.WebApp.downloadFile (он не умеет передавать заголовки)."""
    order = await _own(session, viewer.user, order_id)
    base = settings.webapp_url.rstrip("/")
    exp = int(time.time()) + 3600
    out = []
    for path in Pipeline(settings.work_dir).delivered_files(order):
        if path.suffix.lower() not in (".pdf", ".pptx", ".docx"):
            continue
        sig = _sign(settings, order.id, path.name, exp)
        query = urlencode({"name": path.name, "exp": exp, "sig": sig})
        out.append(DownloadOut(name=path.name, url=f"{base}/api/orders/{order.id}/file?{query}"))
    return out


@router.get("/{order_id}/file", response_model=None)
async def signed_file(
    order_id: int, name: str, exp: int, sig: str, session: SessionDep, settings: SettingsDep
) -> FileResponse:
    """Скачивание по подписанной ссылке (без initData): имя файла и срок проверяются подписью."""
    if exp < time.time() or not hmac.compare_digest(sig, _sign(settings, order_id, name, exp)):
        raise HTTPException(status_code=403, detail="Ссылка устарела — откройте заказ заново")
    order = await repo.get_order(session, order_id)
    match = [p for p in Pipeline(settings.work_dir).delivered_files(order) if p.name == name]
    if not match:
        raise HTTPException(status_code=404, detail="Файл не найден")
    return FileResponse(match[0], filename=name)
