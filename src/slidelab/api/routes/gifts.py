"""Подарки из кошелька: купон или презентации из пакета — ссылкой другу."""

from fastapi import APIRouter, HTTPException

from slidelab.api.deps import SessionDep, SettingsDep, ViewerDep
from slidelab.api.schemas import GiftIn, GiftOut, OkOut
from slidelab.core.enums import GiftKind
from slidelab.core.models import Coupon, Gift
from slidelab.core.services.gifts import GiftService, link

router = APIRouter(prefix="/gifts", tags=["gifts"])


async def _out(service: GiftService, gift: Gift, bot_username: str) -> GiftOut:
    slides = None
    if gift.kind is GiftKind.COUPON and gift.coupon_id:
        coupon = await service.session.get(Coupon, gift.coupon_id)
        slides = coupon.slides if coupon else None
    return GiftOut(
        id=gift.id,
        kind=gift.kind,
        count=gift.count,
        slides=slides,
        plan=gift.plan_code,
        link=link(bot_username, gift),
        created_at=gift.created_at,
    )


@router.get("")
async def my_gifts(viewer: ViewerDep, session: SessionDep, settings: SettingsDep) -> list[GiftOut]:
    """Отправленные подарки, которые ещё не забрали — их можно переслать или отменить."""
    service = GiftService(session)
    return [await _out(service, g, settings.bot_username) for g in await service.pending(viewer.user.id)]


@router.post("")
async def make_gift(body: GiftIn, viewer: ViewerDep, session: SessionDep, settings: SettingsDep) -> GiftOut:
    service = GiftService(session)
    if body.kind is GiftKind.COUPON:
        if body.coupon_id is None:
            raise HTTPException(status_code=422, detail="Какой купон подарить?")
        gift = await service.gift_coupon(viewer.user.id, body.coupon_id)
    else:
        gift = await service.gift_pack(viewer.user.id)
    await session.commit()
    return await _out(service, gift, settings.bot_username)


@router.delete("/{gift_id}")
async def revoke_gift(gift_id: int, viewer: ViewerDep, session: SessionDep) -> OkOut:
    await GiftService(session).revoke(gift_id, viewer.user.id)
    await session.commit()
    return OkOut()
