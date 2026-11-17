from io import BytesIO
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from PIL import Image, ImageOps
from sqlalchemy import func, select

from slidelab.api.deps import SessionDep, SettingsDep, ViewerDep
from slidelab.api.payments_flow import decode_image
from slidelab.api.schemas import LangIn, MeOut, PackageOut, WalletCoverIn
from slidelab.core import repositories as repo
from slidelab.core.errors import DomainError
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
    vouchers = await repo.open_vouchers(session, user.id)
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
        voucher=vouchers[0].slides if vouchers else None,
        vouchers=len(vouchers),
        voucher_list=[v.slides for v in vouchers],
        wallet_cover=user.wallet_cover,
    )


@router.patch("")
async def set_lang(body: LangIn, viewer: ViewerDep, session: SessionDep) -> MeOut:
    viewer.user.lang = body.lang
    await session.commit()
    return await get_me(viewer, session)


# --- кошелёк: обложка из фото клиента ------------------------------------------------------

WALLET_W, WALLET_H = 1200, 760  # пропорции передней стенки кошелька


def _wallet_dir(data_dir: Path) -> Path:
    path = data_dir / "wallet"
    path.mkdir(parents=True, exist_ok=True)
    return path


def make_wallet_cover(blob: bytes) -> bytes:
    """Фото → обложка кошелька: поворот по EXIF, кадр по центру под пропорции кошелька, JPEG."""
    try:
        img = ImageOps.exif_transpose(Image.open(BytesIO(blob))).convert("RGB")
    except Exception:
        raise DomainError("Не получилось открыть фото — попробуйте другое") from None
    img = ImageOps.fit(img, (WALLET_W, WALLET_H), Image.Resampling.LANCZOS, centering=(0.5, 0.45))
    out = BytesIO()
    img.save(out, "JPEG", quality=86, optimize=True, progressive=True)
    return out.getvalue()


@router.post("/wallet-cover")
async def set_wallet_cover(body: WalletCoverIn, viewer: ViewerDep, session: SessionDep, settings: SettingsDep) -> MeOut:
    blob, _ = decode_image(body.image)
    folder = _wallet_dir(settings.data_dir)
    user = viewer.user
    name = f"{user.id}_{int(utcnow().timestamp())}.jpg"
    (folder / name).write_bytes(make_wallet_cover(blob))
    old = user.wallet_cover
    user.wallet_cover = name
    await session.commit()
    if old:
        (folder / old).unlink(missing_ok=True)
    return await get_me(viewer, session)


@router.delete("/wallet-cover")
async def reset_wallet_cover(viewer: ViewerDep, session: SessionDep, settings: SettingsDep) -> MeOut:
    old, viewer.user.wallet_cover = viewer.user.wallet_cover, None
    await session.commit()
    if old:
        (_wallet_dir(settings.data_dir) / old).unlink(missing_ok=True)
    return await get_me(viewer, session)


@router.get("/wallet-cover", response_model=None)
async def wallet_cover(viewer: ViewerDep, settings: SettingsDep) -> FileResponse:
    name = viewer.user.wallet_cover
    path = _wallet_dir(settings.data_dir) / name if name else None
    if path is None or not path.is_file():
        raise HTTPException(status_code=404, detail="Обложки нет")
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=86400"})
