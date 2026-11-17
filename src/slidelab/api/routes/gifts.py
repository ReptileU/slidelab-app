"""Подарки из кошелька: купон или презентации из пакета — ссылкой другу."""

from fastapi import APIRouter, HTTPException

from slidelab.api.deps import FlowsDep, SessionDep, SettingsDep, ViewerDep
from slidelab.api.schemas import GiftIn, GiftOut, GiftShareOut, OkOut
from slidelab.core.enums import GiftKind, GiftStatus
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


@router.post("/{gift_id}/share")
async def share_gift(gift_id: int, viewer: ViewerDep, session: SessionDep, flows: FlowsDep) -> GiftShareOut:
    """Открытка для друга: приходит в чат с ботом (можно переслать) и, где Telegram умеет,
    готовое сообщение для «Поделиться» прямо из приложения."""
    gift = await session.get(Gift, gift_id)
    if gift is None or gift.from_user_id != viewer.user.id:
        raise HTTPException(status_code=404, detail="Подарок не найден")
    if gift.status is not GiftStatus.PENDING:
        raise HTTPException(status_code=409, detail="Подарок уже забрали или отменили")
    prepared = await flows.prepare_gift_share(gift, viewer.user)
    await session.commit()
    return GiftShareOut(prepared_id=prepared)


@router.delete("/{gift_id}")
async def revoke_gift(gift_id: int, viewer: ViewerDep, session: SessionDep) -> OkOut:
    await GiftService(session).revoke(gift_id, viewer.user.id)
    await session.commit()
    return OkOut()
