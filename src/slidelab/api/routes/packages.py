from fastapi import APIRouter

from slidelab.api import payments_flow
from slidelab.api.deps import FlowsDep, SessionDep, ViewerDep
from slidelab.api.schemas import InvoiceIn, InvoiceOut, OkOut, ReceiptIn
from slidelab.core import repositories as repo
from slidelab.core.enums import PaymentProvider, PlanCode
from slidelab.core.i18n import t
from slidelab.core.services.payments import PaymentService

router = APIRouter(prefix="/packages", tags=["packages"])


@router.post("/{plan}/invoice")
async def invoice(
    plan: PlanCode, body: InvoiceIn, viewer: ViewerDep, session: SessionDep, flows: FlowsDep
) -> InvoiceOut:
    """Как в боте: недавно сданный заказ засчитывается в пакет сам, владелец получает заявку."""
    user = viewer.user
    payments = PaymentService(session)
    credit_id = await payments.best_credit(user.id, plan)
    quote = await payments.plan_quote(plan, credit_id, user.id)
    if body.provider == "card":
        if body.app:
            return payments_flow.card_in_app(flows.n, quote.amount)
        await flows.plan_payment(user, plan, credit_id or 0)
        await session.commit()
        return InvoiceOut(provider="card", amount=quote.amount, currency="UZS")
    payments_flow.ensure_stars(flows.n)
    package_plan = await repo.get_plan(session, plan)
    payment = await payments.for_plan(user.id, plan, PaymentProvider.STARS, credit_id)
    await session.commit()
    count = package_plan.count - (quote.credit.units if quote.credit else 0)
    return await payments_flow.stars_invoice(
        payment,
        t(user.lang, "invoice_package", plan=t(user.lang, "plan_" + plan.value)),
        t(user.lang, "invoice_package_desc", count=count, days=package_plan.days),
        bot=flows.bot,
    )


@router.post("/{plan}/receipt")
async def receipt(plan: PlanCode, body: ReceiptIn, viewer: ViewerDep, session: SessionDep, flows: FlowsDep) -> OkOut:
    """Скриншот оплаты пакета из приложения — владельцу, как чек из чата."""
    user = viewer.user
    blob, ext = payments_flow.decode_image(body.image)
    payments = PaymentService(session)
    credit_id = await payments.best_credit(user.id, plan)
    payment = await payments.for_plan(user.id, plan, PaymentProvider.MANUAL_CARD, credit_id)
    await session.commit()
    what = f"пакет «{t(None, 'plan_' + plan.value)}»" + (f" (засчитан #{credit_id})" if payment.credit_order_id else "")
    await payments_flow.receipt_to_staff(flows.n, user, payment, what, blob, ext)
    await session.commit()
    return OkOut()
