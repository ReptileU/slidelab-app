from fastapi import APIRouter

from slidelab.api import payments_flow
from slidelab.api.deps import FlowsDep, SessionDep, ViewerDep
from slidelab.api.schemas import InvoiceIn, InvoiceOut
from slidelab.core import repositories as repo
from slidelab.core.enums import PaymentProvider, PlanCode
from slidelab.core.i18n import t
from slidelab.core.services.payments import PaymentService

router = APIRouter(prefix="/packages", tags=["packages"])


@router.post("/{plan}/invoice")
async def invoice(
    plan: PlanCode, body: InvoiceIn, viewer: ViewerDep, session: SessionDep, flows: FlowsDep
) -> InvoiceOut:
    user = viewer.user
    package_plan = await repo.get_plan(session, plan)
    if body.provider == "card":
        out = await payments_flow.card_in_chat(flows.n, user, package_plan.price, plan=plan)
        await session.commit()
        return out
    payment = await PaymentService(session).for_plan(user.id, plan, PaymentProvider.STARS)
    await session.commit()
    return await payments_flow.stars_invoice(
        payment,
        t(user.lang, "invoice_package", plan=t(user.lang, "plan_" + plan.value)),
        t(user.lang, "invoice_package_desc", count=package_plan.count, days=package_plan.days),
        bot=flows.bot,
    )
