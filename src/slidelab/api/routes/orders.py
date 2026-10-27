import html
from io import BytesIO
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, Response
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from slidelab.api import payments_flow
from slidelab.api.auth import TgUser
from slidelab.api.deps import BotDep, FlowsDep, SessionDep, SettingsDep, ViewerDep
from slidelab.api.schemas import (
    EventOut,
    InvoiceIn,
    InvoiceOut,
    OkOut,
    OrderOut,
    QuoteIn,
    QuoteOut,
    RevisionIn,
)
from slidelab.core import repositories as repo
from slidelab.core.enums import AttachmentKind, Lang, OrderSource, OrderStatus, PaymentProvider, Stage
from slidelab.core.i18n import guess_lang, t
from slidelab.core.models import Attachment, Order, OrderEvent, ShowcaseStyle, User
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
    flows.pipeline.add_note(order.id, "Клиент (обложка)", body.text)
    await flows.sync(order)
    await session.commit()
    await flows.n.refresh_card(order, f"🎨 хочет другую обложку — Claude переделает:\n{html.escape(body.text)}")
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
    revision = await OrderService(session).request_revision(order_id, viewer.user.id, body.text)
    order = await repo.get_order(session, order_id)
    flows.pipeline.add_note(order.id, "Клиент (правки)", body.text)
    await flows.sync(order)
    await session.commit()
    paid = " · <b>платная</b>" if revision.is_paid else ""
    await flows.n.refresh_card(order, f"✏️ правки{paid} — Claude вносит:\n{html.escape(body.text)}")
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
