from fastapi import APIRouter, HTTPException

from slidelab.api import payments_flow
from slidelab.api.deps import FlowsDep, SessionDep, ViewerDep
from slidelab.api.schemas import (
    InvoiceIn,
    InvoiceOut,
    LuckyOddsOut,
    LuckyOut,
    LuckyPrizeOut,
    OkOut,
    PointsBoxOut,
    PointsOut,
    PointsPrizeOut,
    PointsResultOut,
    ReceiptIn,
)
from slidelab.core import repositories as repo
from slidelab.core.enums import PaymentProvider, PlanCode
from slidelab.core.errors import NotFoundError
from slidelab.core.i18n import t
from slidelab.core.services import lucky, points
from slidelab.core.services.lucky import LuckyService
from slidelab.core.services.payments import PaymentService
from slidelab.core.services.points import PointsService

router = APIRouter(prefix="/packages", tags=["packages"])


@router.get("/lucky")
async def lucky_info(viewer: ViewerDep, session: SessionDep) -> LuckyOut:
    """Бонус-пакет: цена, шансы (те же числа, по которым идёт розыгрыш), лимит и неоткрытый пакет."""
    service = LuckyService(session)
    plan = await repo.get_plan(session, PlanCode.LUCKY)
    box = await service.pending(viewer.user.id)
    return LuckyOut(
        price=plan.price,
        odds=[LuckyOddsOut(prize=p.code, count=p.count, percent=p.percent) for p in lucky.PRIZES],
        limit=lucky.LIMIT,
        window_days=lucky.WINDOW.days,
        can_buy=False,  # снят с продажи; витрина нужна только чтобы открыть купленный раньше
        pending=LuckyPrizeOut(prize=box.prize, count=box.count) if box else None,
    )


@router.post("/lucky/open")
async def lucky_open(viewer: ViewerDep, session: SessionDep) -> LuckyPrizeOut:
    """Клиент открыл бонус-пакет: презентации уже начислены при оплате, здесь только отметка «посмотрел»."""
    box = await LuckyService(session).open(viewer.user.id)
    if box is None:
        raise NotFoundError("Нет неоткрытого бонус-пакета")
    await session.commit()
    return LuckyPrizeOut(prize=box.prize, count=box.count)


@router.get("/points")
async def points_info(viewer: ViewerDep, session: SessionDep) -> PointsOut:
    """Баллы клиента и три пакета за баллы — с теми же шансами, по которым идёт розыгрыш."""
    service = PointsService(session)
    balance = await service.balance(viewer.user)
    await session.commit()  # если баллы сгорели — списание сохраняется
    return PointsOut(
        points=balance,
        expire_at=viewer.user.points_expire_at,
        per_presentation=points.PER_PRESENTATION,
        expire_days=points.EXPIRE_DAYS,
        discount_pct=viewer.user.discount_pct,
        boxes=[
            PointsBoxOut(
                key=b.key,
                price=b.price,
                prizes=[PointsPrizeOut(prize=p.code, value=p.value, percent=p.percent) for p in b.prizes],
            )
            for b in points.BOXES.values()
        ],
    )


@router.post("/points/{key}")
async def points_box(key: str, viewer: ViewerDep, session: SessionDep) -> PointsResultOut:
    """Пакет за баллы: списать баллы и сразу разыграть приз (презентации и скидка начисляются сразу)."""
    box = await PointsService(session).open_box(viewer.user, key)
    await session.commit()
    return PointsResultOut(prize=box.prize, value=box.count, points=viewer.user.points)


@router.post("/{plan}/invoice")
async def invoice(
    plan: PlanCode, body: InvoiceIn, viewer: ViewerDep, session: SessionDep, flows: FlowsDep
) -> InvoiceOut:
    """Как в боте: недавно сданный заказ засчитывается в пакет сам, владелец получает заявку."""
    user = viewer.user
    payments = PaymentService(session)
    if plan is PlanCode.LUCKY:
        # бонус-пакет снят с продажи (вместо него — кейсы за баллы); купленные раньше открываются как прежде
        raise HTTPException(status_code=422, detail="Бонус-пакет больше не продаётся")
    credit_id = None if body.gift else await payments.best_credit(user.id, plan)
    quote = await payments.plan_quote(plan, credit_id, user.id)
    if body.provider == "card":
        if body.app:
            return payments_flow.card_in_app(flows.n, quote.amount)
        await flows.plan_payment(user, plan, credit_id or 0, as_gift=body.gift)
        await session.commit()
        return InvoiceOut(provider="card", amount=quote.amount, currency="UZS")
    payments_flow.ensure_stars(flows.n)
    package_plan = await repo.get_plan(session, plan)
    payment = await payments.for_plan(user.id, plan, PaymentProvider.STARS, credit_id, as_gift=body.gift)
    await session.commit()
    count = package_plan.count - (quote.credit.units if quote.credit else 0)
    title = t(user.lang, "invoice_package", plan=t(user.lang, "plan_" + plan.value))
    return await payments_flow.stars_invoice(
        payment,
        ("🎁 " + title) if body.gift else title,
        t(user.lang, "invoice_package_desc", count=count, days=package_plan.days),
        bot=flows.bot,
    )


@router.post("/{plan}/receipt")
async def receipt(plan: PlanCode, body: ReceiptIn, viewer: ViewerDep, session: SessionDep, flows: FlowsDep) -> OkOut:
    """Скриншот оплаты пакета из приложения — владельцу, как чек из чата."""
    user = viewer.user
    blob, ext = payments_flow.decode_image(body.image)
    payments = PaymentService(session)
    credit_id = None if body.gift else await payments.best_credit(user.id, plan)
    payment = await payments.for_plan(user.id, plan, PaymentProvider.MANUAL_CARD, credit_id, as_gift=body.gift)
    await session.commit()
    what = f"пакет «{t(None, 'plan_' + plan.value)}»" + (f" (засчитан #{credit_id})" if payment.credit_order_id else "")
    if body.gift:
        what = "🎁 в подарок: " + what
    await payments_flow.receipt_to_staff(flows.n, user, payment, what, blob, ext)
    await session.commit()
    return OkOut()
