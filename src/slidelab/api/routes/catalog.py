from typing import Annotated, Any

from fastapi import APIRouter, Query
from sqlalchemy import select

from slidelab.api.deps import SessionDep, SettingsDep
from slidelab.api.schemas import CatalogOut, FaqOut, PlanOut, PricesOut, StyleOut, WorkOut
from slidelab.core import repositories as repo
from slidelab.core.enums import Lang
from slidelab.core.models import FaqItem, PackagePlan, PortfolioWork, ShowcaseStyle

router = APIRouter(prefix="/catalog", tags=["catalog"])


def _tr(texts: dict[str, Any], lang: Lang) -> dict[str, str]:
    result: dict[str, str] = texts.get(lang.value) or texts[Lang.RU.value]
    return result


@router.get("")
async def get_catalog(
    session: SessionDep, settings: SettingsDep, lang: Annotated[Lang, Query()] = Lang.RU
) -> CatalogOut:
    """Цены, тарифы, стили, работы и FAQ. Публичный — без авторизации, его можно кешировать."""
    rule = await repo.get_price_rule_row(session)
    plans = await session.scalars(select(PackagePlan).where(PackagePlan.is_active).order_by(PackagePlan.sort))
    styles = await session.scalars(select(ShowcaseStyle).where(ShowcaseStyle.is_active).order_by(ShowcaseStyle.sort))
    works = await session.scalars(select(PortfolioWork).where(PortfolioWork.is_active).order_by(PortfolioWork.sort))
    faq = await session.scalars(select(FaqItem).where(FaqItem.is_active).order_by(FaqItem.sort))
    return CatalogOut(
        prices=PricesOut(
            s10=rule.s10,
            s20=rule.s20,
            s30=rule.s30,
            urgent_pct=rule.urgent_pct,
            extra_text=rule.extra_text,
            extra_notes=rule.extra_notes,
            first_order_s10=rule.first_order_s10,
            uzs_per_star=rule.uzs_per_star,
        ),
        plans=[
            PlanOut(
                code=p.code,
                count=p.count,
                price=p.price,
                days=p.days,
                notes_free=p.notes_free,
                priority=p.priority,
                max_parallel=p.max_parallel,
            )
            for p in plans
        ],
        styles=[
            StyleOut(key=s.key, tags=s.tags, images=s.images, is_real_work=s.is_real_work, **_tr(s.texts, lang))
            for s in styles
        ],
        works=[WorkOut(image=w.image, **_tr(w.texts, lang)) for w in works],
        faq=[FaqOut(**_tr(f.texts, lang)) for f in faq],
        bot_username=settings.bot_username,
        channel_username=settings.channel.lstrip("@") or "slidelab_uz",
        stars=settings.stars,
    )
