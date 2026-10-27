from fastapi import APIRouter
from sqlalchemy import func, select

from slidelab.api.deps import SessionDep, ViewerDep
from slidelab.api.schemas import LangIn, MeOut, PackageOut
from slidelab.core import repositories as repo
from slidelab.core.models import Order
from slidelab.core.models.base import utcnow

router = APIRouter(prefix="/me", tags=["me"])


@router.get("")
async def get_me(viewer: ViewerDep, session: SessionDep) -> MeOut:
    user = viewer.user
    package = await repo.get_active_package(session, user.id, utcnow())
    first = None
    if not await repo.has_orders(session, user.id):
        first = (await repo.get_price_rule_row(session)).first_order_s10
    active = await session.scalar(
        select(func.count(Order.id)).where(Order.user_id == user.id, Order.status.in_(repo.ACTIVE_STATUSES))
    )
    return MeOut(
        id=user.id,
        first_name=user.first_name,
        username=user.username,
        photo_url=viewer.tg.photo_url,
        lang=user.lang,
        first_order_price=first,
        package=PackageOut(
            plan=package.plan_code, left=package.left, total=package.total, expires_at=package.expires_at
        )
        if package
        else None,
        active_orders=int(active or 0),
    )


@router.patch("")
async def set_lang(body: LangIn, viewer: ViewerDep, session: SessionDep) -> MeOut:
    viewer.user.lang = body.lang
    await session.commit()
    return await get_me(viewer, session)
